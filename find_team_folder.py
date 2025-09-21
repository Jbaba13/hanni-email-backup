#!/usr/bin/env python3
"""
Diagnostic script to find Dropbox team folder details
This will help identify the correct namespace and path for "Hanni Email Backups"
"""

import os
from dotenv import load_dotenv
import dropbox
from dropbox import DropboxTeam
import json

load_dotenv()

DROPBOX_TEAM_TOKEN = os.getenv("DROPBOX_TEAM_TOKEN")

if not DROPBOX_TEAM_TOKEN:
    print("❌ DROPBOX_TEAM_TOKEN not found in .env file")
    exit(1)

def find_team_folders():
    """Find all team folders and their details"""
    
    try:
        # Connect as team
        dbx_team = DropboxTeam(DROPBOX_TEAM_TOKEN)
        print("✅ Connected to Dropbox Business\n")
        
        # Method 1: List team folders directly
        print("=" * 60)
        print("METHOD 1: Team Folders via team_folder_list")
        print("=" * 60)
        
        try:
            # List all team folders
            result = dbx_team.team_team_folder_list()
            
            print(f"Found {len(result.team_folders)} team folders:\n")
            
            for folder in result.team_folders:
                print(f"📁 Name: {folder.name}")
                print(f"   ID: {folder.team_folder_id}")
                print(f"   Status: {folder.status._tag}")
                
                if "email backup" in folder.name.lower():
                    print("   ⭐ THIS IS YOUR EMAIL BACKUP FOLDER!")
                    
                print()
                
        except Exception as e:
            print(f"Could not list team folders directly: {e}\n")
        
        # Method 2: List namespaces (alternate approach)
        print("=" * 60)
        print("METHOD 2: Namespaces via team_namespaces_list")
        print("=" * 60)
        
        try:
            namespaces = dbx_team.team_namespaces_list()
            
            team_folders = []
            shared_folders = []
            
            for ns in namespaces.namespaces:
                if ns.namespace_type.is_team_folder():
                    team_folders.append(ns)
                elif ns.namespace_type.is_shared_folder():
                    shared_folders.append(ns)
            
            print(f"Found {len(team_folders)} team folder namespaces:\n")
            
            for ns in team_folders:
                print(f"📁 Name: {ns.name}")
                print(f"   Namespace ID: {ns.namespace_id}")
                print(f"   Type: Team Folder")
                
                if "email backup" in ns.name.lower():
                    print("   ⭐ THIS IS YOUR EMAIL BACKUP FOLDER!")
                    print(f"   ⚠️  SAVE THIS ID: {ns.namespace_id}")
                    
                print()
                
            if shared_folders:
                print(f"\nAlso found {len(shared_folders)} shared folders (not team folders)")
                
        except Exception as e:
            print(f"Could not list namespaces: {e}\n")
        
        # Method 3: Try to access as admin member
        print("=" * 60)
        print("METHOD 3: Access as Admin Member")
        print("=" * 60)
        
        try:
            # Get admin member
            admin_email = os.getenv("GOOGLE_DELEGATED_ADMIN", "jennie@heyhanni.com")
            members = dbx_team.team_members_list_v2(limit=500)
            
            admin_member_id = None
            for member in members.members:
                if member.profile.email.lower() == admin_email.lower():
                    admin_member_id = member.profile.team_member_id
                    print(f"✅ Found admin: {member.profile.email}")
                    print(f"   Member ID: {admin_member_id}\n")
                    break
            
            if admin_member_id:
                # Access as admin
                dbx_user = dbx_team.as_user(admin_member_id)
                
                # Try to list the team folder
                try:
                    # List root to see what's accessible
                    result = dbx_user.files_list_folder("")
                    
                    print("Folders visible at root level:")
                    for entry in result.entries:
                        if isinstance(entry, dropbox.files.FolderMetadata):
                            print(f"  📁 {entry.name}")
                            if "email backup" in entry.name.lower():
                                print("     ⭐ Found it!")
                    
                    # Try to specifically access the team folder
                    print("\nTrying to access /Hanni Email Backups directly...")
                    try:
                        folder_info = dbx_user.files_get_metadata("/Hanni Email Backups")
                        print(f"✅ Can access /Hanni Email Backups")
                        print(f"   Path: {folder_info.path_display}")
                        
                        # Try to list contents
                        contents = dbx_user.files_list_folder("/Hanni Email Backups")
                        print(f"   Contains {len(contents.entries)} items")
                        
                    except Exception as e:
                        error_str = str(e)
                        if "not_found" in error_str:
                            print("❌ Cannot find /Hanni Email Backups in user's root")
                            print("   The team folder might need different access method")
                        else:
                            print(f"❌ Error: {error_str[:200]}")
                    
                except Exception as e:
                    print(f"Could not list folders: {e}")
                    
        except Exception as e:
            print(f"Could not access as admin: {e}\n")
        
        # Method 4: Get team folder access info
        print("\n" + "=" * 60)
        print("RECOMMENDATIONS")
        print("=" * 60)
        
        print("""
Based on the above results, here's what you need to do:

1. If you found a namespace ID for "Hanni Email Backups":
   - Save that namespace ID
   - We'll update the script to use it

2. If the folder is only visible as a regular folder:
   - The team folder might not be fully set up
   - Try adding more team members to it
   - Or we can use the regular path approach

3. Next steps:
   - Run this script and send me the output
   - I'll update backup.py with the correct configuration
   - The backup will then go to the team folder
        """)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("🔍 Dropbox Team Folder Diagnostic Tool\n")
    find_team_folders()