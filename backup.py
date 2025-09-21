#!/usr/bin/env python3
"""
Gmail to Dropbox Business Backup Script with Search
Backs up emails from all Google Workspace users to Dropbox Business team folder
Includes email search and indexing functionality
"""

# ------------------------------------------------------------------
# Core imports
# ------------------------------------------------------------------
import datetime as dt
import json
import os
import re
import sqlite3
import ssl
import threading
import time
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Email parsing
from email import policy
from email.parser import BytesParser

# ------------------------------------------------------------------
# SSL Configuration - Fix SSL issues with Dropbox
# ------------------------------------------------------------------
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create unverified SSL context
ssl._create_default_https_context = ssl._create_unverified_context
ssl._create_unverified_context = ssl._create_unverified_context

# Try to use certifi if available, but don't require it
try:
    import certifi
    os.environ['SSL_CERT_FILE'] = certifi.where()
    os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
except ImportError:
    pass

# Force requests to not verify SSL
os.environ['PYTHONHTTPSVERIFY'] = '0'
os.environ['CURL_CA_BUNDLE'] = ''

# ------------------------------------------------------------------
# Force a clean network environment (helps avoid corp proxy SSL bugs)
# ------------------------------------------------------------------
for _k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
    os.environ.pop(_k, None)
# Explicitly bypass proxies for Dropbox + Google API hosts
os.environ["NO_PROXY"] = (
    "dropboxapi.com,api.dropboxapi.com,content.dropboxapi.com,notify.dropboxapi.com,"
    "googleapis.com,googleusercontent.com"
)

# -------------------------
# Third-party libs
# -------------------------
# Check for required packages and provide helpful error messages
import sys
try:
    from dotenv import load_dotenv
except ImportError:
    print("❌ Missing required package: python-dotenv")
    print("   Install with: pip install python-dotenv")
    sys.exit(1)

try:
    from tenacity import retry, wait_exponential, stop_after_attempt
except ImportError:
    print("❌ Missing required package: tenacity")
    print("   Install with: pip install tenacity")
    sys.exit(1)

try:
    import requests  # For fallback Dropbox uploads
except ImportError:
    print("❌ Missing required package: requests")
    print("   Install with: pip install requests")
    sys.exit(1)

# Google
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
except ImportError:
    print("❌ Missing Google API packages")
    print("   Install with: pip install google-api-python-client google-auth google-auth-oauthlib google-auth-httplib2")
    sys.exit(1)

# Dropbox
try:
    import dropbox
    from dropbox import Dropbox, DropboxTeam
    from dropbox.files import WriteMode
    from dropbox.exceptions import ApiError, AuthError, BadInputError
except ImportError:
    print("❌ Missing required package: dropbox")
    print("   Install with: pip install dropbox")
    sys.exit(1)

# -------------------------
# ENV / CONSTANTS
# -------------------------
load_dotenv()

# Google Configuration
DELEGATED_ADMIN = os.getenv("GOOGLE_DELEGATED_ADMIN")
SCOPES = [s.strip() for s in os.getenv("GOOGLE_SCOPES", "").split(",") if s.strip()]
SA_JSON = os.getenv("GOOGLE_SA_JSON", "./service_account.json")
USER_DOMAIN_FILTER = os.getenv("USER_DOMAIN_FILTER")
START_DATE = os.getenv("START_DATE", "2024-01-01")

# Backup mode configuration
BACKUP_MODE = os.getenv("BACKUP_MODE", "incremental")  # "full" or "incremental"
EARLIEST_DATE = os.getenv("EARLIEST_DATE", "2000-01-01")  # For full backups
USE_INCREMENTAL = os.getenv("USE_INCREMENTAL", "1") == "1"  # Use saved state

# Dropbox Configuration
DROPBOX_TEAM_TOKEN = os.getenv("DROPBOX_TEAM_TOKEN")
DROPBOX_TEAM_FOLDER = "/Hanni Email Backups"  # Your team folder name
DROPBOX_TEAM_NAMESPACE = os.getenv("DROPBOX_TEAM_NAMESPACE", "12777917905")  # Team folder namespace ID

# Behavior / tuning
MAX_USERS = int(os.getenv("MAX_USERS", "0"))
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "200"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "1"))

# Rate limiting for large backups
RATE_LIMIT_DELAY = float(os.getenv("RATE_LIMIT_DELAY", "0.1"))  # Delay between API calls in seconds
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))  # Process emails in batches
BATCH_DELAY = float(os.getenv("BATCH_DELAY", "5"))  # Delay between batches in seconds
AUTO_RESUME = os.getenv("AUTO_RESUME", "1") == "1"  # Auto-resume on rate limit errors
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "10"))  # Max retries for rate limit errors
CHECKPOINT_INTERVAL = int(os.getenv("CHECKPOINT_INTERVAL", "50"))  # Save progress every N messages

# Time-based throttling
BUSINESS_HOURS_SLOWDOWN = os.getenv("BUSINESS_HOURS_SLOWDOWN", "0") == "1"
BUSINESS_START = int(os.getenv("BUSINESS_START", "9"))  # 9 AM
BUSINESS_END = int(os.getenv("BUSINESS_END", "17"))  # 5 PM
BUSINESS_HOURS_DELAY = float(os.getenv("BUSINESS_HOURS_DELAY", "1.0"))  # Longer delay during business hours

# Testing/diagnostics flags
INCLUDE_ONLY = [e.strip().lower() for e in os.getenv("INCLUDE_ONLY_EMAILS", "").split(",") if e.strip()]
MAX_MSGS = int(os.getenv("MAX_MESSAGES_PER_USER", "0"))
DRY_RUN = os.getenv("DRY_RUN", "0").lower() in ("1", "true", "yes")
INDEX_EMAILS = os.getenv("INDEX_EMAILS", "1") == "1"  # Enable search indexing

BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
TMP_DIR = BASE_DIR / "tmp"
STATE_DIR.mkdir(exist_ok=True)
TMP_DIR.mkdir(exist_ok=True)

# Sanity checks
assert os.path.exists(SA_JSON), "Service account JSON not found (GOOGLE_SA_JSON)"
assert DELEGATED_ADMIN, "GOOGLE_DELEGATED_ADMIN missing in .env"
assert SCOPES, "GOOGLE_SCOPES missing in .env (use full URLs, comma-separated)"

print(f"🗂 Using team folder: {DROPBOX_TEAM_FOLDER}")
if DROPBOX_TEAM_NAMESPACE:
    print(f"🔗 Team folder namespace: {DROPBOX_TEAM_NAMESPACE}")
print(f"👤 Admin email: {DELEGATED_ADMIN}")
print(f"📅 Backup mode: {BACKUP_MODE.upper()}")

# -------------------------
# Google Clients
# -------------------------
def get_scoped_credentials(subject: Optional[str] = None):
    creds = service_account.Credentials.from_service_account_file(SA_JSON, scopes=SCOPES)
    if subject:
        creds = creds.with_subject(subject)
    return creds

def admin_directory():
    """Get Admin SDK client for listing users"""
    creds = get_scoped_credentials(subject=DELEGATED_ADMIN)
    return build("admin", "directory_v1", credentials=creds, cache_discovery=False)

def gmail_client(user_email: str):
    """Get Gmail client for specific user"""
    creds = get_scoped_credentials(subject=user_email)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

# -------------------------
# Enhanced Dropbox Client Setup with FIXED Refresh Token Support for Teams
# -------------------------
def get_dropbox_client():
    """Get Dropbox client with automatic token refresh for Business accounts"""
    
    DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")
    DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
    DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
    
    if DROPBOX_REFRESH_TOKEN and DROPBOX_APP_KEY and DROPBOX_APP_SECRET:
        # Use refresh token for permanent access
        try:
            print("🔄 Attempting to connect with refresh token...")
            
            # For Dropbox Business Team apps, we need to use DropboxTeam first
            from dropbox import DropboxTeam, Dropbox
            
            # Create team client with refresh token
            dbx_team = DropboxTeam(
                app_key=DROPBOX_APP_KEY,
                app_secret=DROPBOX_APP_SECRET,
                oauth2_refresh_token=DROPBOX_REFRESH_TOKEN
            )
            
            # Get the admin member ID to act as
            admin_email = DELEGATED_ADMIN
            
            try:
                # Get team members
                members_result = dbx_team.team_members_list(limit=200)
                
                # Find the admin user
                admin_member_id = None
                for member in members_result.members:
                    if member.profile.email == admin_email:
                        admin_member_id = member.profile.team_member_id
                        print(f"✅ Found team member: {admin_email}")
                        break
                
                if not admin_member_id:
                    # If admin not found, try to use first active member
                    for member in members_result.members:
                        if not member.profile.status.is_suspended():
                            admin_member_id = member.profile.team_member_id
                            admin_email = member.profile.email
                            print(f"⚠️ Admin not found, using: {admin_email}")
                            break
                
                if admin_member_id:
                    # Create client as the specific user
                    dbx = dbx_team.as_user(admin_member_id)
                    print(f"✅ Connected as user: {admin_email}")
                    
                    # Apply namespace if configured
                    if DROPBOX_TEAM_NAMESPACE:
                        from dropbox import common
                        path_root = common.PathRoot.namespace_id(DROPBOX_TEAM_NAMESPACE)
                        dbx = dbx.with_path_root(path_root)
                        print(f"✅ Using team folder namespace: {DROPBOX_TEAM_NAMESPACE}")
                    
                    # Store the member ID for use in requests fallback
                    os.environ['DROPBOX_MEMBER_ID'] = admin_member_id
                    
                    return dbx
                else:
                    print("❌ Could not find any team members")
                    return None
                    
            except Exception as e:
                print(f"❌ Error getting team members: {e}")
                return None
            
        except Exception as e:
            print(f"❌ Refresh token failed: {e}")
            print("   Falling back to regular token...")
    
    # Fallback to regular token (will expire after ~4 hours)
    if not DROPBOX_TEAM_TOKEN:
        print("❌ No Dropbox token available!")
        print("   Please configure either:")
        print("   - DROPBOX_REFRESH_TOKEN + APP_KEY + APP_SECRET (recommended)")
        print("   - DROPBOX_TEAM_TOKEN (will expire)")
        sys.exit(1)
    
    print("⚠️  Using regular access token (will expire after ~4 hours)")
    print("   For long backups, configure refresh token instead")
    
    # Original team token code (fallback)
    dbx = DropboxTeam(DROPBOX_TEAM_TOKEN)
    
    # Find the admin user's member ID
    admin_email = DELEGATED_ADMIN
    members_result = dbx.team_members_list()
    
    admin_member_id = None
    for member in members_result.members:
        if member.profile.email == admin_email:
            admin_member_id = member.profile.team_member_id
            print(f"✅ Admin member ID found: {admin_email}")
            break
    
    if not admin_member_id:
        print(f"⚠️  Could not find {admin_email} in Dropbox Business team")
        print("   Will attempt to use team token directly")
        
    # Apply namespace if configured  
    if DROPBOX_TEAM_NAMESPACE:
        from dropbox import common
        path_root = common.PathRoot.namespace_id(DROPBOX_TEAM_NAMESPACE)
        dbx = dbx.with_path_root(path_root)
        print(f"✅ Using team folder namespace: {DROPBOX_TEAM_NAMESPACE}")
        
    return dbx

# Initialize Dropbox client
dbx = get_dropbox_client()
if not dbx:
    print("❌ Failed to initialize Dropbox client")
    print("   Check your Dropbox configuration:")
    print("   - Ensure your app has team member file access")
    print("   - Verify the refresh token is valid")
    print("   - Check that the admin email exists in the team")
    sys.exit(1)

# -------------------------
# State management
# -------------------------
def load_state(email: str) -> Dict:
    """Load saved state for incremental backups"""
    state_file = STATE_DIR / f"{email}.json"
    if state_file.exists() and USE_INCREMENTAL:
        try:
            with open(state_file, "r") as f:
                state = json.load(f)
                # Migration: ensure all fields exist
                if 'failed_messages' not in state:
                    state['failed_messages'] = []
                if 'checkpoint_msg_id' not in state:
                    state['checkpoint_msg_id'] = None
                if 'checkpoint_page_token' not in state:
                    state['checkpoint_page_token'] = None
                if 'total_processed' not in state:
                    state['total_processed'] = len(state.get('downloaded_ids', []))
                return state
        except:
            pass
    return {
        'downloaded_ids': [], 
        'last_backup': None, 
        'failed_messages': [],
        'checkpoint_msg_id': None,
        'checkpoint_page_token': None,
        'total_processed': 0
    }

def save_state(email: str, state: Dict):
    """Save state for incremental backups with checkpoint support"""
    state_file = STATE_DIR / f"{email}.json"
    
    # Update last backup time
    state['last_backup'] = dt.datetime.now().isoformat()
    
    # Save state
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)

# -------------------------
# Rate limiting with exponential backoff
# -------------------------
def handle_rate_limit_error():
    """Handle rate limit errors with exponential backoff"""
    global rate_limit_count
    rate_limit_count = getattr(handle_rate_limit_error, 'count', 0) + 1
    handle_rate_limit_error.count = rate_limit_count
    
    wait_time = min(300, 2 ** rate_limit_count)  # Cap at 5 minutes
    print(f"⏳ Rate limited. Waiting {wait_time} seconds (attempt {rate_limit_count})...")
    time.sleep(wait_time)
    
    return rate_limit_count < MAX_RETRIES

def apply_rate_limit():
    """Apply configured rate limiting between API calls"""
    delay = RATE_LIMIT_DELAY
    
    # Increase delay during business hours if configured
    if BUSINESS_HOURS_SLOWDOWN:
        current_hour = dt.datetime.now().hour
        if BUSINESS_START <= current_hour < BUSINESS_END:
            delay = BUSINESS_HOURS_DELAY
    
    if delay > 0:
        time.sleep(delay)

# -------------------------
# Gmail operations
# -------------------------
def list_messages(service, user_id: str, query: str = "", page_token: Optional[str] = None):
    """List messages with proper pagination and error handling"""
    try:
        apply_rate_limit()
        result = service.users().messages().list(
            userId=user_id,
            q=query,
            maxResults=PAGE_SIZE,
            pageToken=page_token
        ).execute()
        
        messages = result.get('messages', [])
        next_page_token = result.get('nextPageToken', None)
        
        # Reset rate limit counter on success
        handle_rate_limit_error.count = 0
        
        return messages, next_page_token
        
    except HttpError as e:
        if e.resp.status == 429:  # Rate limit
            if handle_rate_limit_error():
                return list_messages(service, user_id, query, page_token)
            else:
                print(f"❌ Max retries exceeded for rate limit")
                return [], None
        elif e.resp.status == 403:
            print(f"❌ Permission denied for user {user_id}")
            return [], None
        else:
            print(f"❌ Error listing messages: {e}")
            return [], None

def get_message_raw(service, user_id: str, msg_id: str) -> Optional[bytes]:
    """Get raw email data with error handling and retries"""
    try:
        apply_rate_limit()
        msg = service.users().messages().get(
            userId=user_id,
            id=msg_id,
            format='raw'
        ).execute()
        
        raw = msg.get('raw', '')
        if raw:
            # Reset rate limit counter on success
            handle_rate_limit_error.count = 0
            return base64.urlsafe_b64decode(raw)
    except HttpError as e:
        if e.resp.status == 429:  # Rate limit
            if handle_rate_limit_error():
                return get_message_raw(service, user_id, msg_id)
        elif e.resp.status == 404:
            print(f"⚠️  Message not found: {msg_id}")
        else:
            print(f"❌ Error getting message {msg_id}: {e}")
    return None

def parse_internal_date_ms(service, user_id: str, msg_id: str) -> int:
    """Get message internal date in milliseconds"""
    for attempt in range(3):
        try:
            apply_rate_limit()
            msg = service.users().messages().get(
                userId=user_id,
                id=msg_id,
                format='metadata',
                metadataHeaders=['Date']
            ).execute()
            internal_date = msg.get('internalDate', '0')
            return int(internal_date)
        except HttpError as e:
            if e.resp.status == 429 and attempt < 2:
                if handle_rate_limit_error():
                    # Retry
                    continue
        except Exception:
            pass
    return 0

def _safe_filename_component(s: str, max_bytes: int = 120) -> str:
    """Create safe filename from email subject"""
    s = (s or "")
    s = re.sub(r"[\x00-\x1f\x7f]", "_", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"[\\/:*?\"<>|]", "_", s)
    
    b = s.encode("utf-8")
    if len(b) > max_bytes:
        b = b[:max_bytes]
        while True:
            try:
                s = b.decode("utf-8")
                break
            except UnicodeDecodeError:
                b = b[:-1]
                if not b:
                    s = ""
                    break
    return s

def make_dropbox_path(internal_ts_ms: int, subject_hint: str = "", msg_id: str = "") -> str:
    """Create path for email file (without user prefix, will be added later)"""
    dt_utc = dt.datetime.fromtimestamp(internal_ts_ms / 1000.0, dt.timezone.utc)
    y = dt_utc.strftime("%Y")
    m = dt_utc.strftime("%m")
    d = dt_utc.strftime("%d")
    
    hint = _safe_filename_component(subject_hint or "", max_bytes=120)
    if not hint:
        hint = _safe_filename_component((msg_id or "message"), max_bytes=32)

    filename = f"{dt_utc.strftime('%Y%m%d_%H%M%S')}_{hint}.eml"
    if len(filename.encode("utf-8")) > 200:
        base = _safe_filename_component(hint, max_bytes=80)
        filename = f"{dt_utc.strftime('%Y%m%d_%H%M%S')}_{base}.eml"

    # Return path without team folder prefix (will be added in upload function)
    path = f"/{y}/{m}/{d}/{filename}"
    return path

def extract_subject_hint(raw_bytes: bytes) -> str:
    """Extract email subject for filename"""
    try:
        head = raw_bytes.split(b"\r\n\r\n", 1)[0].decode("utf-8", "ignore")
        m = re.search(r"^Subject:\s*(.+)$", head, re.MULTILINE | re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception:
        pass
    return ""

def process_one_message(service, user_email: str, msg_id: str) -> int:
    """Download and upload a single email, and index it for search"""
    try:
        raw_bytes = get_message_raw(service, "me", msg_id)
        if not raw_bytes:
            return 0
        
        internal_ts_ms = parse_internal_date_ms(service, "me", msg_id)
        if internal_ts_ms == 0:
            print(f"⚠️  No date for {msg_id}, skipping")
            return 0
        
        # Use BACKUP_MODE to determine date filtering
        if BACKUP_MODE == "full":
            # Check against EARLIEST_DATE
            earliest_ts = int(dt.datetime.strptime(EARLIEST_DATE, "%Y-%m-%d").timestamp() * 1000)
            if internal_ts_ms < earliest_ts:
                return 0  # Too old, skip
        else:
            # Incremental mode - check against START_DATE
            start_ts = int(dt.datetime.strptime(START_DATE, "%Y-%m-%d").timestamp() * 1000)
            if internal_ts_ms < start_ts:
                return 0  # Too old for incremental
        
        subject_hint = extract_subject_hint(raw_bytes)
        dropbox_path = make_dropbox_path(internal_ts_ms, subject_hint, msg_id)
        
        # Upload to Dropbox
        if not DRY_RUN:
            success = upload_to_dropbox_team(user_email, dropbox_path, raw_bytes, msg_id)
            if not success:
                return 0
                
            # Index for search if enabled
            if INDEX_EMAILS:
                full_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}{dropbox_path}"
                index_email(user_email, msg_id, raw_bytes, full_path, internal_ts_ms)
        
        return len(raw_bytes)
    except Exception as e:
        print(f"❌ Error processing message {msg_id}: {e}")
        return 0

# -------------------------
# Email Search & Indexing
# -------------------------
INDEX_DB = BASE_DIR / "email_index.db"

def init_email_index():
    """Initialize SQLite database for email search"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Create table with full-text search
    cursor.execute('''CREATE TABLE IF NOT EXISTS email_index (
        user_email TEXT,
        message_id TEXT PRIMARY KEY,
        subject TEXT,
        sender TEXT,
        recipients TEXT,
        date INTEGER,
        has_attachments INTEGER,
        attachment_names TEXT,
        size_bytes INTEGER,
        dropbox_path TEXT,
        body_preview TEXT
    )''')
    
    # Create indexes for faster searching
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON email_index(user_email)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON email_index(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_sender ON email_index(sender)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_subject ON email_index(subject)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_has_attachments ON email_index(has_attachments)')
    
    conn.commit()
    conn.close()
    print(f"✅ Email search index initialized at {INDEX_DB}")

def parse_email_metadata(raw_bytes: bytes) -> Dict:
    """Extract searchable metadata from raw email bytes"""
    try:
        # Parse email
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        
        # Extract basic info
        subject = msg.get('Subject', 'No Subject')
        sender = msg.get('From', '')
        recipients = ', '.join([
            msg.get('To', ''),
            msg.get('Cc', ''),
            msg.get('Bcc', '')
        ]).strip(', ')
        date_str = msg.get('Date', '')
        message_id = msg.get('Message-ID', '')
        
        # Parse attachments
        attachments = []
        has_attachments = False
        for part in msg.walk():
            disposition = part.get_content_disposition()
            if disposition and disposition == 'attachment':
                filename = part.get_filename()
                if filename:
                    attachments.append(filename)
                    has_attachments = True
        
        # Get body preview (first 500 chars)
        body_preview = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    try:
                        body_preview = part.get_content()[:500]
                        break
                    except:
                        pass
        else:
            try:
                body_preview = msg.get_content()[:500]
            except:
                pass
        
        return {
            'subject': subject,
            'sender': sender,
            'recipients': recipients,
            'date_str': date_str,
            'message_id': message_id,
            'has_attachments': has_attachments,
            'attachment_names': ', '.join(attachments),
            'body_preview': body_preview
        }
    except Exception as e:
        print(f"⚠️ Error parsing email metadata: {e}")
        return {}

def index_email(user_email: str, msg_id: str, raw_bytes: bytes, dropbox_path: str, timestamp_ms: int):
    """Add email to search index"""
    try:
        metadata = parse_email_metadata(raw_bytes)
        
        conn = sqlite3.connect(INDEX_DB)
        cursor = conn.cursor()
        
        cursor.execute('''INSERT OR REPLACE INTO email_index 
            (user_email, message_id, subject, sender, recipients, date, 
             has_attachments, attachment_names, size_bytes, dropbox_path, body_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (user_email, msg_id, metadata.get('subject', ''), 
             metadata.get('sender', ''), metadata.get('recipients', ''),
             timestamp_ms, 1 if metadata.get('has_attachments') else 0,
             metadata.get('attachment_names', ''), len(raw_bytes),
             dropbox_path, metadata.get('body_preview', '')))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"⚠️ Error indexing email {msg_id}: {e}")

def search_emails(query: str, user: Optional[str] = None, 
                 start_date: Optional[str] = None, 
                 end_date: Optional[str] = None,
                 has_attachments: Optional[bool] = None) -> List[Dict]:
    """Search indexed emails with various filters"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Build query
    conditions = []
    params = []
    
    # Text search across multiple fields
    if query:
        text_condition = '''(subject LIKE ? OR sender LIKE ? OR 
                           recipients LIKE ? OR body_preview LIKE ?)'''
        conditions.append(text_condition)
        query_param = f"%{query}%"
        params.extend([query_param] * 4)
    
    # User filter
    if user:
        conditions.append("user_email = ?")
        params.append(user)
    
    # Date filters
    if start_date:
        start_ts = int(dt.datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        conditions.append("date >= ?")
        params.append(start_ts)
    
    if end_date:
        end_ts = int(dt.datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        conditions.append("date <= ?")
        params.append(end_ts)
    
    # Attachment filter
    if has_attachments is not None:
        conditions.append("has_attachments = ?")
        params.append(1 if has_attachments else 0)
    
    # Build final query
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query_sql = f'''SELECT * FROM email_index 
                   WHERE {where_clause}
                   ORDER BY date DESC
                   LIMIT 100'''
    
    cursor.execute(query_sql, params)
    
    # Format results
    columns = [description[0] for description in cursor.description]
    results = []
    for row in cursor.fetchall():
        result = dict(zip(columns, row))
        # Format date
        result['date_formatted'] = dt.datetime.fromtimestamp(
            result['date'] / 1000
        ).strftime('%Y-%m-%d %H:%M:%S')
        # Format size
        size_mb = result['size_bytes'] / (1024 * 1024)
        result['size_formatted'] = f"{size_mb:.2f} MB"
        results.append(result)
    
    conn.close()
    return results

def interactive_search():
    """Interactive email search interface"""
    print("\n" + "="*60)
    print("📧 Email Search Interface")
    print("="*60)
    
    while True:
        print("\n🔍 Search Options:")
        print("1. Text search (subject, sender, body)")
        print("2. Search by user")
        print("3. Search by date range")
        print("4. Find emails with attachments")
        print("5. Advanced search (combine filters)")
        print("6. Exit search")
        
        choice = input("\nSelect option (1-6): ").strip()
        
        if choice == "1":
            query = input("Enter search text: ").strip()
            results = search_emails(query)
            
        elif choice == "2":
            user = input("Enter user email: ").strip()
            results = search_emails("", user=user)
            
        elif choice == "3":
            start = input("Start date (YYYY-MM-DD) or press Enter to skip: ").strip()
            end = input("End date (YYYY-MM-DD) or press Enter to skip: ").strip()
            results = search_emails("", 
                                  start_date=start if start else None,
                                  end_date=end if end else None)
            
        elif choice == "4":
            results = search_emails("", has_attachments=True)
            
        elif choice == "5":
            query = input("Search text (or press Enter to skip): ").strip()
            user = input("User email (or press Enter to skip): ").strip()
            start = input("Start date YYYY-MM-DD (or press Enter to skip): ").strip()
            end = input("End date YYYY-MM-DD (or press Enter to skip): ").strip()
            attach = input("Has attachments? (y/n or press Enter to skip): ").strip().lower()
            
            has_attach = True if attach == 'y' else (False if attach == 'n' else None)
            
            results = search_emails(
                query if query else "",
                user=user if user else None,
                start_date=start if start else None,
                end_date=end if end else None,
                has_attachments=has_attach
            )
            
        elif choice == "6":
            print("👋 Exiting search...")
            break
            
        else:
            print("❌ Invalid option")
            continue
        
        # Display results
        if results:
            print(f"\n📊 Found {len(results)} results:")
            print("-" * 80)
            
            for i, email in enumerate(results[:10], 1):  # Show first 10
                print(f"\n{i}. {email['subject']}")
                print(f"   From: {email['sender']}")
                print(f"   To: {email['recipients'][:50]}...")
                print(f"   Date: {email['date_formatted']}")
                print(f"   Size: {email['size_formatted']}")
                if email['has_attachments']:
                    print(f"   📎 Attachments: {email['attachment_names']}")
                print(f"   Path: {email['dropbox_path']}")
                print(f"   Preview: {email['body_preview'][:100]}...")
            
            if len(results) > 10:
                print(f"\n... and {len(results) - 10} more results")
                
            # Export option
            export = input("\n💾 Export results to CSV? (y/n): ").strip().lower()
            if export == 'y':
                export_search_results(results)
        else:
            print("\n❌ No results found")

def export_search_results(results: List[Dict]):
    """Export search results to CSV file"""
    import csv
    
    filename = f"email_search_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        if results:
            writer = csv.DictWriter(f, fieldnames=results[0].keys())
            writer.writeheader()
            writer.writerows(results)
    
    print(f"✅ Results exported to {filename}")

def rebuild_index_from_dropbox():
    """Rebuild search index from existing Dropbox files"""
    print("\n🔄 Rebuilding email search index from Dropbox...")
    
    # Backup existing index
    if INDEX_DB.exists():
        backup_name = f"{INDEX_DB}.backup.{int(time.time())}"
        os.rename(INDEX_DB, backup_name)
        print(f"📦 Backed up existing index to {backup_name}")
    
    init_email_index()
    
    indexed_count = 0
    
    try:
        # Import Dropbox types
        from dropbox import files as dropbox_files
        
        # List all files in team folder
        def list_all_files(path=""):
            files = []
            result = dbx.files_list_folder(path)
            
            while True:
                for entry in result.entries:
                    if isinstance(entry, dropbox_files.FileMetadata):
                        if entry.name.endswith('.eml'):
                            files.append(entry)
                
                if not result.has_more:
                    break
                    
                result = dbx.files_list_folder_continue(result.cursor)
            
            return files
        
        # Get all .eml files
        print(f"📂 Scanning {DROPBOX_TEAM_FOLDER} for email files...")
        eml_files = list_all_files("")
        print(f"📧 Found {len(eml_files)} email files to index")
        
        # Process each file
        for i, file_entry in enumerate(eml_files, 1):
            try:
                # Parse user email from path
                # Path format: /user@email.com/YYYY/MM/DD/filename.eml
                path_parts = file_entry.path_display.strip('/').split('/')
                if len(path_parts) > 0:
                    user_email = path_parts[0]
                    
                    # Download file content
                    _, response = dbx.files_download(file_entry.path_display)
                    raw_bytes = response.content
                    
                    # Extract message ID from filename or content
                    msg_id = file_entry.name.replace('.eml', '').split('_')[-1]
                    
                    # Get timestamp from file
                    timestamp_ms = int(file_entry.server_modified.timestamp() * 1000)
                    
                    # Index the email
                    index_email(user_email, msg_id, raw_bytes, file_entry.path_display, timestamp_ms)
                    indexed_count += 1
                    
                    if i % 100 == 0:
                        print(f"   Indexed {i}/{len(eml_files)} emails...")
                        
            except Exception as e:
                print(f"⚠️ Error indexing {file_entry.path_display}: {e}")
                continue
        
        print(f"\n✅ Index rebuilt successfully!")
        print(f"📊 Total emails indexed: {indexed_count}")
        
    except Exception as e:
        print(f"❌ Error rebuilding index: {e}")

# -------------------------
# Dropbox upload with retries and SSL fallback
# -------------------------
def upload_to_dropbox_team(user_email: str, path: str, data: bytes, msg_id: str = "") -> bool:
    """Upload file to Dropbox team folder with user subfolder"""
    
    # Check if Dropbox client exists
    if not dbx:
        print("❌ No Dropbox connection. Check your token.")
        return False
    
    # Build the full path
    # Path comes in as: /2025/09/19/filename.eml
    
    # Parse the path to extract date components
    path_parts = path.strip('/').split('/')
    
    # Check if we have a date structure (YYYY/MM/DD/filename)
    if len(path_parts) >= 4:
        # Try to parse as date structure
        try:
            year = path_parts[0]
            month = path_parts[1]
            day = path_parts[2]
            filename = path_parts[3]
            
            # Validate it looks like a date
            if (len(year) == 4 and year.isdigit() and 
                len(month) == 2 and month.isdigit() and 
                len(day) == 2 and day.isdigit()):
                # Good date structure
                if DROPBOX_TEAM_NAMESPACE:
                    # When using namespace root, paths are relative
                    team_path = f"/{user_email}/{year}/{month}/{day}/{filename}"
                else:
                    # Full path when not using namespace
                    team_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}/{year}/{month}/{day}/{filename}"
            else:
                # Not a date structure, just use filename
                filename = path_parts[-1]
                if DROPBOX_TEAM_NAMESPACE:
                    team_path = f"/{user_email}/{filename}"
                else:
                    team_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}/{filename}"
        except:
            # Any error, just use the filename
            filename = path_parts[-1] if path_parts else 'email.eml'
            if DROPBOX_TEAM_NAMESPACE:
                team_path = f"/{user_email}/{filename}"
            else:
                team_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}/{filename}"
    else:
        # Not enough parts for date structure
        filename = path_parts[-1] if path_parts else 'email.eml'
        if DROPBOX_TEAM_NAMESPACE:
            team_path = f"/{user_email}/{filename}"
        else:
            team_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}/{filename}"
    
    # Try multiple upload attempts
    for attempt in range(3):
        try:
            # Try native Dropbox SDK upload first
            dbx.files_upload(
                data, 
                team_path,
                mode=WriteMode('add'),
                autorename=True,
                mute=True
            )
            
            print(f"✅ Upload successful: {team_path}")
            return True
            
        except ApiError as e:
            if hasattr(e, 'error'):
                error = e.error
                
                # Check for path conflict (file already exists)
                if hasattr(error, 'is_path') and error.is_path():
                    path_error = error.get_path()
                    if hasattr(path_error, 'is_conflict') and path_error.is_conflict():
                        print(f"⭕️ File already exists: {team_path}")
                        return True  # Consider it successful
                
                # Check for insufficient space
                if hasattr(error, 'is_path') and error.is_path():
                    path_error = error.get_path()
                    if hasattr(path_error, 'is_insufficient_space') and path_error.is_insufficient_space():
                        print(f"❌ Insufficient space in Dropbox")
                        return False
            
            # For SSL or other connection errors, try fallback
            if "SSL" in str(e) or "CERTIFICATE" in str(e).upper() or attempt < 2:
                print(f"⚠️ Upload attempt {attempt + 1} failed: {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)  # Exponential backoff
                    
                    # Try with requests as fallback on last attempt
                    if attempt == 1:
                        print("🔄 Trying requests library fallback...")
                        return upload_with_requests_fallback(user_email, path, data, team_path)
            else:
                print(f"❌ Upload failed: {e}")
                return False
                
        except AuthError as e:
            print(f"❌ Authentication error: {e}")
            print("   Check your Dropbox token")
            return False
            
        except Exception as e:
            print(f"⚠️ Unexpected error on attempt {attempt + 1}: {e}")
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                # Last resort - try requests fallback
                print("🔄 Final attempt with requests fallback...")
                return upload_with_requests_fallback(user_email, path, data, team_path)
    
    return False

def upload_with_requests_fallback(user_email: str, path: str, data: bytes, full_path: str) -> bool:
    """Fallback upload using requests library when Dropbox SDK fails"""
    import json
    import requests
    
    # Try to get an access token
    DROPBOX_REFRESH_TOKEN = os.getenv("DROPBOX_REFRESH_TOKEN")
    DROPBOX_APP_KEY = os.getenv("DROPBOX_APP_KEY")
    DROPBOX_APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
    
    if DROPBOX_REFRESH_TOKEN and DROPBOX_APP_KEY and DROPBOX_APP_SECRET:
        # Get a fresh access token from refresh token
        try:
            token_response = requests.post(
                'https://api.dropboxapi.com/oauth2/token',
                data={
                    'grant_type': 'refresh_token',
                    'refresh_token': DROPBOX_REFRESH_TOKEN,
                    'client_id': DROPBOX_APP_KEY,
                    'client_secret': DROPBOX_APP_SECRET
                }
            )
            
            if token_response.status_code == 200:
                token_data = token_response.json()
                token = token_data.get('access_token')
                print("🔑 Got fresh access token for requests fallback")
            else:
                print("❌ Failed to get access token from refresh token")
                return False
                
        except Exception as e:
            print(f"❌ Error getting access token: {e}")
            return False
    else:
        # Fall back to regular token if available
        token = DROPBOX_TEAM_TOKEN
        if not token:
            print("❌ No access token available for fallback")
            return False
    
    try:
        # Get member ID if available
        member_id = os.getenv('DROPBOX_MEMBER_ID')
        
        # Build headers based on namespace usage
        if DROPBOX_TEAM_NAMESPACE:
            # When using namespace, need to include it in headers
            full_path = f"/{user_email}/{path.strip('/')}"
            headers = {
                'Authorization': f'Bearer {token}',
                'Dropbox-API-Arg': json.dumps({
                    'path': full_path,
                    'mode': 'add',
                    'autorename': True,
                    'mute': True
                }),
                'Dropbox-API-Path-Root': json.dumps({
                    '.tag': 'namespace_id',
                    'namespace_id': DROPBOX_TEAM_NAMESPACE
                }),
                'Content-Type': 'application/octet-stream'
            }
        else:
            # Regular path without namespace
            full_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}/{path.strip('/')}"
            headers = {
                'Authorization': f'Bearer {token}',
                'Dropbox-API-Arg': json.dumps({
                    'path': full_path,
                    'mode': 'add',
                    'autorename': True,
                    'mute': True
                }),
                'Content-Type': 'application/octet-stream'
            }
        
        # Add team member selection header if we have a member ID
        if member_id:
            headers['Dropbox-API-Select-User'] = member_id
            print(f"📤 Using team member: {member_id}")
        
        response = requests.post(
            'https://content.dropboxapi.com/2/files/upload',
            headers=headers,
            data=data,
            verify=False,
            timeout=60
        )
        
        if response.status_code == 200:
            print(f"✅ Upload successful (requests fallback): {full_path}")
            return True
        elif response.status_code == 409:
            print(f"⭕️ File already exists (requests): {full_path}")
            return True
        elif response.status_code == 401:
            print(f"❌ Token expired/invalid (requests fallback)")
            return False
        else:
            print(f"❌ Upload failed (requests): {response.status_code} - {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Requests fallback failed: {e}")
        return False

# -------------------------
# Main backup process
# -------------------------
def backup_user_emails(user_email: str) -> Dict:
    """Backup all emails for a single user with checkpoint support"""
    
    print(f"\n{'='*60}")
    print(f"👤 Processing: {user_email}")
    print(f"{'='*60}")
    
    # Load state for incremental backup
    state = load_state(user_email)
    downloaded_ids = set(state.get('downloaded_ids', []))
    failed_messages = state.get('failed_messages', [])
    checkpoint_page_token = state.get('checkpoint_page_token', None)
    total_processed = state.get('total_processed', 0)
    
    # Determine query based on backup mode
    if BACKUP_MODE == "full":
        # Full backup from EARLIEST_DATE
        date_filter = f"after:{EARLIEST_DATE}"
        print(f"🔄 Full backup mode - Getting all emails from {EARLIEST_DATE}")
    else:
        # Incremental backup
        if state.get('last_backup'):
            # Resume from last backup
            last_backup_date = state['last_backup'].split('T')[0]
            date_filter = f"after:{last_backup_date}"
            print(f"🔄 Incremental mode - Getting emails after {last_backup_date}")
        else:
            # First run, use START_DATE
            date_filter = f"after:{START_DATE}"
            print(f"🔄 First backup - Getting emails from {START_DATE}")
    
    try:
        service = gmail_client(user_email)
        
        # Test access
        profile = service.users().getProfile(userId='me').execute()
        total_messages = profile.get('messagesTotal', 0)
        print(f"📊 Total messages in account: {total_messages}")
        
        # Resume from checkpoint if available
        if checkpoint_page_token:
            print(f"⏩ Resuming from checkpoint (already processed: {total_processed})")
        
        downloaded = 0
        failed = 0
        total_size = 0
        page_token = checkpoint_page_token
        
        while True:
            # List messages for this page
            messages, next_page_token = list_messages(service, 'me', date_filter, page_token)
            
            if not messages:
                break
            
            print(f"📥 Processing batch of {len(messages)} messages...")
            
            # Process messages in this batch
            batch_downloaded = 0
            for i, msg in enumerate(messages):
                msg_id = msg['id']
                
                # Skip if already downloaded (unless in full mode and forcing re-download)
                if msg_id in downloaded_ids and BACKUP_MODE != "full":
                    continue
                
                # Skip if in failed list from previous attempts
                if msg_id in failed_messages and not AUTO_RESUME:
                    failed += 1
                    continue
                
                # Process the message
                size = process_one_message(service, user_email, msg_id)
                
                if size > 0:
                    downloaded += 1
                    batch_downloaded += 1
                    total_size += size
                    downloaded_ids.add(msg_id)
                    
                    # Remove from failed list if successful
                    if msg_id in failed_messages:
                        failed_messages.remove(msg_id)
                    
                    print(f"   [{downloaded}/{total_messages}] {msg_id} ({size/1024:.1f} KB)")
                else:
                    failed += 1
                    if msg_id not in failed_messages:
                        failed_messages.append(msg_id)
                
                # Save checkpoint periodically
                if (downloaded + failed) % CHECKPOINT_INTERVAL == 0:
                    state['downloaded_ids'] = list(downloaded_ids)
                    state['failed_messages'] = failed_messages
                    state['checkpoint_page_token'] = page_token
                    state['total_processed'] = total_processed + downloaded + failed
                    save_state(user_email, state)
                    print(f"💾 Checkpoint saved at {downloaded + failed} messages")
                
                # Apply batch delay if configured
                if batch_downloaded >= BATCH_SIZE:
                    print(f"   ⏸️ Batch limit reached, pausing for {BATCH_DELAY} seconds...")
                    time.sleep(BATCH_DELAY)
                    batch_downloaded = 0
                
                # Check max messages limit
                if MAX_MSGS and downloaded >= MAX_MSGS:
                    print(f"📊 Reached max messages limit ({MAX_MSGS})")
                    break
            
            # Check if we should continue to next page
            if not next_page_token:
                break
                
            if MAX_MSGS and downloaded >= MAX_MSGS:
                break
            
            page_token = next_page_token
            print(f"📄 Moving to next page...")
        
        # Final state save
        state['downloaded_ids'] = list(downloaded_ids)
        state['failed_messages'] = failed_messages
        state['checkpoint_page_token'] = None  # Clear checkpoint
        state['total_processed'] = total_processed + downloaded + failed
        save_state(user_email, state)
        
        # Report results
        size_mb = total_size / (1024 * 1024)
        print(f"\n✅ User backup complete: {user_email}")
        print(f"   Downloaded: {downloaded} emails ({size_mb:.2f} MB)")
        print(f"   Failed: {failed}")
        print(f"   Total in state: {len(downloaded_ids)}")
        
        return {"downloaded": downloaded, "failed": failed, "size_mb": size_mb}
        
    except HttpError as e:
        if e.resp.status == 403:
            print(f"⚠️ No Gmail access for {user_email}")
        else:
            print(f"❌ Error accessing Gmail for {user_email}: {e}")
        
        # Save state even on error
        state['downloaded_ids'] = list(downloaded_ids)
        state['failed_messages'] = failed_messages
        state['checkpoint_page_token'] = page_token if 'page_token' in locals() else None
        state['total_processed'] = total_processed + downloaded if 'downloaded' in locals() else total_processed
        save_state(user_email, state)
        
        return {"downloaded": 0, "failed": 0, "size_mb": 0}
    except Exception as e:
        print(f"❌ Unexpected error for {user_email}: {e}")
        
        # Save state
        if 'downloaded_ids' in locals():
            state['downloaded_ids'] = list(downloaded_ids)
        if 'failed_messages' in locals():
            state['failed_messages'] = failed_messages
        save_state(user_email, state)
        
        return {"downloaded": 0, "failed": 0, "size_mb": 0}

def backup_single_user(email: str):
    """Backup emails for a specific user (for testing)"""
    print(f"\n🎯 Single user backup: {email}")
    
    # Initialize search index if enabled
    if INDEX_EMAILS:
        init_email_index()
    
    result = backup_user_emails(email)
    
    downloaded = result.get("downloaded", 0)
    failed = result.get("failed", 0)
    
    if failed > 0:
        print(f"\n⚠️ {failed} messages failed to download.")
        print(f"   Run again to continue.")
    else:
        print(f"✅ Backup complete for {email}!")

    return {"downloaded": downloaded, "failed": failed}

def main():
    """Main backup process with search functionality"""
    
    # Check command-line arguments
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] in ['search', '--search', '-s']:
            init_email_index()
            interactive_search()
            return
        elif sys.argv[1] in ['rebuild-index', '--rebuild-index', '-r']:
            # Initialize Dropbox connection for rebuild
            init_email_index()
            rebuild_index_from_dropbox()
            return
        elif sys.argv[1] in ['help', '--help', '-h']:
            print("""
Gmail to Dropbox Backup with Search

Usage:
  python backup.py              # Run backup
  python backup.py search       # Search emails
  python backup.py rebuild-index # Rebuild search index from Dropbox
  python backup.py help         # Show this help
            """)
            return
    
    # Regular backup mode
    print("\n" + "="*60)
    print("🚀 Gmail to Dropbox Team Folder Backup")
    print(f"🗂 Destination: {DROPBOX_TEAM_FOLDER}")
    if DROPBOX_TEAM_NAMESPACE:
        print(f"🔗 Team Folder ID: {DROPBOX_TEAM_NAMESPACE}")
        print(f"✅ Using centralized team folder (not personal folders)")
    print(f"📅 Mode: {BACKUP_MODE.upper()}")
    if BACKUP_MODE == "full":
        print(f"   Starting from: {EARLIEST_DATE if EARLIEST_DATE != '2000-01-01' else 'Beginning of time'}")
    
    # Check Dropbox connection type
    if os.getenv("DROPBOX_REFRESH_TOKEN"):
        print(f"🔐 Using refresh token (permanent access)")
    else:
        print(f"⚠️ Using regular token (expires after ~4 hours)")
    
    print("="*60)
    
    # Initialize search index if enabled
    if INDEX_EMAILS:
        init_email_index()
    
    # Get list of users
    try:
        directory = admin_directory()
        
        # Get all users - we'll filter by domain after
        request = directory.users().list(
            customer='my_customer',
            maxResults=500,
            orderBy='email'
        )
        
        all_users = []
        while request:
            result = request.execute()
            users = result.get('users', [])
            all_users.extend(users)
            
            request = directory.users().list_next(request, result)
        
        # Filter to primary emails only
        user_emails = []
        for user in all_users:
            email = user.get('primaryEmail', '').lower()
            if email:
                # Filter by domain if specified
                if USER_DOMAIN_FILTER:
                    if email.endswith(f"@{USER_DOMAIN_FILTER}"):
                        # Apply include filter if specified
                        if INCLUDE_ONLY:
                            if any(inc in email for inc in INCLUDE_ONLY):
                                user_emails.append(email)
                        else:
                            user_emails.append(email)
                else:
                    # No domain filter, just apply include filter
                    if INCLUDE_ONLY:
                        if any(inc in email for inc in INCLUDE_ONLY):
                            user_emails.append(email)
                    else:
                        user_emails.append(email)
        
        # Apply max users limit if set
        if MAX_USERS > 0:
            user_emails = user_emails[:MAX_USERS]
        
        print(f"\n📊 Found {len(user_emails)} users to backup")
        if INCLUDE_ONLY:
            print(f"   Filtered to: {', '.join(INCLUDE_ONLY)}")
        if MAX_USERS:
            print(f"   Limited to first {MAX_USERS} users")
        
        for email in user_emails:
            print(f"   • {email}")
        
        print("\n" + "="*60)
        
        # Process users based on concurrency setting
        total_downloaded = 0
        total_failed = 0
        total_size_mb = 0
        successful_users = []
        failed_users = []
        
        if CONCURRENCY > 1:
            # Parallel processing
            print(f"🚀 Processing users in parallel (max {CONCURRENCY} concurrent)")
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
                future_to_email = {
                    executor.submit(backup_user_emails, email): email
                    for email in user_emails
                }
                
                for future in as_completed(future_to_email):
                    email = future_to_email[future]
                    try:
                        result = future.result()
                        total_downloaded += result['downloaded']
                        total_failed += result['failed']
                        total_size_mb += result.get('size_mb', 0)
                        if result['downloaded'] > 0:
                            successful_users.append(email)
                        else:
                            failed_users.append(email)
                    except Exception as e:
                        print(f"❌ Error processing {email}: {e}")
                        failed_users.append(email)
        else:
            # Sequential processing (default)
            for i, email in enumerate(user_emails, 1):
                print(f"\n[{i}/{len(user_emails)}] Processing {email}...")
                
                result = backup_user_emails(email)
                total_downloaded += result['downloaded']
                total_failed += result['failed']
                total_size_mb += result.get('size_mb', 0)
                
                if result['downloaded'] > 0:
                    successful_users.append(email)
                elif result['failed'] == 0:
                    print(f"   ℹ️ No new emails to backup")
                else:
                    failed_users.append(email)
                
                # Small delay between users to be respectful
                if i < len(user_emails):
                    time.sleep(2)
        
        # Final summary
        print("\n" + "="*60)
        print("📊 BACKUP SUMMARY")
        print("="*60)
        print(f"✅ Successful users: {len(successful_users)}")
        for user in successful_users:
            print(f"   • {user}")
        
        if failed_users:
            print(f"\n⚠️ Failed users: {len(failed_users)}")
            for user in failed_users:
                print(f"   • {user}")
        
        print(f"\n📈 Total Statistics:")
        print(f"   Emails downloaded: {total_downloaded:,}")
        print(f"   Emails failed: {total_failed:,}")
        print(f"   Total size: {total_size_mb:.2f} MB")
        print(f"   Success rate: {(total_downloaded/(total_downloaded+total_failed)*100) if (total_downloaded+total_failed) > 0 else 0:.1f}%")
        
        # Search index summary
        if INDEX_EMAILS and INDEX_DB.exists():
            conn = sqlite3.connect(INDEX_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM email_index")
            indexed_count = cursor.fetchone()[0]
            conn.close()
            print(f"   Emails indexed: {indexed_count:,}")
        
        print("\n✅ Backup process complete!")
        print(f"🗂 Location: Team Folder - {DROPBOX_TEAM_FOLDER}")
        if BACKUP_MODE == "full":
            print("💡 Next steps:")
            print("   1. Switch to BACKUP_MODE=incremental in .env")
            print("   2. Schedule daily incremental backups")
            print("   3. Grant team members access to their subfolders as needed")
            print("   4. Use 'python backup.py search' to search backed-up emails")
        else:
            print("💡 Next steps:")
            print("   1. Schedule this script to run daily for incremental backups")
            print("   2. Use 'python backup.py search' to search backed-up emails")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()