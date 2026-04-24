import os
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

load_dotenv('.env')

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

CLIENT_ID = os.environ.get('EMAIL_CLIENT_ID', '').strip()
CLIENT_SECRET = os.environ.get('EMAIL_CLIENT_SECRET', '').strip()

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost:8085/", "http://localhost:8085"]
    }
}

def main():
    if not CLIENT_ID or not CLIENT_SECRET or "your_client" in CLIENT_ID:
        print("Please ensure your real EMAIL_CLIENT_ID and EMAIL_CLIENT_SECRET are in .env")
        return
        
    try:
        # We need to construct a flow manually since from_client_config requires a specific structure
        flow = InstalledAppFlow.from_client_config(
            client_config, 
            SCOPES
        )
        # Using a fixed port and setting access_type outside
        creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')
        
        print("\n" + "="*60)
        print("SUCCESS! YOUR GMAIL REFRESH TOKEN IS:")
        print(creds.refresh_token)
        print("="*60 + "\n")
        print("Now, open your .env file and paste that token into EMAIL_REFRESH_TOKEN=")
        print("Do NOT share this token with anyone.")
        
    except Exception as e:
        print(f"\nError mapping OAuth flow: {e}")
        print("Error during OAuth flow. Ensure your Google Cloud Client ID is configured as a 'Desktop app'.")

if __name__ == '__main__':
    main()
