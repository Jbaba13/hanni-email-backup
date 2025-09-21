#!/usr/bin/env python3
"""
Debug why emails aren't showing up in Dropbox
Check what actually got uploaded and where
"""

import os
from dotenv import load_dotenv
from dropbox import DropboxTeam
from datetime import datetime

load_dotenv()
DROPBOX_TEAM_TOKEN = os.getenv("DROPBOX_TEAM_TOKEN")
DROPBOX_ROOT = os.getenv("DROPBOX_ROOT_FOLDER", "/Email Backups")

def debug_missing_emails():
    """Find out why emails aren't in Dropbox"""
    
    print("🔍 Debugging Missing Email Backups")
    print("="*50)
    
    try:
        team = DropboxTeam(DROPBOX_TEAM_TOKEN)
        
        # Test users that should have backups
        test_users = [
            "ann@heyhanni.com",
            "hillary@heyhanni.com", 
            "jenn@heyhanni.com",
            "jennie@heyhanni.com",
            "leslie@heyhanni.com"
        ]
        
        for user_email in test_users:
            print(f"\n👤 Checking {user_email}")
            print("-" * 30)
            
            try:
                # Get team member ID
                members = team.team_members_list_v2()
                member_id = None
                
                for member in members.members:
                    if member.profile.email.lower() == user_email.lower():
                        member_id = member.profile.team_member_id
                        break
                
                if not member_id:
                    print("   ❌ Not found in Dropbox team")
                    continue
                
                print(f"   ✅ Found in team: {member_id}")
                
                # Get user's Dropbox client
                user_client = team.as_user(member_id)
                
                # Check multiple possible locations
                locations_to_check = [
                    "/Email Backups",
                    "/Email_Backups", 
                    "/Email Backups/2025",
                    "/Email Backups/2025/09",
                    "/Email Backups/2025/09/18",
                    "/",  # Root folder
                ]
                
                found_anything = False
                
                for location in locations_to_check:
                    try:
                        print(f"   🔍 Checking: {location}")
                        result = user_client.files_list_folder(location)
                        
                        files = [f for f in result.entries]
                        if files:
                            print(f"      ✅ Found {len(files)} items:")
                            for file in files[:5]:  # Show first 5
                                file_type = "📁" if hasattr(file, 'sharing_info') else "📄"
                                print(f"         {file_type} {file.name}")
                            if len(files) > 5:
                                print(f"         ... and {len(files) - 5} more")
                            found_anything = True
                        else:
                            print(f"      📭 Empty")
                            
                    except Exception as e:
                        print(f"      ❌ Error: {str(e)[:50]}...")
                
                if not found_anything:
                    print("   ⚠️  No files found in any location")
                    
            except Exception as e:
                print(f"   ❌ Error accessing {user_email}: {e}")
    
    except Exception as e:
        print(f"❌ Failed to connect to Dropbox: {e}")
        return False
    
    return True

def check_upload_permissions():
    """Test if we can actually upload to Dropbox"""
    
    print(f"\n🧪 Testing Upload Permissions")
    print("="*35)
    
    try:
        team = DropboxTeam(DROPBOX_TEAM_TOKEN)
        
        # Test with jennie@heyhanni.com (known to be in team)
        test_user = "jennie@heyhanni.com"
        
        # Get member ID
        members = team.team_members_list_v2()
        member_id = None
        
        for member in members.members:
            if member.profile.email.lower() == test_user.lower():
                member_id = member.profile.team_member_id
                break
        
        if not member_id:
            print(f"❌ Can't find {test_user} in team")
            return False
        
        print(f"✅ Found {test_user}: {member_id}")
        
        # Get user client
        user_client = team.as_user(member_id)
        
        # Try to upload a test file
        test_content = f"Test upload at {datetime.now()}"
        test_path = f"{DROPBOX_ROOT}/test_upload.txt"
        
        print(f"📤 Testing upload to: {test_path}")
        
        try:
            user_client.files_upload(
                test_content.encode('utf-8'),
                test_path,
                mode=dropbox.files.WriteMode.overwrite
            )
            print("✅ Test upload successful!")
            
            # Try to list the file
            try:
                result = user_client.files_list_folder(DROPBOX_ROOT)
                test_file_found = any(f.name == "test_upload.txt" for f in result.entries)
                if test_file_found:
                    print("✅ Test file visible in folder")
                else:
                    print("⚠️  Test file uploaded but not visible")
            except Exception as e:
                print(f"⚠️  Can't list folder: {e}")
            
            # Clean up test file
            try:
                user_client.files_delete_v2(test_path)
                print("🧹 Test file cleaned up")
            except:
                pass
                
        except Exception as e:
            print(f"❌ Test upload failed: {e}")
            return False
            
    except Exception as e:
        print(f"❌ Permission test failed: {e}")
        return False
    
    return True

def suggest_fixes():
    """Suggest potential fixes"""
    
    print(f"\n🔧 Potential Issues & Fixes")
    print("="*30)
    
    print("1. 📁 FOLDER STRUCTURE:")
    print("   - Files should be in: /Email Backups/2025/09/18/")
    print("   - Check if you're looking at the right level")
    
    print("\n2. 🔐 PERMISSIONS:")
    print("   - Dropbox team app might need 'files.content.write' scope")
    print("   - Team member might not have proper access")
    
    print("\n3. 🚫 SILENT UPLOAD FAILURES:")
    print("   - Logs showed 'Request to files/upload' but might have failed")
    print("   - Need to check actual API responses")
    
    print("\n4. 📍 WRONG LOCATION:")
    print("   - Files might be uploading to different folder")
    print("   - Check DROPBOX_ROOT_FOLDER in .env file")
    
    print("\n5. ⏱️  SYNC DELAY:")
    print("   - Dropbox might need time to sync")
    print("   - Try refreshing the web interface")
    
    print(f"\n💡 IMMEDIATE ACTIONS:")
    print("   1. Run this debug script: python debug_uploads.py")
    print("   2. Check .env file: DROPBOX_ROOT_FOLDER setting") 
    print("   3. Try manual test upload")
    print("   4. Re-run backup with DRY_RUN=1 to test without uploads")

if __name__ == "__main__":
    if debug_missing_emails():
        check_upload_permissions()
    suggest_fixes()