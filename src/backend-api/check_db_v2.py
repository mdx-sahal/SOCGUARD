from database import SessionLocal
from models import Alert

def list_recent_alerts():
    db = SessionLocal()
    try:
        alerts = db.query(Alert).order_by(Alert.timestamp.desc()).limit(5).all()
        print(f"--- Found {len(alerts)} Recent Alerts ---")
        for a in alerts:
            print(f"ID: {a.id} | Time: {a.timestamp}")
            print(f"Platform: {a.platform} | Threat: {a.threat_category}")
            print(f"URL: {a.original_url}")
            print(f"Score: {a.severity_score}")
            print("-" * 30)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_recent_alerts()
