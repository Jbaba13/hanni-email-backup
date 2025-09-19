#!/usr/bin/env python3
"""
Gmail -> Dropbox Team Folder Backup with Search & Retrieval
- Backs up all emails to centralized team folder: /Hanni Email Backups/
- Creates subfolders for each user: /Hanni Email Backups/user@domain.com/
- Admin controls all backups, can grant read-only access per user
- Uses Google Workspace Domain-Wide Delegation for Gmail access
- Indexes all emails for fast search and retrieval

Usage:
  1) Set .env file with configuration
  2) Backup mode: python -u backup.py
  3) Search mode: python backup.py search

Search Features:
- Search by sender, subject, date range, attachments
- Quick retrieval of specific emails
- Export search results to CSV
- Download individual emails from backup

# Search Configuration
INDEX_EMAILS=1                      # Enable email indexing for search

Sample .env configuration for large-scale backups:
--------------------------------------------------
# Google Workspace
GOOGLE_DELEGATED_ADMIN=jennie@heyhanni.com
GOOGLE_SCOPES=https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/admin.directory.user.readonly
GOOGLE_SA_JSON=./service_account.json
USER_DOMAIN_FILTER=heyhanni.com

# Dropbox Business (Team app)
DROPBOX_TEAM_TOKEN=sl.u.your_token_here
DROPBOX_TEAM_NAMESPACE=12777917905  # Hanni Email Backups folder ID

# Backup Configuration
BACKUP_MODE=full                    # 'full' for initial backup, 'incremental' for daily
EARLIEST_DATE=2020-01-01            # For full backups, how far back to go
START_DATE=2024-01-01               # For incremental backups
USE_INCREMENTAL=1                   # Use saved state to resume

# Rate Limiting (CRITICAL for large backups)
RATE_LIMIT_DELAY=0.2                # Seconds between API calls (0.2 = 5 calls/second)
BATCH_SIZE=50                       # Process emails in batches
BATCH_DELAY=10                      # Seconds to pause between batches
CHECKPOINT_INTERVAL=100             # Save progress every N messages
AUTO_RESUME=1                       # Auto-resume on rate limit errors
MAX_RETRIES=20                      # Max retries for rate limit errors

# Optional: Slow down during business hours
BUSINESS_HOURS_SLOWDOWN=1           # Enable business hours throttling
BUSINESS_START=9                    # 9 AM
BUSINESS_END=17                     # 5 PM  
BUSINESS_HOURS_DELAY=0.5            # Slower rate during business hours

# Processing limits
MAX_USERS=0                         # 0 = all users
MAX_MESSAGES_PER_USER=0             # 0 = all messages
CONCURRENCY=1                       # Keep at 1 for large backups
PAGE_SIZE=500                       # Messages per page (max 500)

# Specific users (optional)
INCLUDE_ONLY_EMAILS=jennie@heyhanni.com  # Comma-separated, or leave blank for all

# Search Index
INDEX_EMAILS=1                      # Enable email indexing for search (1=yes, 0=no)

# Testing
DRY_RUN=0                           # Set to 1 to test without uploading

Requirements (pip install):
---------------------------
google-api-python-client==2.108.0
google-auth==2.23.4
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
dropbox==11.36.2
python-dotenv==1.0.0
tenacity==8.2.3
requests==2.31.0
certifi==2023.11.17

Search Mode Usage:
------------------
python backup.py search              # Interactive search
python backup.py rebuild-index       # Rebuild index from Dropbox
"""

import base64
import datetime as dt
import json
import os
import re
import traceback
import ssl
import socket
import urllib3
import time
import sqlite3
import email
from email import policy
from email.parser import BytesParser
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ------------------------------------------------------------------
# SSL Configuration - Fix SSL issues with Dropbox
# ------------------------------------------------------------------
# Force disable SSL verification to bypass corporate proxy/firewall issues
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
assert DROPBOX_TEAM_TOKEN, "DROPBOX_TEAM_TOKEN missing in .env"

print(f"📁 Using team folder: {DROPBOX_TEAM_FOLDER}")
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
# Dropbox Client Setup (FIXED)
# -------------------------
try:
    # Test if the token is valid first
    from dropbox import Dropbox, DropboxTeam
    
    # Check if this is a team token or personal token
    is_team_token = False
    dbx = None
    
    try:
        # First try as a team token
        dbx_team = DropboxTeam(DROPBOX_TEAM_TOKEN)
        # Test the token by making a simple API call
        dbx_team.team_get_info()
        is_team_token = True
        print(f"✅ Connected to Dropbox Business (Team Token)")
        
        # Try to get the admin member for uploads
        try:
            members = dbx_team.team_members_list_v2(limit=500)
            admin_member_id = None
            
            for member in members.members:
                if member.profile.email.lower() == DELEGATED_ADMIN.lower():
                    admin_member_id = member.profile.team_member_id
                    print(f"✅ Admin member ID found: {member.profile.email}")
                    break
            
            if admin_member_id:
                # Create a user-specific client for the admin
                dbx_base = dbx_team.as_user(admin_member_id)
                
                # Use the team folder namespace for all operations
                if DROPBOX_TEAM_NAMESPACE:
                    from dropbox import common
                    path_root = common.PathRoot.namespace_id(DROPBOX_TEAM_NAMESPACE)
                    dbx = dbx_base.with_path_root(path_root)
                    print(f"✅ Using team folder namespace: {DROPBOX_TEAM_NAMESPACE}")
                    print(f"📁 All uploads will go to team folder: {DROPBOX_TEAM_FOLDER}")
                else:
                    dbx = dbx_base
                    print(f"⚠️  No namespace ID, using regular folder access")
            else:
                raise Exception("Admin member not found in team")
                
        except Exception as e:
            print(f"⚠️  Could not get admin member access: {e}")
            # Create a regular Dropbox client with the team token
            dbx_regular = Dropbox(DROPBOX_TEAM_TOKEN)
            
            if DROPBOX_TEAM_NAMESPACE:
                # Set the namespace root for the regular client
                from dropbox import common
                path_root = common.PathRoot.namespace_id(DROPBOX_TEAM_NAMESPACE)
                dbx = dbx_regular.with_path_root(path_root)
                print(f"✅ Using regular Dropbox client with team folder namespace")
            else:
                # Use regular client without namespace
                dbx = dbx_regular
                print(f"✅ Using regular Dropbox client (no namespace)")
    
    except AuthError as auth_err:
        # Not a team token or invalid team token, try as personal token
        print(f"⚠️  Not a team token or invalid team token: {str(auth_err)[:100]}")
        
        try:
            # Try as a personal/app token
            dbx = Dropbox(DROPBOX_TEAM_TOKEN)
            # Test the token
            dbx.users_get_current_account()
            print(f"✅ Connected to Dropbox (Personal/App Token)")
            
            if DROPBOX_TEAM_NAMESPACE:
                # Try to use namespace with personal token
                from dropbox import common
                path_root = common.PathRoot.namespace_id(DROPBOX_TEAM_NAMESPACE)
                dbx = dbx.with_path_root(path_root)
                print(f"✅ Using namespace with personal token")
                
        except AuthError as auth_err:
            print(f"\n" + "="*60)
            print(f"❌ DROPBOX TOKEN ERROR")
            print(f"="*60)
            print(f"The Dropbox access token is invalid or expired.")
            print(f"\nError details: {str(auth_err)[:200]}")
            print(f"\n📝 TO FIX THIS:")
            print(f"1. Go to https://www.dropbox.com/developers/apps")
            print(f"2. Select your app: 'Company Email Backup'")
            print(f"3. Go to Settings → OAuth 2 section")
            print(f"4. Click 'Generate' under 'Generated access token'")
            print(f"5. Copy the NEW token (should be ~150 characters)")
            print(f"6. Update DROPBOX_TEAM_TOKEN in your .env file")
            print(f"\n💡 Current token length: {len(DROPBOX_TEAM_TOKEN)} characters")
            print(f"   (Normal tokens are ~150 characters)")
            print(f"\n⚠️  Make sure you're using the correct token type:")
            print(f"   - For Team Folders: Use a Dropbox Business API token")
            print(f"   - For Personal: Use a regular Dropbox API token")
            print(f"="*60)
            dbx = None
            sys.exit(1)
        
except Exception as e:
    print(f"\n" + "="*60)
    print(f"❌ DROPBOX CONNECTION FAILED")
    print(f"="*60)
    print(f"Error: {str(e)[:200]}")
    print(f"\nPlease check:")
    print(f"1. Your Dropbox token is valid")
    print(f"2. Your internet connection is working")
    print(f"3. Dropbox API is accessible")
    print(f"="*60)
    dbx = None
    sys.exit(1)

def create_user_folder(user_email: str) -> bool:
    """Create user subfolder in team folder if it doesn't exist"""
    if not dbx:
        print(f"⚠️  No Dropbox client available for folder creation")
        return True  # Continue anyway
        
    try:
        # When using namespace root, paths are relative to the team folder
        if DROPBOX_TEAM_NAMESPACE:
            folder_path = f"/{user_email}"  # Relative to team folder namespace
        else:
            folder_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}"  # Full path
        
        try:
            # Check if the client has the files_create_folder_v2 method
            if hasattr(dbx, 'files_create_folder_v2'):
                dbx.files_create_folder_v2(folder_path)
                print(f"✅ Created folder: {folder_path}")
            else:
                print(f"⚠️  Client doesn't support folder creation, will create during upload")
                
        except ApiError as e:
            error_str = str(e)
            if "conflict" in error_str.lower() or "already_exists" in error_str.lower():
                print(f"📁 Folder already exists: {folder_path}")
            elif "no_write_permission" in error_str.lower():
                print(f"⚠️  No write permission to team folder. Folder might be created automatically during upload.")
            else:
                print(f"⚠️  Could not create folder: {error_str[:200]}")
        except Exception as e:
            print(f"⚠️  Folder creation skipped: {str(e)[:100]}")
        
        return True
        
    except Exception as e:
        print(f"⚠️  Error with folder for {user_email}: {str(e)[:100]}")
        return True  # Continue anyway, upload might create folders automatically

@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(10))
def dropbox_upload_to_team_folder(user_email: str, path: str, data: bytes):
    """Upload file to team folder (centralized backup location)"""
    
    # Check if we have a valid Dropbox client
    if not dbx:
        print(f"❌ No valid Dropbox client available. Check your token permissions.")
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
            # Upload to team folder
            result = dbx.files_upload(
                data,
                team_path,
                mode=WriteMode("add"),
                autorename=True,
                mute=True
            )
            
            if attempt > 0:
                print(f"✅ Upload successful after {attempt + 1} attempts")
            
            return True
            
        except (ssl.SSLError, socket.error, ConnectionError, TimeoutError) as e:
            if attempt < 2:
                print(f"⚠️  SSL/Network error (attempt {attempt + 1}/3), retrying...")
                time.sleep(2 ** attempt)
            else:
                print(f"⚠️  SSL/Network error after 3 attempts")
                return False
                
        except AuthError as e:
            # Authentication error - token is invalid
            print(f"\n" + "="*60)
            print(f"❌ AUTHENTICATION ERROR - TOKEN INVALID")
            print(f"="*60)
            print(f"Your Dropbox token is invalid or expired!")
            print(f"\n🔧 TO GET A NEW TOKEN:")
            print(f"1. Go to: https://www.dropbox.com/developers/apps")
            print(f"2. Click on your app")
            print(f"3. Go to Settings tab")
            print(f"4. Scroll to 'OAuth 2' section")
            print(f"5. Click 'Generate' under 'Generated access token'")
            print(f"6. Copy the ENTIRE token (about 150 characters)")
            print(f"7. Replace DROPBOX_TEAM_TOKEN in .env file")
            print(f"\n⚠️  Your current token has {len(DROPBOX_TEAM_TOKEN)} characters")
            print(f"   (Should be around 150 characters)")
            print(f"="*60)
            return False
            
        except ApiError as e:
            error_str = str(e).lower()
            if "conflict" in error_str or "already_exists" in error_str:
                # File already exists, skip silently
                return True
            elif "not_found" in error_str:
                # Parent folder doesn't exist, try to create it
                try:
                    # Create all parent folders
                    parent_parts = team_path.split('/')[:-1]
                    for i in range(2, len(parent_parts) + 1):
                        partial_path = '/'.join(parent_parts[:i])
                        try:
                            if hasattr(dbx, 'files_create_folder_v2'):
                                dbx.files_create_folder_v2(partial_path)
                        except:
                            pass  # Folder might already exist
                    
                    # Retry upload after creating folders
                    if attempt < 2:
                        time.sleep(1)
                        continue
                except:
                    pass
            elif "no_write_permission" in error_str:
                print(f"❌ No write permission to team folder. Check Dropbox permissions.")
                return False
                
            print(f"⚠️  Dropbox API error: {str(e)[:200]}")
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            else:
                return False
            
        except BadInputError as e:
            # This is usually a token/permission issue
            print(f"❌ Bad input error: {str(e)[:200]}")
            print(f"   Check that the team folder allows uploads")
            return False
            
        except AttributeError as e:
            # Handle the case where dbx doesn't have files_upload method
            print(f"❌ Client doesn't support file upload: {str(e)[:200]}")
            # Try the fallback upload method
            return upload_with_requests_fallback(user_email, path, data)
            
        except Exception as e:
            print(f"⚠️  Unexpected error: {str(e)[:200]}")
            if attempt < 2:
                time.sleep(2 ** attempt)
            else:
                return False
    
    return False

def upload_with_requests_fallback(user_email: str, path: str, data: bytes):
    """Fallback upload using requests library when SDK fails"""
    try:
        # Build proper path
        if DROPBOX_TEAM_NAMESPACE:
            # When using namespace, need to include it in headers
            full_path = f"/{user_email}/{path.strip('/')}"
            headers = {
                'Authorization': f'Bearer {DROPBOX_TEAM_TOKEN}',
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
                'Authorization': f'Bearer {DROPBOX_TEAM_TOKEN}',
                'Dropbox-API-Arg': json.dumps({
                    'path': full_path,
                    'mode': 'add',
                    'autorename': True,
                    'mute': True
                }),
                'Content-Type': 'application/octet-stream'
            }
        
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
            print(f"⭕️  File already exists (requests): {full_path}")
            return True
        else:
            print(f"❌ Upload failed (requests): {response.status_code} - {response.text[:200]}")
            return False
            
    except Exception as e:
        print(f"❌ Requests fallback failed: {e}")
        return False

# -------------------------
# State helpers
# -------------------------
def state_path(user_email: str) -> Path:
    safe = re.sub(r"[^a-zA-Z0-9._@+-]", "_", user_email)
    return STATE_DIR / f"{safe}.json"

def load_state(user_email: str) -> Dict:
    p = state_path(user_email)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}

def save_state(user_email: str, data: Dict):
    p = state_path(user_email)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")

# -------------------------
# Email Index Database
# -------------------------
INDEX_DB = BASE_DIR / "email_index.db"

def init_email_index():
    """Initialize SQLite database for email search index"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Create table for email metadata
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS email_index (
            id TEXT PRIMARY KEY,
            user_email TEXT NOT NULL,
            message_id TEXT NOT NULL,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            date INTEGER,
            date_str TEXT,
            has_attachments BOOLEAN,
            attachment_names TEXT,
            size_bytes INTEGER,
            dropbox_path TEXT,
            body_preview TEXT,
            labels TEXT,
            UNIQUE(user_email, message_id)
        )
    ''')
    
    # Create indexes for common searches
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
                body_preview = ""
        
        # Get Gmail labels if present
        labels = ""
        for header, value in msg.items():
            if header.lower() == 'x-gmail-labels':
                labels = value
                break
        
        return {
            'message_id': message_id,
            'subject': subject,
            'sender': sender,
            'recipients': recipients,
            'date_str': date_str,
            'has_attachments': has_attachments,
            'attachment_names': ', '.join(attachments),
            'body_preview': body_preview,
            'labels': labels,
            'size_bytes': len(raw_bytes)
        }
    except Exception as e:
        print(f"⚠️  Error parsing email metadata: {e}")
        return {}

def index_email(user_email: str, msg_id: str, raw_bytes: bytes, dropbox_path: str, timestamp_ms: int):
    """Add email to search index"""
    try:
        # Parse email metadata
        metadata = parse_email_metadata(raw_bytes)
        if not metadata:
            return
        
        # Connect to database
        conn = sqlite3.connect(INDEX_DB)
        cursor = conn.cursor()
        
        # Prepare data
        unique_id = f"{user_email}:{msg_id}"
        date_dt = dt.datetime.fromtimestamp(timestamp_ms / 1000.0, dt.timezone.utc)
        
        # Insert or update index
        cursor.execute('''
            INSERT OR REPLACE INTO email_index 
            (id, user_email, message_id, subject, sender, recipients, date, date_str,
             has_attachments, attachment_names, size_bytes, dropbox_path, body_preview, labels)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            unique_id,
            user_email,
            msg_id,
            metadata.get('subject', ''),
            metadata.get('sender', ''),
            metadata.get('recipients', ''),
            timestamp_ms,
            date_dt.isoformat(),
            metadata.get('has_attachments', False),
            metadata.get('attachment_names', ''),
            metadata.get('size_bytes', 0),
            dropbox_path,
            metadata.get('body_preview', ''),
            metadata.get('labels', '')
        ))
        
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"⚠️  Error indexing email: {e}")

# -------------------------
# Search Functions
# -------------------------
def search_emails(query: str = "", user_email: str = None, sender: str = None, 
                  subject: str = None, start_date: str = None, end_date: str = None,
                  has_attachments: bool = None, limit: int = 100) -> List[Dict]:
    """
    Search indexed emails with various filters
    
    Args:
        query: General search term (searches subject, sender, recipients, body)
        user_email: Filter by specific user
        sender: Filter by sender email
        subject: Filter by subject line
        start_date: ISO format date string (YYYY-MM-DD)
        end_date: ISO format date string (YYYY-MM-DD)
        has_attachments: Filter by attachment presence
        limit: Maximum results to return
    
    Returns:
        List of matching email records
    """
    conn = sqlite3.connect(INDEX_DB)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    cursor = conn.cursor()
    
    # Build query
    conditions = []
    params = []
    
    if query:
        conditions.append('''
            (subject LIKE ? OR sender LIKE ? OR recipients LIKE ? OR body_preview LIKE ?)
        ''')
        query_param = f"%{query}%"
        params.extend([query_param] * 4)
    
    if user_email:
        conditions.append("user_email = ?")
        params.append(user_email)
    
    if sender:
        conditions.append("sender LIKE ?")
        params.append(f"%{sender}%")
    
    if subject:
        conditions.append("subject LIKE ?")
        params.append(f"%{subject}%")
    
    if start_date:
        start_ts = int(dt.datetime.fromisoformat(start_date).timestamp() * 1000)
        conditions.append("date >= ?")
        params.append(start_ts)
    
    if end_date:
        end_ts = int(dt.datetime.fromisoformat(end_date).timestamp() * 1000)
        conditions.append("date <= ?")
        params.append(end_ts)
    
    if has_attachments is not None:
        conditions.append("has_attachments = ?")
        params.append(has_attachments)
    
    # Construct final query
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    query_sql = f'''
        SELECT * FROM email_index 
        WHERE {where_clause}
        ORDER BY date DESC
        LIMIT ?
    '''
    params.append(limit)
    
    # Execute search
    cursor.execute(query_sql, params)
    results = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    return results

def download_email_from_index(email_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Download a specific email from Dropbox using index
    
    Args:
        email_id: The unique ID from the index (format: user@email.com:message_id)
    
    Returns:
        Tuple of (email_bytes, filename) or (None, None) if not found
    """
    if not dbx:
        print("❌ No Dropbox connection available")
        return None, None
    
    # Get email info from index
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM email_index WHERE id = ?", (email_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print(f"❌ Email not found in index: {email_id}")
        return None, None
    
    # Download from Dropbox
    try:
        dropbox_path = row[11]  # dropbox_path column
        
        # Download file
        metadata, response = dbx.files_download(dropbox_path)
        email_bytes = response.content
        
        # Generate filename from path
        filename = os.path.basename(dropbox_path)
        
        print(f"✅ Downloaded: {filename}")
        return email_bytes, filename
        
    except Exception as e:
        print(f"❌ Error downloading email: {e}")
        return None, None

def export_search_results(results: List[Dict], output_file: str = "search_results.csv"):
    """Export search results to CSV file"""
    if not results:
        print("No results to export")
        return
    
    # Write CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    
    print(f"✅ Exported {len(results)} results to {output_file}")

def print_search_results(results: List[Dict], verbose: bool = False):
    """Pretty print search results"""
    if not results:
        print("No emails found matching search criteria")
        return
    
    print(f"\n📧 Found {len(results)} matching emails:\n")
    print("-" * 80)
    
    for i, email in enumerate(results, 1):
        date = dt.datetime.fromtimestamp(email['date'] / 1000).strftime('%Y-%m-%d %H:%M')
        subject = email['subject'][:50] + "..." if len(email['subject']) > 50 else email['subject']
        sender = email['sender'][:30] + "..." if len(email['sender']) > 30 else email['sender']
        
        print(f"{i:3}. [{date}] {subject}")
        print(f"     From: {sender}")
        print(f"     User: {email['user_email']}")
        
        if email['has_attachments']:
            print(f"     📎 Attachments: {email['attachment_names'][:60]}...")
        
        if verbose and email['body_preview']:
            preview = email['body_preview'][:100].replace('\n', ' ')
            print(f"     Preview: {preview}...")
        
        print(f"     ID: {email['id']}")
        print("-" * 80)
    
    print(f"\n💡 To download an email, use: download_email_from_index('email_id')")

def rebuild_index_from_dropbox():
    """Rebuild search index by scanning all .eml files in Dropbox"""
    print("\n🔄 Rebuilding email search index from Dropbox...")
    
    if not dbx:
        print("❌ No Dropbox connection available")
        return
    
    # Initialize fresh database
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
                print(f"⚠️  Error indexing {file_entry.path_display}: {e}")
                continue
        
        print(f"\n✅ Index rebuilt successfully!")
        print(f"   Total emails indexed: {indexed_count}")
        
    except Exception as e:
        print(f"❌ Error rebuilding index: {e}")

def interactive_search():
    """Interactive command-line search interface"""
    print("\n" + "="*60)
    print("📧 Email Search & Retrieval System")
    print("="*60)
    
    # Show index statistics
    try:
        conn = sqlite3.connect(INDEX_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM email_index")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(DISTINCT user_email) FROM email_index")
        users = cursor.fetchone()[0]
        conn.close()
        print(f"\n📊 Index contains {total:,} emails from {users} users")
    except:
        print("\n⚠️  Index not found or empty. Run a backup first or rebuild index.")
    
    while True:
        print("\nSearch Options:")
        print("1. Quick search (all fields)")
        print("2. Search by sender")
        print("3. Search by subject")
        print("4. Search by date range")
        print("5. Search emails with attachments")
        print("6. Advanced search")
        print("7. Download email by ID")
        print("8. Export last search to CSV")
        print("9. Rebuild index from Dropbox")
        print("0. Exit search")
        
        choice = input("\nEnter choice (0-9): ").strip()
        
        if choice == '1':
            query = input("Enter search term: ").strip()
            results = search_emails(query=query)
            print_search_results(results)
            
        elif choice == '2':
            sender = input("Enter sender email/name: ").strip()
            results = search_emails(sender=sender)
            print_search_results(results)
            
        elif choice == '3':
            subject = input("Enter subject text: ").strip()
            results = search_emails(subject=subject)
            print_search_results(results)
            
        elif choice == '4':
            start = input("Enter start date (YYYY-MM-DD): ").strip()
            end = input("Enter end date (YYYY-MM-DD): ").strip()
            results = search_emails(start_date=start, end_date=end)
            print_search_results(results)
            
        elif choice == '5':
            results = search_emails(has_attachments=True)
            print_search_results(results)
            
        elif choice == '6':
            print("\nAdvanced Search (leave blank to skip)")
            query = input("General search term: ").strip() or None
            user = input("User email: ").strip() or None
            sender = input("Sender: ").strip() or None
            subject = input("Subject: ").strip() or None
            start = input("Start date (YYYY-MM-DD): ").strip() or None
            end = input("End date (YYYY-MM-DD): ").strip() or None
            attachments = input("Has attachments (y/n): ").strip().lower()
            has_attach = True if attachments == 'y' else False if attachments == 'n' else None
            
            results = search_emails(
                query=query, user_email=user, sender=sender,
                subject=subject, start_date=start, end_date=end,
                has_attachments=has_attach
            )
            print_search_results(results, verbose=True)
            
        elif choice == '7':
            email_id = input("Enter email ID: ").strip()
            email_bytes, filename = download_email_from_index(email_id)
            if email_bytes:
                save_path = input(f"Save as ({filename}): ").strip() or filename
                with open(save_path, 'wb') as f:
                    f.write(email_bytes)
                print(f"✅ Email saved to {save_path}")
                
        elif choice == '8':
            if 'results' in locals():
                filename = input("Export filename (search_results.csv): ").strip() or "search_results.csv"
                export_search_results(results, filename)
            else:
                print("No search results to export")
                
        elif choice == '9':
            confirm = input("Rebuild index from Dropbox? This may take a while (y/n): ").strip().lower()
            if confirm == 'y':
                rebuild_index_from_dropbox()
                
        elif choice == '0':
            break
        
        else:
            print("Invalid choice")

# -------------------------
# Rate Limiting & Quota Management
# -------------------------
class RateLimiter:
    """Intelligent rate limiter for Google API calls"""
    def __init__(self):
        self.last_call = 0
        self.calls_today = 0
        self.quota_reset = None
        self.consecutive_errors = 0
        
    def wait_if_needed(self):
        """Apply rate limiting based on configuration"""
        now = time.time()
        
        # Check if we're in business hours (for slower processing)
        if BUSINESS_HOURS_SLOWDOWN:
            current_hour = dt.datetime.now().hour
            if BUSINESS_START <= current_hour < BUSINESS_END:
                delay = BUSINESS_HOURS_DELAY
            else:
                delay = RATE_LIMIT_DELAY
        else:
            delay = RATE_LIMIT_DELAY
        
        # Apply minimum delay between calls
        elapsed = now - self.last_call
        if elapsed < delay:
            time.sleep(delay - elapsed)
        
        self.last_call = time.time()
        self.calls_today += 1
        
    def handle_rate_limit_error(self, retry_after=None):
        """Handle 429 rate limit errors with exponential backoff"""
        self.consecutive_errors += 1
        
        if retry_after:
            wait_time = retry_after
        else:
            # Exponential backoff: 1, 2, 4, 8, 16, 32, 64, 128, 256, 512 seconds
            wait_time = min(2 ** self.consecutive_errors, 512)
        
        print(f"⏳ Rate limited. Waiting {wait_time} seconds (attempt {self.consecutive_errors}/{MAX_RETRIES})")
        
        # Show countdown for long waits
        if wait_time > 10:
            for remaining in range(int(wait_time), 0, -10):
                print(f"   Resuming in {remaining} seconds...")
                time.sleep(min(10, remaining))
        else:
            time.sleep(wait_time)
        
        return self.consecutive_errors < MAX_RETRIES
        
    def reset_error_count(self):
        """Reset consecutive error count on successful call"""
        if self.consecutive_errors > 0:
            print(f"✅ Recovered from rate limiting after {self.consecutive_errors} retries")
        self.consecutive_errors = 0

rate_limiter = RateLimiter()

# -------------------------
# Users listing (Admin SDK)
# -------------------------
def list_users() -> List[str]:
    """List all users in the domain or use INCLUDE_ONLY if specified"""
    
    # If specific users are listed, just use those
    if INCLUDE_ONLY:
        print(f"📋 Using specified users from INCLUDE_ONLY_EMAILS")
        return [email for email in INCLUDE_ONLY if email]
    
    try:
        svc = admin_directory()
        users: List[str] = []
        page_token = None
        params = {"customer": "my_customer", "maxResults": 200, "orderBy": "email"}

        while True:
            if page_token:
                params["pageToken"] = page_token
            if USER_DOMAIN_FILTER:
                params["domain"] = USER_DOMAIN_FILTER

            resp = svc.users().list(**params).execute()
            for u in resp.get("users", []):
                if u.get("suspended"):
                    continue
                primary = u.get("primaryEmail")
                if primary:
                    users.append(primary)

            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        # Apply MAX_USERS limit if set
        if MAX_USERS and MAX_USERS > 0:
            users = users[:MAX_USERS]
            
        return users
        
    except Exception as e:
        print(f"⚠️  Could not list users via Admin SDK: {e}")
        if INCLUDE_ONLY:
            print(f"📋 Falling back to INCLUDE_ONLY_EMAILS")
            return [email for email in INCLUDE_ONLY if email]
        return []

# -------------------------
# Gmail listing & download
# -------------------------
def iso_to_date(iso_str: str) -> dt.datetime:
    if "T" in iso_str:
        return dt.datetime.fromisoformat(iso_str)
    return dt.datetime.fromisoformat(iso_str + "T00:00:00")

def gmail_query_after(iso_date: str) -> str:
    d = iso_to_date(iso_date)
    return f"after:{d.strftime('%Y/%m/%d')}"

def list_message_ids(service, user_id: str, query: Optional[str], page_size: int) -> List[str]:
    """List all message IDs matching the query (or ALL if query is None)"""
    ids: List[str] = []
    page_token = None
    pages_fetched = 0
    
    # Build params
    params = {
        "userId": user_id,
        "maxResults": page_size
    }
    
    # Only add query if provided (None means get ALL emails)
    if query:
        params["q"] = query
    
    while True:
        try:
            if page_token:
                params["pageToken"] = page_token
            
            # Apply rate limiting
            rate_limiter.wait_if_needed()
            
            req = service.users().messages().list(**params)
            resp = req.execute()
            
            # Reset error count on success
            rate_limiter.reset_error_count()
            
        except HttpError as e:
            if getattr(e, "resp", None) and e.resp.status == 429:
                # Rate limit error - use intelligent backoff
                retry_after = None
                if hasattr(e.resp, 'headers'):
                    retry_after = e.resp.headers.get('Retry-After')
                    if retry_after:
                        retry_after = int(retry_after)
                
                if AUTO_RESUME and rate_limiter.handle_rate_limit_error(retry_after):
                    continue
                else:
                    print(f"❌ Rate limit exceeded after {MAX_RETRIES} retries")
                    raise
            elif getattr(e, "resp", None) and e.resp.status in (500, 503):
                print(f"⚠️  Gmail API server error, waiting...")
                time.sleep(5)
                continue
            else:
                raise

        for m in resp.get("messages", []):
            ids.append(m["id"])
        
        pages_fetched += 1
        if pages_fetched % 10 == 0:
            print(f"   📄 Fetched {pages_fetched} pages, {len(ids)} messages so far...")
            
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
            
    return ids

@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(10))
def get_message_raw(service, user_id: str, msg_id: str) -> bytes:
    """Get raw email data including attachments"""
    try:
        # Apply rate limiting
        rate_limiter.wait_if_needed()
        
        msg = service.users().messages().get(userId=user_id, id=msg_id, format="raw").execute()
        
        # Reset error count on success
        rate_limiter.reset_error_count()
        
        raw = msg.get("raw")
        if not raw:
            return b""
        return base64.urlsafe_b64decode(raw.encode("utf-8"))
        
    except HttpError as e:
        if getattr(e, "resp", None) and e.resp.status == 429:
            # Rate limit error
            retry_after = None
            if hasattr(e.resp, 'headers'):
                retry_after = e.resp.headers.get('Retry-After')
                if retry_after:
                    retry_after = int(retry_after)
            
            if rate_limiter.handle_rate_limit_error(retry_after):
                raise  # Let retry decorator handle it
            else:
                print(f"❌ Giving up on message {msg_id} after rate limit retries")
                return b""
        else:
            raise

def parse_internal_date_ms(service, user_id: str, msg_id: str) -> int:
    """Get email timestamp"""
    try:
        # Apply rate limiting
        rate_limiter.wait_if_needed()
        
        meta = service.users().messages().get(userId=user_id, id=msg_id, format="metadata").execute()
        
        # Reset error count on success
        rate_limiter.reset_error_count()
        
        return int(meta.get("internalDate", "0"))
        
    except HttpError as e:
        if getattr(e, "resp", None) and e.resp.status == 429:
            # Rate limit error
            if rate_limiter.handle_rate_limit_error():
                # Retry
                return parse_internal_date_ms(service, user_id, msg_id)
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
            
        ts_ms = parse_internal_date_ms(service, "me", msg_id)
        subject_hint = extract_subject_hint(raw_bytes)
        dbx_path = make_dropbox_path(ts_ms, subject_hint, msg_id)
        
        if not DRY_RUN:
            # Upload to team folder
            if dropbox_upload_to_team_folder(user_email, dbx_path, raw_bytes):
                # Index the email for search (if enabled)
                if INDEX_EMAILS:
                    # Build the full Dropbox path for the index
                    if DROPBOX_TEAM_NAMESPACE:
                        full_dbx_path = f"/{user_email}{dbx_path}"
                    else:
                        full_dbx_path = f"{DROPBOX_TEAM_FOLDER}/{user_email}{dbx_path}"
                    
                    index_email(user_email, msg_id, raw_bytes, full_dbx_path, ts_ms)
            
        return ts_ms
        
    except Exception as e:
        print(f"[{user_email}] Failed to process message {msg_id}: {e}")
        return 0

def backup_user(user_email: str) -> Dict[str, int]:
    """Backup all emails for a specific user with intelligent rate limiting and checkpointing"""
    
    print(f"\n{'='*60}")
    print(f"📧 Starting backup for: {user_email}")
    print(f"{'='*60}")
    
    # Create user folder in team space
    create_user_folder(user_email)
    
    # Get Gmail service for this user
    service = gmail_client(user_email)
    
    # Load state (to resume from previous runs)
    st = load_state(user_email)
    
    # Check if we're resuming a previous backup
    if st.get("backup_in_progress"):
        print(f"📂 Resuming previous backup from message {st.get('messages_processed', 0)}")
        processed_ids = set(st.get("processed_message_ids", []))
    else:
        processed_ids = set()
        st["backup_in_progress"] = True
        st["backup_started"] = dt.datetime.now().isoformat()
        save_state(user_email, st)
    
    # Determine backup mode and query
    query = None
    if BACKUP_MODE == "full":
        # Full backup mode - get ALL emails or from earliest date
        if EARLIEST_DATE != "2000-01-01":
            query = gmail_query_after(EARLIEST_DATE)
            print(f"📅 FULL BACKUP MODE - Getting all emails from {EARLIEST_DATE}")
        else:
            # No query means ALL emails
            query = None
            print(f"📅 FULL BACKUP MODE - Getting ALL emails (no date filter)")
    else:
        # Incremental mode
        if USE_INCREMENTAL and "last_iso" in st:
            # Continue from where we left off
            after_iso = st.get("last_iso", START_DATE)
            query = gmail_query_after(after_iso)
            print(f"📅 INCREMENTAL MODE - Getting emails from {after_iso}")
        else:
            # First run in incremental mode - use START_DATE
            after_iso = START_DATE
            query = gmail_query_after(after_iso)
            print(f"📅 INCREMENTAL MODE (first run) - Getting emails from {after_iso}")

    # Get list of messages (or use cached list if resuming)
    if st.get("backup_in_progress") and "all_message_ids" in st:
        print(f"📋 Using cached message list from previous run")
        msg_ids = st["all_message_ids"]
        # Filter out already processed messages
        msg_ids = [mid for mid in msg_ids if mid not in processed_ids]
        print(f"📊 {len(processed_ids)} already processed, {len(msg_ids)} remaining")
    else:
        print(f"🔍 Fetching message list (this may take a while for large mailboxes)...")
        start_fetch = time.time()
        msg_ids = list_message_ids(service, "me", query, PAGE_SIZE)
        fetch_duration = time.time() - start_fetch
        print(f"📊 Found {len(msg_ids)} messages in {fetch_duration/60:.1f} minutes")
        
        # Cache the message list for resume capability
        st["all_message_ids"] = msg_ids
        st["total_messages"] = len(msg_ids)
        save_state(user_email, st)

    total_messages = st.get("total_messages", len(msg_ids))

    # Warning for large backups
    if total_messages > 1000:
        print(f"⚠️  Large backup detected: {total_messages} total emails")
        estimated_hours = (total_messages * (RATE_LIMIT_DELAY + 0.5)) / 3600
        print(f"⏱️  Estimated time: {estimated_hours:.1f} hours at current rate limit settings")
        print(f"💡 Tip: This backup can be safely interrupted and resumed")
        if total_messages > 10000:
            print(f"🌙 Consider running overnight or over a weekend")

    if MAX_MSGS and len(msg_ids) > MAX_MSGS:
        msg_ids = msg_ids[:MAX_MSGS]
        print(f"📉 Limited to {MAX_MSGS} messages per user setting")
        
    print(f"⚙️  Processing {len(msg_ids)} messages in batches of {BATCH_SIZE}")
    print(f"   Rate limit: {RATE_LIMIT_DELAY}s/call, checkpoint every {CHECKPOINT_INTERVAL} messages")

    downloaded = st.get("messages_downloaded", 0)
    failed = st.get("messages_failed", 0)
    latest_ts = st.get("last_ts_ms", 0)
    messages_processed = st.get("messages_processed", 0)

    if not msg_ids:
        # Backup complete, clean up state
        if st.get("backup_in_progress"):
            st["backup_in_progress"] = False
            st["backup_completed"] = dt.datetime.now().isoformat()
            save_state(user_email, st)
        print(f"✅ No new messages to backup for {user_email}")
        return {"downloaded": downloaded, "failed": failed}

    # Process messages in batches
    start_time = time.time()
    batch_count = 0
    
    try:
        for batch_start in range(0, len(msg_ids), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(msg_ids))
            batch = msg_ids[batch_start:batch_end]
            batch_count += 1
            
            print(f"\n📦 Processing batch {batch_count} ({batch_start+1}-{batch_end} of {len(msg_ids)})")
            
            # Process batch with single threading for better rate limit control
            for i, msg_id in enumerate(batch, 1):
                try:
                    # Skip if already processed
                    if msg_id in processed_ids:
                        continue
                    
                    # Process the message
                    ts_ms = process_one_message(service, user_email, msg_id)
                    
                    if ts_ms:
                        if ts_ms > latest_ts:
                            latest_ts = ts_ms
                        downloaded += 1
                        processed_ids.add(msg_id)
                    else:
                        failed += 1
                    
                    messages_processed += 1
                    
                    # Checkpoint progress periodically
                    if messages_processed % CHECKPOINT_INTERVAL == 0:
                        print(f"💾 Checkpoint: {messages_processed}/{total_messages} messages ({downloaded} success, {failed} failed)")
                        
                        # Save checkpoint
                        st["messages_processed"] = messages_processed
                        st["messages_downloaded"] = downloaded
                        st["messages_failed"] = failed
                        st["last_ts_ms"] = latest_ts
                        st["processed_message_ids"] = list(processed_ids)[-1000:]  # Keep last 1000 for resume
                        
                        # Calculate and show progress
                        progress_pct = (messages_processed / total_messages) * 100
                        elapsed = time.time() - start_time
                        rate = messages_processed / elapsed if elapsed > 0 else 0
                        eta = (total_messages - messages_processed) / rate if rate > 0 else 0
                        
                        print(f"📊 Progress: {progress_pct:.1f}% | Rate: {rate:.1f} msgs/sec | ETA: {eta/60:.1f} minutes")
                        
                        save_state(user_email, st)
                    
                    # Show progress every 10 messages
                    if messages_processed % 10 == 0:
                        print(f"   Processing... {messages_processed}/{total_messages} ({(messages_processed/total_messages)*100:.1f}%)", end='\r')
                        
                except Exception as e:
                    print(f"\n⚠️  Error processing message {msg_id}: {str(e)[:100]}")
                    failed += 1
                    continue
            
            # Delay between batches to avoid rate limits
            if batch_end < len(msg_ids):
                print(f"⏸️  Batch complete. Pausing {BATCH_DELAY} seconds before next batch...")
                time.sleep(BATCH_DELAY)
                
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Backup interrupted by user. Progress saved.")
        print(f"   Processed: {messages_processed}/{total_messages} messages")
        print(f"   Run the script again to resume from this point.")
    except Exception as e:
        print(f"\n❌ Backup error: {e}")
        print(f"   Progress saved. You can resume by running the script again.")
    
    # Calculate final stats
    duration = time.time() - start_time
    
    # Save final state
    st["messages_processed"] = messages_processed
    st["messages_downloaded"] = downloaded
    st["messages_failed"] = failed
    st["last_ts_ms"] = latest_ts
    
    # Mark backup as complete if all messages processed
    if messages_processed >= len(msg_ids):
        st["backup_in_progress"] = False
        st["backup_completed"] = dt.datetime.now().isoformat()
        if BACKUP_MODE == "incremental" and latest_ts:
            st["last_iso"] = dt.datetime.fromtimestamp(latest_ts / 1000.0, dt.timezone.utc).strftime("%Y-%m-%d")
        # Clean up large cached data
        st.pop("all_message_ids", None)
        st.pop("processed_message_ids", None)
    
    save_state(user_email, st)
    
    print(f"\n⏱️  Session took {duration/60:.1f} minutes")
    print(f"📈 Session stats: {downloaded} downloaded, {failed} failed")
    
    if st.get("backup_in_progress"):
        print(f"🔄 Backup not complete. Run again to continue.")
    else:
        print(f"✅ Backup complete for {user_email}!")

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
    print(f"📁 Destination: {DROPBOX_TEAM_FOLDER}")
    if DROPBOX_TEAM_NAMESPACE:
        print(f"🔗 Team Folder ID: {DROPBOX_TEAM_NAMESPACE}")
        print(f"✅ Using centralized team folder (not personal folders)")
    print(f"📅 Mode: {BACKUP_MODE.upper()}")
    if BACKUP_MODE == "full":
        print(f"   Starting from: {EARLIEST_DATE if EARLIEST_DATE != '2000-01-01' else 'Beginning of time'}")
    print("\n⚙️  Rate Limiting Configuration:")
    print(f"   API call delay: {RATE_LIMIT_DELAY}s")
    print(f"   Batch size: {BATCH_SIZE} messages")
    print(f"   Batch delay: {BATCH_DELAY}s")
    print(f"   Checkpoint interval: {CHECKPOINT_INTERVAL} messages")
    if BUSINESS_HOURS_SLOWDOWN:
        print(f"   Business hours slowdown: {BUSINESS_START}:00-{BUSINESS_END}:00 ({BUSINESS_HOURS_DELAY}s delay)")
    if INDEX_EMAILS:
        print(f"🔍 Search indexing: ENABLED")
    else:
        print(f"🔍 Search indexing: DISABLED (set INDEX_EMAILS=1 to enable)")
    print("="*60 + "\n")
    
    # Initialize email index database (if enabled)
    if INDEX_EMAILS:
        init_email_index()
    
    # Get list of users to backup
    users = list_users()
    
    print(f"👥 Found {len(users)} user(s) to backup")
    if MAX_USERS:
        print(f"   (limited by MAX_USERS={MAX_USERS})")
    
    if not users:
        print("❌ No users found to backup")
        print("   Check INCLUDE_ONLY_EMAILS in .env file")
        return

    # Check for any in-progress backups
    users_in_progress = []
    for user_email in users:
        st = load_state(user_email)
        if st.get("backup_in_progress"):
            users_in_progress.append(user_email)
    
    if users_in_progress:
        print(f"\n📂 Found {len(users_in_progress)} in-progress backup(s):")
        for user in users_in_progress:
            st = load_state(user)
            processed = st.get("messages_processed", 0)
            total = st.get("total_messages", 0)
            if total > 0:
                print(f"   - {user}: {processed}/{total} messages ({(processed/total)*100:.1f}%)")
            else:
                print(f"   - {user}: backup in progress")

    # Summary statistics
    total_downloaded = 0
    total_failed = 0
    successful_users = 0
    failed_users = []
    
    # Track overall start time
    overall_start = time.time()
    
    # Backup each user
    for i, user_email in enumerate(users, 1):
        try:
            print(f"\n{'='*60}")
            print(f"[{i}/{len(users)}] USER: {user_email}")
            print(f"{'='*60}")
            
            user_start = time.time()
            stats = backup_user(user_email)
            user_duration = time.time() - user_start
            
            total_downloaded += stats["downloaded"]
            total_failed += stats.get("failed", 0)
            
            if stats["downloaded"] > 0:
                successful_users += 1
                
            print(f"⏱️  User backup session took {user_duration/60:.1f} minutes")
            
            # Check if this user's backup is complete
            st = load_state(user_email)
            if st.get("backup_in_progress"):
                print(f"🔄 Backup for {user_email} is not complete. Run again to continue.")
            else:
                print(f"✅ Backup for {user_email} is complete!")
                
        except Exception as e:
            print(f"❌ Failed to backup {user_email}: {e}")
            traceback.print_exc()
            failed_users.append(user_email)
            continue
    
    # Overall duration
    overall_duration = time.time() - overall_start
    
    # Final summary
    print("\n" + "="*60)
    print("📊 BACKUP SESSION COMPLETE")
    print("="*60)
    print(f"⏱️  Total session time: {overall_duration/60:.1f} minutes")
    print(f"✅ Successful users: {successful_users}/{len(users)}")
    if failed_users:
        print(f"❌ Failed users: {', '.join(failed_users)}")
    print(f"📧 Total emails uploaded: {total_downloaded}")
    if total_failed:
        print(f"⚠️  Failed uploads: {total_failed}")
    print(f"📁 All backups saved to team folder:")
    print(f"   Location: {DROPBOX_TEAM_FOLDER}/[user-email]/")
    if DROPBOX_TEAM_NAMESPACE:
        print(f"   Team Folder ID: {DROPBOX_TEAM_NAMESPACE}")
        print(f"   ✅ This is a centralized team folder (not personal space)")
    
    # Search index statistics
    if INDEX_EMAILS:
        try:
            conn = sqlite3.connect(INDEX_DB)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM email_index")
            total_indexed = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(DISTINCT user_email) FROM email_index")
            users_indexed = cursor.fetchone()[0]
            conn.close()
            
            print(f"\n🔍 Search Index Statistics:")
            print(f"   Total emails indexed: {total_indexed:,}")
            print(f"   Users in index: {users_indexed}")
            print(f"   Index database: {INDEX_DB}")
            print(f"   Run 'python backup.py search' to search emails")
        except:
            pass
    
    # Check for incomplete backups
    incomplete = []
    for user_email in users:
        st = load_state(user_email)
        if st.get("backup_in_progress"):
            incomplete.append(user_email)
    
    if incomplete:
        print(f"\n🔄 INCOMPLETE BACKUPS ({len(incomplete)} users):")
        for user in incomplete:
            st = load_state(user)
            processed = st.get("messages_processed", 0)
            total = st.get("total_messages", 0)
            if total > 0:
                remaining = total - processed
                eta_hours = (remaining * RATE_LIMIT_DELAY) / 3600
                print(f"   - {user}: {processed}/{total} done, ~{eta_hours:.1f}h remaining")
        print(f"\n💡 Run the script again to continue these backups")
        print(f"   The script will automatically resume from where it left off")
    else:
        print(f"\n🎉 All backups complete!")
        print(f"📁 Location: Team Folder - {DROPBOX_TEAM_FOLDER}")
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

if __name__ == "__main__":
    main()