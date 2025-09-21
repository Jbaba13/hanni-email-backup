#!/usr/bin/env python3
"""
Script to get the Client ID from your service account JSON file
"""

import json

def get_client_id():
    service_account_file = r'C:\EmailBackup\service_account.json'
    
    try:
        with open(service_account_file, 'r') as f:
            service_account_info = json.load(f)
            
        client_id = service_account_info.get('client_id')
        client_email = service_account_info.get('client_email')
        
        print(f"Client ID: {client_id}")
        print(f"Client Email: {client_email}")
        print(f"Project ID: {service_account_info.get('project_id')}")
        
        return client_id
        
    except FileNotFoundError:
        print("Service account file not found. Check the file path.")
        return None
    except json.JSONDecodeError:
        print("Invalid JSON file.")
        return None

if __name__ == "__main__":
    get_client_id()