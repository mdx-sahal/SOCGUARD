from database import SessionLocal
from models import Alert
from sqlalchemy import desc

def list_image_alerts():
    db = SessionLocal()
    try:
        # Check alerts with URL (images/audio)
        alerts = db.query(Alert).filter(Alert.original_url != None).order_by(Alert.timestamp.desc()).limit(5).all()
        print(f"--- Found {len(alerts)} Recent Image Alerts ---")
        for a in alerts:
            print(f"ID: {a.id}")
            print(f"Time: {a.timestamp}")
            print(f"Threat: {a.threat_category}")
            print(f"URL: {a.original_url[:50]}...") # Truncate URL
            print(f"Score: {a.severity_score}")
            print("-" * 30)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_image_alerts()
