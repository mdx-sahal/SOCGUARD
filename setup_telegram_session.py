import os
from telethon import TelegramClient

# These match the .env (hardcoded here for the standalone script or read from env)
# User provided:
API_ID = os.environ.get('TELEGRAM_API_ID')       # REMOVED SENSITIVE DATA
API_HASH = os.environ.get('TELEGRAM_API_HASH')   # REMOVED SENSITIVE DATA
SESSION_NAME = 'socguard_session'

def setup_session():
    print("---------------------------------------------------")
    print("SOCGUARD TELEGRAM SESSION SETUP")
    print("---------------------------------------------------")
    print("This script will create a persistent session file.")
    print("Please follow the prompts to log in (Phone Number -> Code).")
    
    client = TelegramClient(SESSION_NAME, API_ID, API_HASH)
    
    async def main():
        await client.start()
        print("\nSUCCESS: Session created!")
        print(f"File '{SESSION_NAME}.session' is now ready.")
        print("Move this file to your docker volume or root if mapping volumes.")
        
        me = await client.get_me()
        print(f"Logged in as: {me.username}")

    with client:
        client.loop.run_until_complete(main())

if __name__ == '__main__':
    setup_session()
