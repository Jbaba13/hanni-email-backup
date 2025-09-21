#!/usr/bin/env python3
"""
Generate Dropbox refresh token for permanent API access
Works with Dropbox Business Team apps
Run this once to get your refresh token
"""

import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import requests
import json
import os
import sys

print("="*60)
print("🔐 Dropbox Refresh Token Generator")
print("   For Dropbox Business Team Apps")
print("="*60)

# Get credentials from environment or prompt
try:
    from dotenv import load_dotenv
    load_dotenv()
    APP_KEY = os.getenv("DROPBOX_APP_KEY")
    APP_SECRET = os.getenv("DROPBOX_APP_SECRET")
except:
    APP_KEY = None
    APP_SECRET = None

# If not in env, prompt for them
if not APP_KEY:
    print("\n📋 Please enter your Dropbox App credentials")
    print("   (Get these from https://www.dropbox.com/developers/apps)")
    print("")
    APP_KEY = input("App Key: ").strip()
    
if not APP_SECRET:
    APP_SECRET = input("App Secret: ").strip()

if not APP_KEY or not APP_SECRET:
    print("\n❌ App Key and App Secret are required!")
    print("   Get them from: https://www.dropbox.com/developers/apps")
    print("   1. Click on your app")
    print("   2. Copy 'App key' and 'App secret' from Settings tab")
    sys.exit(1)

print(f"\n✅ Using App Key: {APP_KEY[:10]}...")

# Global variable to store the result
auth_result = None

class OAuthHandler(BaseHTTPRequestHandler):
    """Handle OAuth callback from Dropbox"""
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging"""
        pass
    
    def do_GET(self):
        global auth_result
        
        query = urlparse(self.path).query
        params = parse_qs(query)
        
        if 'code' in params:
            auth_code = params['code'][0]
            print(f"\n✅ Authorization code received!")
            print("   Exchanging for refresh token...")
            
            # Exchange auth code for refresh token
            token_url = "https://api.dropboxapi.com/oauth2/token"
            data = {
                'code': auth_code,
                'grant_type': 'authorization_code',
                'client_id': APP_KEY,
                'client_secret': APP_SECRET,
                'redirect_uri': 'http://localhost:8000'
            }
            
            try:
                response = requests.post(token_url, data=data)
                tokens = response.json()
                
                if 'error' in tokens:
                    error_msg = tokens.get('error_description', tokens['error'])
                    auth_result = {'error': error_msg}
                    
                    html = f"""
                    <html><body style="font-family: Arial, sans-serif; padding: 40px;">
                    <h1 style="color: red;">❌ Error Getting Token</h1>
                    <pre style="background: #f5f5f5; padding: 20px; border-radius: 5px;">
{error_msg}
                    </pre>
                    <p>Please check your App Key and Secret, then try again.</p>
                    <p>You can close this window.</p>
                    </body></html>
                    """
                    
                elif 'refresh_token' in tokens:
                    auth_result = tokens
                    
                    html = f"""
                    <html><body style="font-family: Arial, sans-serif; padding: 40px;">
                    <h1 style="color: green;">✅ Success! Save these tokens:</h1>
                    <div style="background: #f0f8ff; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    <h2>Add to your .env file:</h2>
                    <pre style="background: white; padding: 15px; border: 1px solid #ddd; border-radius: 5px;">
# Dropbox Configuration (Permanent Access)
DROPBOX_APP_KEY={APP_KEY}
DROPBOX_APP_SECRET={APP_SECRET}
DROPBOX_REFRESH_TOKEN={tokens['refresh_token']}

# Your existing team token (keep as fallback)
# DROPBOX_TEAM_TOKEN=your_old_token
                    </pre>
                    </div>
                    <div style="background: #fff9e6; padding: 15px; border-radius: 5px; border-left: 4px solid #ffc107;">
                    <h3>⚠️ Important Notes:</h3>
                    <ul>
                        <li>This refresh token provides <strong>permanent access</strong></li>
                        <li>Keep it secure - don't share or commit to git</li>
                        <li>Your app will auto-refresh access tokens as needed</li>
                    </ul>
                    </div>
                    <p style="margin-top: 20px;">You can close this window now.</p>
                    </body></html>
                    """
                    
                    # Also print to console
                    print("\n" + "="*60)
                    print("🎉 REFRESH TOKEN OBTAINED SUCCESSFULLY!")
                    print("="*60)
                    print("\n📝 Add these to your .env file:\n")
                    print(f"DROPBOX_APP_KEY={APP_KEY}")
                    print(f"DROPBOX_APP_SECRET={APP_SECRET}")
                    print(f"DROPBOX_REFRESH_TOKEN={tokens['refresh_token']}")
                    print("\n" + "="*60)
                    
                    # Save to file for convenience
                    with open("dropbox_refresh_token.txt", "w") as f:
                        f.write(f"# Add these to your .env file:\n")
                        f.write(f"DROPBOX_APP_KEY={APP_KEY}\n")
                        f.write(f"DROPBOX_APP_SECRET={APP_SECRET}\n")
                        f.write(f"DROPBOX_REFRESH_TOKEN={tokens['refresh_token']}\n")
                    print("💾 Also saved to: dropbox_refresh_token.txt")
                    print("="*60)
                    
                else:
                    auth_result = {'error': 'No refresh token in response'}
                    html = f"""
                    <html><body style="font-family: Arial, sans-serif; padding: 40px;">
                    <h1 style="color: orange;">⚠️ Partial Success</h1>
                    <p>Got access token but no refresh token.</p>
                    <pre style="background: #f5f5f5; padding: 20px; border-radius: 5px;">
{json.dumps(tokens, indent=2)}
                    </pre>
                    <p>Make sure your app has offline access enabled.</p>
                    </body></html>
                    """
                    
            except Exception as e:
                auth_result = {'error': str(e)}
                html = f"""
                <html><body style="font-family: Arial, sans-serif; padding: 40px;">
                <h1 style="color: red;">❌ Error</h1>
                <pre>{str(e)}</pre>
                <p>Check your internet connection and try again.</p>
                </body></html>
                """
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
            
        elif 'error' in params:
            error = params.get('error_description', params['error'])[0]
            auth_result = {'error': error}
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""
            <html><body style="font-family: Arial, sans-serif; padding: 40px;">
            <h1 style="color: red;">❌ Authorization Denied</h1>
            <p>{error}</p>
            <p>Please run the script again and authorize the app.</p>
            </body></html>
            """
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()

def main():
    global auth_result
    
    print("\n📌 Prerequisites:")
    print("   1. Your Dropbox app must be configured at:")
    print("      https://www.dropbox.com/developers/apps")
    print("   2. Add redirect URI: http://localhost:8000")
    print("   3. Enable these permissions:")
    print("      - files.content.write")
    print("      - files.content.read")
    print("      - team_data.member (if team app)")
    print("      - team_data.team_space (if team app)")
    
    input("\n🔑 Press Enter to start OAuth flow...")
    
    # Build authorization URL for offline access
    auth_url = (
        f"https://www.dropbox.com/oauth2/authorize?"
        f"client_id={APP_KEY}&"
        f"response_type=code&"
        f"redirect_uri=http://localhost:8000&"
        f"token_access_type=offline"  # This requests a refresh token
    )
    
    print("\n🌐 Opening browser for Dropbox authorization...")
    print("   If browser doesn't open, manually visit:")
    print(f"   {auth_url}")
    
    # Open browser
    webbrowser.open(auth_url)
    
    # Start local server to receive callback
    print("\n⏳ Waiting for authorization callback...")
    print("   (Listening on http://localhost:8000)")
    
    server = HTTPServer(('localhost', 8000), OAuthHandler)
    server.timeout = 120  # 2 minute timeout
    
    # Handle one request (the callback)
    server.handle_request()
    server.server_close()
    
    # Check result
    if auth_result and 'refresh_token' in auth_result:
        print("\n✅ Success! Check your browser window for the tokens.")
        print("   Don't forget to update your .env file!")
        return 0
    elif auth_result and 'error' in auth_result:
        print(f"\n❌ Error: {auth_result['error']}")
        return 1
    else:
        print("\n⏱️ Timeout or no response received.")
        print("   Please try again.")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n👋 Cancelled by user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)