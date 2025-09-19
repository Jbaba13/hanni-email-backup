#!/usr/bin/env python3
"""
Test script to verify domain-wide delegation is working
"""

import json
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\EmailBackup\service_account.json'
ADMIN_EMAIL = 'jennie@heyhanni.com'  # Your admin email
COMPANY_DOMAIN = 'heyhanni.com'       # Your domain

SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/admin.directory.user'
]

def test_delegation():
    print("Testing domain-wide delegation...")
    
    try:
        # Load service account credentials
        print(f"Loading service account from: {SERVICE_ACCOUNT_FILE}")
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        
        # Create delegated credentials
        print(f"Creating delegated credentials for: {ADMIN_EMAIL}")
        delegated_credentials = credentials.with_subject(ADMIN_EMAIL)
        
        # Test Admin SDK access
        print("Testing Admin SDK access...")
        admin_service = build('admin', 'directory_v1', credentials=delegated_credentials)
        
        result = admin_service.users().list(
            domain=COMPANY_DOMAIN,
            maxResults=5
        ).execute()
        
        users = result.get('users', [])
        print(f"✅ Admin SDK working! Found {len(users)} users")
        
        if users:
            test_user_email = users[0]['primaryEmail']
            print(f"✅ Test user: {test_user_email}")
            
            # Test Gmail API access for first user
            print(f"Testing Gmail API access for: {test_user_email}")
            gmail_credentials = credentials.with_subject(test_user_email)
            gmail_service = build('gmail', 'v1', credentials=gmail_credentials)
            
            profile = gmail_service.users().getProfile(userId='me').execute()
            print(f"✅ Gmail API working! Email: {profile['emailAddress']}")
            
            # Test listing messages
            messages = gmail_service.users().messages().list(
                userId='me', maxResults=5
            ).execute()
            
            message_count = len(messages.get('messages', []))
            print(f"✅ Found {message_count} messages")
            
        print("\n🎉 All tests passed! Domain-wide delegation is working correctly.")
        
    except HttpError as error:
        print(f"❌ HTTP Error: {error}")
        if 'invalid_scope' in str(error):
            print("This indicates domain-wide delegation is not properly configured.")
            print("Please check the Google Admin Console setup.")
    except Exception as error:
        print(f"❌ Error: {error}")

if __name__ == "__main__":
    test_delegation()