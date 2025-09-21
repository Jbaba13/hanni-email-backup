#!/usr/bin/env python3
"""
Email backup script that works with just Gmail API (no Admin SDK needed)
You manually specify the list of users to backup
"""

import os
import json
import base64
import logging
from datetime import datetime, timedelta
from typing import List

import dropbox
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configuration
SERVICE_ACCOUNT_FILE = r'C:\EmailBackup\service_account.json'
DROPBOX_ACCESS_TOKEN = 'sl.u.AF9c2-JjQfygwW-MuYcgNWP7m7QCTfjKne3F94gRJglGpTtlTJJBG1aNGJiN0Jt8gG550609Qa9p-BelwyFxX1ECeCAB1hvTpFqxpOLjdhBQhDoGP0D9ax2C5o2CR8yQib_FuUoM20aQ48A1dFNzbI7hAANwAZxOUtORby_MzExtDA1FXKT_gDFMMC86sPtujoJtNVAlo6qTZdnhwxddtqAGl5-qVOBoul_rnKreNFM3cEm7O_cNqEwqiLh37FXlgrUUZ7owJVPUQZlWG2ShUQ5ryuHbLi8ugsfUlUj2pyldSlDexMlEwhcCc0ItK0tUYKHICmnz1wpTSY0bIGasnCqn8Aya84BimaUGN1WiWsfizty19qEP2Hih25WTFMt82C55uL2Jn6fKT4JPZyJLG--vyHZptnGshM5QD46Mb707FocDqQQXM51986y40pIcTe-UJgawlGeP9zpgnnKrt1eed115lqyqrVQZ9vh5C8w4XlOuKr0lyXniLsnZzU4iwszOVV8KApaA7JGP2VOc2rltYd8_NsKMPkLzSsDOsrQzc_jMNPDOM8q7ud2meaOhYysHEFqnT_b9LP7EMhmIhf0CPFcmNIqklE7Ebq_uYWxuwqTeR2XkaVQMjO7tpnSOJ_A1bwKEspyvIFygmRYUTsTzDQEyAXsqkNhg-Np5jBvEjXf95vrO3F-QOFDkSEarkhCgcbE6bne6VhwrgN3ZCTOJUFZMQrAgRiYB3Ha6pGDF-TP-bYC4jt8eToY1j4Ke_E4lK1cTc1ObkWe1JZOuOaIdAO4kZ8ZBXmX0c5OvRq-42JegTS5-PJljaIexXOw5DvVsoBp9YJwPv_KW3STO79ow4H0fWFludXqv61Iia4XJk7D1fcALi1AA6yoWONHdjamG31sUNpILMdqdOSv-Fk5cIvH2xzsIUSL8fjnj56a7FlUTl655RQz8Fng1QwNVTz23T83Ic7hzp1NFaGWGwlnIE0TKJlcryTO6xQvL4duK2Gy0hEYkCg95kf0D4qMOTrI51IQlXJF7t23Zt3NOkMtBrUzyVEH-gutOVwMX-vYbfSs6XIDMTaoL1gC6JlZ49b7lB8gfIZHzyqzCy3an61pOHk1DSuVB7cQ6u03-v7jK8Q'
BACKUP_FOLDER_PREFIX = '/Email_Backups'

# Manual list of users to backup (add all your company emails here)
COMPANY_USERS = [
    'jennie@heyhanni.com',
    'user2@heyhanni.com',
    'user3@heyhanni.com',
    # Add more users as needed
]

# Just Gmail scope (no admin needed)
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('email_backup.log'),
        logging.StreamHandler()
    ]
)

class GmailOnlyBackupService:
    def __init__(self):
        self.dropbox_client = dropbox.DropboxTeam(DROPBOX_ACCESS_TOKEN)
        
    def _get_delegated_credentials(self, user_email: str):
        """Get credentials for domain-wide delegation"""
        credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        delegated_credentials = credentials.with_subject(user_email)
        return delegated_credentials
    
    def create_dropbox_folder(self, user_email: str) -> bool:
        """Create individual Dropbox folder for user"""
        try:
            folder_path = f"{BACKUP_FOLDER_PREFIX}/{user_email}"
            
            # Get team member info
            member_info = self._get_team_member_info(user_email)
            if not member_info:
                logging.error(f"Could not find Dropbox member for {user_email}")
                return False
                
            member_client = self.dropbox_client.as_user(member_info['team_member_id'])
            
            try:
                member_client.files_create_folder_v2(folder_path)
                logging.info(f"Created Dropbox folder: {folder_path}")
            except dropbox.exceptions.ApiError as e:
                if 'path/conflict/folder' in str(e):
                    logging.info(f"Folder already exists: {folder_path}")
                else:
                    raise
                    
            return True
            
        except Exception as error:
            logging.error(f"Error creating Dropbox folder for {user_email}: {error}")
            return False
    
    def _get_team_member_info(self, email: str):
        """Get Dropbox team member info by email"""
        try:
            members = self.dropbox_client.team_members_list()
            for member in members.members:
                if member.profile.email.lower() == email.lower():
                    return {
                        'team_member_id': member.profile.team_member_id,
                        'email': member.profile.email
                    }
            return None
        except Exception as error:
            logging.error(f"Error getting team member info: {error}")
            return None
    
    def backup_user_emails(self, user_email: str, days_back: int = 7) -> bool:
        """Backup emails for a specific user"""
        try:
            # Get delegated credentials for this user
            user_credentials = self._get_delegated_credentials(user_email)
            gmail_service = build('gmail', 'v1', credentials=user_credentials)
            
            # Calculate date range
            since_date = datetime.now() - timedelta(days=days_back)
            query = f'after:{since_date.strftime("%Y/%m/%d")}'
            
            # Get messages
            result = gmail_service.users().messages().list(
                userId='me', q=query, maxResults=100
            ).execute()
            
            messages = result.get('messages', [])
            logging.info(f"Found {len(messages)} messages for {user_email}")
            
            if not messages:
                return True
            
            # Get Dropbox member client
            member_info = self._get_team_member_info(user_email)
            if not member_info:
                logging.error(f"No Dropbox member found for {user_email}")
                return False
                
            member_client = self.dropbox_client.as_user(member_info['team_member_id'])
            
            # Process each message
            for msg in messages:
                try:
                    self._backup_single_email(
                        gmail_service, member_client, user_email, msg['id']
                    )
                except Exception as e:
                    logging.error(f"Error backing up message {msg['id']}: {e}")
                    continue
                    
            logging.info(f"Completed backup for {user_email}")
            return True
            
        except HttpError as error:
            logging.error(f"Error backing up emails for {user_email}: {error}")
            return False
    
    def _backup_single_email(self, gmail_service, dropbox_client, user_email: str, message_id: str):
        """Backup a single email message"""
        try:
            # Get the full message
            message = gmail_service.users().messages().get(
                userId='me', id=message_id, format='raw'
            ).execute()
            
            # Decode the raw message
            raw_email = base64.urlsafe_b64decode(message['raw']).decode('utf-8')
            
            # Get message headers for filename
            headers = gmail_service.users().messages().get(
                userId='me', id=message_id, format='metadata',
                metadataHeaders=['Subject', 'Date']
            ).execute()
            
            subject = 'No Subject'
            date_str = datetime.now().strftime('%Y%m%d')
            
            for header in headers['payload']['headers']:
                if header['name'] == 'Subject':
                    subject = header['value'][:50]  # Limit length
                elif header['name'] == 'Date':
                    try:
                        date_str = datetime.strptime(
                            header['value'].split(' ')[1:4], 
                            '%d %b %Y'
                        ).strftime('%Y%m%d')
                    except:
                        pass
            
            # Create safe filename
            safe_subject = "".join(c for c in subject if c.isalnum() or c in (' ', '-', '_')).rstrip()
            filename = f"{date_str}_{safe_subject}_{message_id}.eml"
            
            # Upload to Dropbox
            folder_path = f"{BACKUP_FOLDER_PREFIX}/{user_email}"
            file_path = f"{folder_path}/{filename}"
            
            dropbox_client.files_upload(
                raw_email.encode('utf-8'),
                file_path,
                mode=dropbox.files.WriteMode.overwrite
            )
            
            logging.debug(f"Backed up: {filename}")
            
        except Exception as error:
            logging.error(f"Error backing up message {message_id}: {error}")
            raise
    
    def run_backup(self, days_back: int = 7):
        """Run backup for specified users"""
        logging.info("Starting email backup for specified users")
        
        if not COMPANY_USERS:
            logging.error("No users specified in COMPANY_USERS list")
            return
        
        success_count = 0
        total_users = len(COMPANY_USERS)
        
        for user_email in COMPANY_USERS:
            logging.info(f"Processing user: {user_email}")
            
            try:
                # Create Dropbox folder
                if self.create_dropbox_folder(user_email):
                    # Backup emails
                    if self.backup_user_emails(user_email, days_back):
                        success_count += 1
                        
            except Exception as error:
                logging.error(f"Failed to backup {user_email}: {error}")
                continue
        
        logging.info(f"Backup completed: {success_count}/{total_users} users successful")

def main():
    """Main function"""
    try:
        backup_service = GmailOnlyBackupService()
        
        # Run backup for emails from last 7 days
        backup_service.run_backup(days_back=7)
        
    except Exception as error:
        logging.error(f"Backup failed: {error}")
        raise

if __name__ == "__main__":
    main()