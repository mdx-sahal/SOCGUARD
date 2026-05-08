import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Configuration
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    DB_USER = os.environ.get('DB_USER', 'socguard_user')
    DB_PASS = os.environ.get('DB_PASS', 'socguard_password')
    # If DB_HOST is not provided, assume we are running locally (outside docker)
    DB_HOST = os.environ.get('DB_HOST')
    if DB_HOST:
        DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}/{os.environ.get('DB_NAME', 'socguard_db')}"
    else:
        DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@127.0.0.1:5435/socguard_db"

# Database Setup
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
