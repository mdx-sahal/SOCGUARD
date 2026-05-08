import os
import json
import asyncio
from typing import List
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import func
from confluent_kafka import Consumer

from database import get_db, engine, Base
from models import Alert, Feedback
from fastapi.responses import FileResponse

# Initialize DB tables
try:
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized successfully.")
except Exception as e:
    print(f"Warning: Could not initialize database tables. Ensure PostgreSQL is running. Error: {e}")

app = FastAPI(title="SOCGUARD Backend API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# Kafka Config
# Default to localhost:9092 if KAFKA_BROKER is not set (e.g. running locally outside Docker)
KAFKA_BROKER = os.environ.get('KAFKA_BROKER')
if not KAFKA_BROKER:
    KAFKA_BROKER = 'localhost:9092'
KAFKA_TOPIC = 'processed_alerts'

# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                # Handle disconnected clients that weren't properly removed
                pass

manager = ConnectionManager()

# Background Kafka Consumer
async def consume_alerts():
    conf = {
        'bootstrap.servers': KAFKA_BROKER,
        'group.id': 'backend-api-group',
        'auto.offset.reset': 'latest'
    }
    try:
        consumer = Consumer(conf)
        consumer.subscribe([KAFKA_TOPIC])
        print(f"Subscribed to Kafka topic: {KAFKA_TOPIC}")
    except Exception as e:
        print(f"Could not connect to Kafka at {KAFKA_BROKER}: {e}")
        return

    try:
        while True:
            # Run poll in executor to avoid blocking the event loop
            msg = await asyncio.get_event_loop().run_in_executor(None, consumer.poll, 1.0)
            
            if msg is None:
                continue
            if msg.error():
                print(f"Consumer error: {msg.error()}")
                continue
            
            try:
                data = json.loads(msg.value().decode('utf-8'))
                await manager.broadcast(data)
            except Exception as e:
                print(f"Error processing/broadcasting message: {e}")
    finally:
        consumer.close()

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(consume_alerts())

@app.get("/")
async def read_root():
    return FileResponse(os.path.join(BASE_DIR, 'static/index.html'))

@app.get("/login")
async def read_login():
    return FileResponse(os.path.join(BASE_DIR, 'static/login.html'))

class LoginRequest(BaseModel):
    username: str
    password: str

class FeedbackRequest(BaseModel):
    alert_content_id: str
    alert_category: str = ""
    feedback_type: str          # 'confirm' | 'dispute'
    dispute_reason: str = ""    # empty string when confirming
    analyst_notes: str = ""

@app.post("/api/login")
async def login(request: LoginRequest):
    # For MVP/Demo: Hardcoded credentials
    if request.username == "admin" and request.password == "admin123":
        return {"status": "success", "token": "socguard_token_12345"}
    return {"status": "error", "message": "Invalid credentials"}

# REST Endpoints
def serialize_alert(a):
    """Convert an Alert ORM object to a JSON-safe dict with all fields the frontend expects."""
    is_image = (a.content_type == 'image') if a.content_type else False
    return {
        "id":             a.id,
        "content_id":     a.content_id,
        "timestamp":      a.timestamp.isoformat() if a.timestamp else None,
        "platform":       a.platform,
        "threat_category": a.threat_category,
        "severity_score": a.severity_score,
        "reasoning":      a.reasoning,
        "content_type":   a.content_type,
        "original_text":  a.original_text,
        "author":         a.author,
        "author_username": a.author,
        "is_resolved":    a.is_resolved,
        "audio_url":      a.audio_url,
        "explanation_image": a.explanation_image,
        # frontend checks alert.image_url first, then alert.original_url
        "image_url":      a.original_url if is_image else None,
        "original_url":   a.original_url,
    }

@app.get("/api/alerts")
def get_alerts(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).offset(skip).limit(limit).all()
    return [serialize_alert(a) for a in alerts]

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total_alerts = db.query(Alert).count()
    
    # Group by threat_category
    category_counts = db.query(Alert.threat_category, func.count(Alert.id)).group_by(Alert.threat_category).all()
    
    # Count High Severity Alerts
    high_severity_count = db.query(Alert).filter(Alert.severity_score > 80).count()

    stats = {
        "total_alerts": total_alerts,
        "high_severity_alerts": high_severity_count,
        "categories": {category: count for category, count in category_counts}
    }
    return stats

@app.delete("/api/alerts")
def clear_alerts(db: Session = Depends(get_db)):
    try:
        num_deleted = db.query(Alert).delete()
        db.commit()
        return {"status": "success", "message": f"Deleted {num_deleted} alerts"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}

@app.post("/api/feedback", status_code=201)
def submit_feedback(request: FeedbackRequest, db: Session = Depends(get_db)):
    """Persist analyst feedback on a threat alert."""
    # Validate feedback type
    if request.feedback_type not in ('confirm', 'dispute'):
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="feedback_type must be 'confirm' or 'dispute'")

    if request.feedback_type == 'dispute' and not request.dispute_reason:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="dispute_reason is required when disputing")

    entry = Feedback(
        alert_content_id=request.alert_content_id,
        alert_category=request.alert_category or None,
        feedback_type=request.feedback_type,
        dispute_reason=request.dispute_reason or None,
        analyst_notes=request.analyst_notes or None,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    print(f"[Feedback] Saved: id={entry.id} alert={entry.alert_content_id} type={entry.feedback_type}")
    return {"status": "success", "feedback_id": entry.id}

@app.get("/api/feedback")
def get_feedback(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """Return all submitted analyst feedback entries."""
    import datetime
    rows = db.query(Feedback).order_by(Feedback.submitted_at.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": r.id,
            "alert_content_id": r.alert_content_id,
            "alert_category": r.alert_category,
            "feedback_type": r.feedback_type,
            "dispute_reason": r.dispute_reason,
            "analyst_notes": r.analyst_notes,
            "submitted_at": r.submitted_at.isoformat() if r.submitted_at else None,
        }
        for r in rows
    ]

@app.get("/api/logs")
def get_logs():
    try:
        with open("/app/../ingestion_logs_new.txt", "rb") as f:
            content = f.read().decode("utf-16le", errors="replace")
            return {"logs": content[-5000:]}
    except Exception as e:
        return {"error": str(e)}


# WebSocket Endpoint
@app.websocket("/ws/live-threats")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive, wait for client messages (if any)
            # In this case, we are mostly pushing, but we need to await receive to detect disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    import uvicorn
    # Pass the app object directly so it works regardless of the current working directory
    uvicorn.run(app, host="0.0.0.0", port=8000)
