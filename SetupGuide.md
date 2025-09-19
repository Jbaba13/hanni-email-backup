# Quick Setup Guide - Email Backup System

## Prerequisites

- ✅ Google Workspace admin access
- ✅ Dropbox Business admin access  
- ✅ Python 3.9+ installed
- ✅ Windows/Mac/Linux computer or server

## Step 1: Google Cloud Setup (15 minutes)

### 1.1 Create Google Cloud Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Sign in with your Google Workspace admin account
3. Create new project or select existing one

### 1.2 Enable APIs
1. Navigate to "APIs & Services" → "Library"
2. Enable **Gmail API**
3. Enable **Admin SDK API**

### 1.3 Create Service Account
1. Go to "IAM & Admin" → "Service Accounts"
2. Click "Create Service Account"
3. Name: `email-backup-service`
4. Check "Enable Google Workspace Domain-wide Delegation"
5. Download JSON key file
6. Save as `service_account.json`

### 1.4 Configure Domain-Wide Delegation
1. Go to [admin.google.com](https://admin.google.com)
2. Navigate to: Security → API Controls → Domain-wide delegation
3. Click "Add new"
4. **Client ID**: Get from `service_account.json` (run `python get_client_id.py`)
5. **OAuth scopes**: 
   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/admin.directory.user
   ```
6. Click "Authorize"
7. **Wait 10-15 minutes** for propagation

## Step 2: Dropbox Business Setup (10 minutes)

### 2.1 Create Dropbox App
1. Go to [dropbox.com/developers/apps](https://dropbox.com/developers/apps)
2. Click "Create app"
3. Choose **Scoped access**
4. Choose **Full Dropbox**
5. Name your app: `Company Email Backup`

### 2.2 Configure Permissions
1. Go to app settings → Permissions tab
2. Enable these scopes:
   - `files.content.write`
   - `files.content.read`
   - `team_data.member`
   - `team_data.team_space`

### 2.3 Generate Access Token
1. Go to Settings tab
2. Scroll to "OAuth 2" section
3. Click "Generate access token"
4. **Copy and save this token**

## Step 3: Install & Configure (5 minutes)

### 3.1 Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 3.2 Update Configuration
Edit `emailbackup.py` and update these lines:
```python
SERVICE_ACCOUNT_FILE = r'C:\EmailBackup\service_account.json'  # Your path
DROPBOX_ACCESS_TOKEN = 'your_dropbox_token_here'  # From Step 2.3
ADMIN_EMAIL = 'admin@yourdomain.com'  # Your admin email
COMPANY_DOMAIN = 'yourdomain.com'  # Your company domain
```

## Step 4: Test & Run (5 minutes)

### 4.1 Test Domain-Wide Delegation
```bash
python test_delegation.py
```
**Expected output:**
```
✅ Admin SDK working! Found X users
✅ Gmail API working! Email: user@domain.com
✅ Found X messages
🎉 All tests passed!
```

### 4.2 Run Full Backup
```bash
python emailbackup.py
```

## Step 5: Schedule Automation (Optional)

### Windows Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (daily at 2 AM)
4. Action: `python C:\EmailBackup\emailbackup.py`

### Linux Cron Job
```bash
# Edit crontab
crontab -e

# Add this line for daily 2 AM backup
0 2 * * * /usr/bin/python3 /path/to/emailbackup.py
```

### Cloud Functions (Advanced)
Deploy as serverless function on AWS Lambda, Google Cloud Functions, or Azure Functions.

## Troubleshooting

### "Invalid scope" Error
- Double-check domain-wide delegation setup
- Ensure scopes are exactly as specified
- Wait 15 minutes after making changes
- Verify Client ID matches exactly

### "Could not find Dropbox member"
- Normal for users not in Dropbox Business
- Only users in both Google Workspace AND Dropbox will be backed up

### "Permission denied"
- Ensure admin account has Super Admin privileges
- Verify service account has domain-wide delegation enabled

## File Structure After Setup

```
EmailBackup/
├── emailbackup.py              # Main backup script
├── test_delegation.py          # Test script  
├── debug_service_account.py    # Debug helper
├── get_client_id.py           # Client ID extractor
├── service_account.json       # Google credentials (KEEP SECURE)
├── requirements.txt           # Python dependencies
├── email_backup.log          # Runtime logs
└── README.md                 # This guide
```

## Success Indicators

When working correctly, you should see:
- ✅ Users discovered from Google Workspace
- ✅ Dropbox folders created: `/Email_Backups/user@domain.com/`
- ✅ Emails uploaded as `.eml` files
- ✅ Log showing "Backup completed: X/Y users successful"

## Security Notes

- 🔒 Keep `service_account.json` secure and private
- 🔒 Store Dropbox token as environment variable in production
- 🔒 Regularly rotate access tokens
- 🔒 Monitor API usage and access logs
- 🔒 Ensure compliance with data protection regulations

---

**Need help?** Check the main documentation file for detailed troubleshooting and advanced configuration options.