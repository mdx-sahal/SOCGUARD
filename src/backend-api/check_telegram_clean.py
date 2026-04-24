from database import SessionLocal
from models import Alert
from sqlalchemy import desc

def list_telegram_clean():
    db = SessionLocal()
    try:
        # Filter for Telegram and Images (URL not null)
        alerts = db.query(Alert).filter(Alert.platform.ilike('%telegram%'), Alert.original_url != None).order_by(Alert.timestamp.desc()).limit(5).all()
        print(f"--- Found {len(alerts)} Telegram Images ---")
        for a in alerts:
            # Print as single string to avoid interleaving
            print(f"ID:{a.id} Time:{a.timestamp} Threat:{a.threat_category} Score:{a.severity_score} URL:{a.original_url[-20:]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    list_telegram_clean()
