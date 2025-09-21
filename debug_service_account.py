#!/usr/bin/env python3
"""
Debug script to check service account configuration
"""

import json

def debug_service_account():
    service_account_file = r'C:\EmailBackup\service_account.json'
    
    try:
        with open(service_account_file, 'r') as f:
            service_account_info = json.load(f)
            
        print("=== SERVICE ACCOUNT INFORMATION ===")
        print(f"Client ID: {service_account_info.get('client_id')}")
        print(f"Client Email: {service_account_info.get('client_email')}")
        print(f"Project ID: {service_account_info.get('project_id')}")
        print(f"Type: {service_account_info.get('type')}")
        print(f"Auth URI: {service_account_info.get('auth_uri')}")
        print(f"Token URI: {service_account_info.get('token_uri')}")
        
        # Check if domain-wide delegation is enabled
        if 'client_id' in service_account_info:
            print(f"\n✅ Client ID found: {service_account_info['client_id']}")
            print("📋 Copy this Client ID exactly for Google Admin Console")
        else:
            print("❌ Client ID not found in service account file")
            
        print("\n=== WHAT TO DO NEXT ===")
        print("1. Go to Google Admin Console (admin.google.com)")
        print("2. Navigate to: Security → API Controls → Domain-wide delegation")
        print("3. Look for an entry with this Client ID:")
        print(f"   {service_account_info.get('client_id')}")
        print("4. If found, check the scopes are EXACTLY:")
        print("   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/admin.directory.users.readonly")
        print("5. If not found, add a new entry with the Client ID above")
        
        return service_account_info.get('client_id')
        
    except FileNotFoundError:
        print("❌ Service account file not found")
        return None
    except json.JSONDecodeError:
        print("❌ Invalid JSON in service account file")
        return None

if __name__ == "__main__":
    debug_service_account()