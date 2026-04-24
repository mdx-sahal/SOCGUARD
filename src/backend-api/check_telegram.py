from database import SessionLocal
from models import Alert
from sqlalchemy import desc

def list_telegram_alerts():
    db = SessionLocal()
    try:
        # Filter strictly for Telegram
        alerts = db.query(Alert).filter(Alert.platform.ilike('%telegram%')).order_by(Alert.timestamp.desc()).limit(5).all()
        print(f"--- Found {len(alerts)} Telegram Alerts ---")
        for a in alerts:
            print(f"ID: {a.id}")
            print(f"Time: {a.timestamp}")
            print(f"Threat: {a.threat_category}")
            print(f"URL: {a.original_url}")
            print(f"Score: {a.severity_score}")
            print("-" * 30)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_telegram_alerts()
