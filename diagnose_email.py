"""
SOCGUARD Email Pipeline Diagnostic Script
Run this on the HOST machine (not inside Docker) to pinpoint where the pipeline breaks.
Usage:  python diagnose_email.py
"""

import os, sys, base64, re, json, time

# ── Load credentials from .env ─────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

CLIENT_ID     = os.environ.get('EMAIL_CLIENT_ID')
CLIENT_SECRET = os.environ.get('EMAIL_CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('EMAIL_REFRESH_TOKEN')
USER_ID       = os.environ.get('EMAIL_USER_ID', 'me')

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"

print("=" * 60)
print("  SOCGUARD EMAIL PIPELINE DIAGNOSTIC")
print("=" * 60)

# ── STEP 1: Check credentials ──────────────────────────────────────────────────
print("\n[1] Checking credentials...")
if CLIENT_ID and CLIENT_SECRET and REFRESH_TOKEN:
    print(f"  {PASS}  CLIENT_ID      : {CLIENT_ID[:30]}...")
    print(f"  {PASS}  CLIENT_SECRET  : {CLIENT_SECRET[:10]}...")
    print(f"  {PASS}  REFRESH_TOKEN  : {REFRESH_TOKEN[:20]}...")
    print(f"  {PASS}  USER_ID        : {USER_ID}")
else:
    print(f"  {FAIL}  Missing credentials! Check your .env file.")
    sys.exit(1)

# ── STEP 2: Build Gmail service ────────────────────────────────────────────────
print("\n[2] Building Gmail API service...")
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    )
    service = build('gmail', 'v1', credentials=creds)
    print(f"  {PASS}  Gmail service built successfully")
except Exception as e:
    print(f"  {FAIL}  Could not build Gmail service: {e}")
    print("\n  >> Check that google-api-python-client, google-auth-oauthlib are installed.")
    sys.exit(1)

# ── STEP 3: Test OAuth token refresh ──────────────────────────────────────────
print("\n[3] Testing OAuth token (calling getProfile)...")
try:
    profile = service.users().getProfile(userId=USER_ID).execute()
    print(f"  {PASS}  Authenticated as: {profile.get('emailAddress')}")
    print(f"        Messages total : {profile.get('messagesTotal')}")
    print(f"        Threads total  : {profile.get('threadsTotal')}")
except Exception as e:
    print(f"  {FAIL}  OAuth failed: {e}")
    print("\n  >> Your REFRESH_TOKEN may have expired or been revoked.")
    print("  >> Run: python generate_gmail_token.py   to regenerate it.")
    sys.exit(1)

# ── STEP 4: List unread messages ───────────────────────────────────────────────
print("\n[4] Fetching unread messages (inbox + spam)...")
try:
    results = service.users().messages().list(
        userId=USER_ID,
        maxResults=5,
        q="is:unread",
        includeSpamTrash=True
    ).execute()
    messages = results.get('messages', [])
    print(f"  {'✅ PASS' if messages else WARN}  Found {len(messages)} unread message(s)")
    if not messages:
        print(f"\n  >> No unread messages found.")
        print(f"  >> Send a test email to {USER_ID} and ensure it is UNREAD, then re-run.")
        sys.exit(0)
except Exception as e:
    print(f"  {FAIL}  Failed to list messages: {e}")
    sys.exit(1)

# ── STEP 5: Fetch and parse the first message ──────────────────────────────────
print("\n[5] Fetching and parsing the first message...")
msg_id = messages[0]['id']
try:
    msg_detail = service.users().messages().get(
        userId=USER_ID, id=msg_id, format='full'
    ).execute()
    print(f"  {PASS}  Message fetched. ID: {msg_id}")
except Exception as e:
    print(f"  {FAIL}  Failed to fetch message {msg_id}: {e}")
    sys.exit(1)

payload = msg_detail.get('payload', {})
headers = payload.get('headers', [])
subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '(No Subject)')
sender  = next((h['value'] for h in headers if h['name'].lower() == 'from'),    'unknown')
snippet = msg_detail.get('snippet', '')

print(f"  {PASS}  From    : {sender}")
print(f"  {PASS}  Subject : {subject}")
print(f"  {PASS}  Snippet : {snippet[:80]}...")

# ── STEP 6: Extract body ───────────────────────────────────────────────────────
print("\n[6] Extracting email body...")
body      = ""
html_body = ""
image_url = None

parts = [payload]
while parts:
    part = parts.pop()
    if part.get('parts'):
        parts.extend(part['parts'])
    mime = part.get('mimeType', '')
    data = part.get('body', {}).get('data', '')

    print(f"        Part mimeType: '{mime}' | data present: {bool(data)}")

    if mime == 'text/plain' and not body and data:
        try:
            data = data.replace(' ', '').replace('\n', '').replace('\r', '')
            data = data + '=' * (-len(data) % 4)
            body = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            print(f"  {PASS}  text/plain body extracted ({len(body)} chars)")
        except Exception as e:
            print(f"  {FAIL}  text/plain decode error: {e}")

    elif mime == 'text/html' and not html_body and data:
        try:
            data = data.replace(' ', '').replace('\n', '').replace('\r', '')
            data = data + '=' * (-len(data) % 4)
            raw_html = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
            html_body = re.sub(r'<[^>]+>', ' ', raw_html)
            html_body = re.sub(r'\s+', ' ', html_body).strip()
            print(f"  {PASS}  text/html body extracted + stripped ({len(html_body)} chars)")
        except Exception as e:
            print(f"  {FAIL}  text/html decode error: {e}")

    elif mime.startswith('image/'):
        print(f"  {WARN}  Image attachment found: {mime}")

final_body = body if body else html_body
if not final_body:
    final_body = snippet
    print(f"  {WARN}  Body empty — using snippet as fallback: '{snippet[:60]}'")

if final_body:
    print(f"\n  {PASS}  Final body ({len(final_body)} chars):")
    print(f"        {repr(final_body[:200])}")
else:
    print(f"  {FAIL}  Could not extract any body content!")

# ── STEP 7: Simulate what gets sent to Kafka ───────────────────────────────────
print("\n[7] Simulating Kafka event_data payload...")
event_data = {
    'content_id':      msg_id,
    'platform':        'email',
    'content_type':    'text',
    'subject':         subject,
    'content':         final_body,
    'display_content': f"Subject: {subject}\n\n{final_body}",
    'image_url':       image_url,
    'author_username': sender.split('<')[0].strip() if '<' in sender else sender,
}
print(f"  {PASS}  content field (NLP input): {repr(event_data['content'][:120])}")
print(f"  {PASS}  author_username          : {event_data['author_username']}")
print(f"  {PASS}  platform                 : {event_data['platform']}")

if not event_data['content']:
    print(f"  {FAIL}  content is EMPTY — text analyzer will drop this message!")
    sys.exit(1)

# ── STEP 8: Check backend API reachability ────────────────────────────────────
print("\n[8] Checking backend API (http://localhost:8000)...")
try:
    import requests as req
    r = req.get("http://localhost:8000/api/alerts?limit=1", timeout=5)
    alerts = r.json()
    print(f"  {PASS}  Backend API responded. Latest alert count: {len(alerts)}")
    if alerts:
        a = alerts[0]
        print(f"        Latest: [{a.get('platform')}] {a.get('threat_category')} score={a.get('severity_score')}")
        print(f"        content_id: {a.get('content_id')}")
except Exception as e:
    print(f"  {FAIL}  Backend API not reachable: {e}")
    print("  >> Is Docker running? Is the backend-api container up?")

# ── STEP 9: Check for recent email alerts in DB ────────────────────────────────
print("\n[9] Checking for email alerts in database...")
try:
    import requests as req
    r = req.get("http://localhost:8000/api/alerts?limit=50", timeout=5)
    all_alerts = r.json()
    email_alerts = [a for a in all_alerts if (a.get('platform') or '').lower() == 'email']
    print(f"  {'✅' if email_alerts else WARN}  Email alerts in DB: {len(email_alerts)} of {len(all_alerts)} total")
    for a in email_alerts[:3]:
        print(f"        [{a.get('timestamp')}] {a.get('threat_category')} | {a.get('original_text','')[:60]}")
except Exception as e:
    print(f"  {FAIL}  Could not check DB: {e}")

# ── STEP 10: Mark message as read (cleanup) ───────────────────────────────────
print(f"\n[10] Marking message {msg_id} as UNREAD again (reset for real service)...")
try:
    service.users().messages().modify(
        userId=USER_ID, id=msg_id,
        body={'addLabelIds': ['UNREAD']}
    ).execute()
    print(f"  {PASS}  Message reset to UNREAD — ingestion service will pick it up")
except Exception as e:
    print(f"  {WARN}  Could not reset message: {e}")

print("\n" + "=" * 60)
print("  DIAGNOSTIC COMPLETE")
print("=" * 60)
print("\nNext steps based on results above:")
print("  - If Step 3 failed → run generate_gmail_token.py to refresh OAuth")
print("  - If Step 4 found 0 messages → email is already marked read or not arrived")
print("  - If Step 6 body is empty → Gmail encoding issue (snippet fallback active)")
print("  - If Step 8 failed → Docker containers are not running")
print("  - If Step 9 shows 0 email alerts → pipeline issue (text analyzer dropping it)")
