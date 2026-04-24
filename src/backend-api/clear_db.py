from database import SessionLocal, engine
from models import Alert
from sqlalchemy import text

def clear_alerts():
    db = SessionLocal()
    try:
        # Use truncate for faster cleanup
        db.execute(text("TRUNCATE TABLE alerts RESTART IDENTITY;"))
        db.commit()
        print("Database cleared successfully.")
    except Exception as e:
        print(f"Error clearing DB: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clear_alerts()
