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
from models import Alert
from fastapi.responses import FileResponse

# Initialize DB tables
Base.metadata.create_all(bind=engine)

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
app.mount("/static", StaticFiles(directory="static"), name="static")

# Kafka Config
KAFKA_BROKER = os.environ.get('KAFKA_BROKER', 'kafka:29092')
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
    return FileResponse('static/index.html')

@app.get("/login")
async def read_login():
    return FileResponse('static/login.html')

class LoginRequest(BaseModel):
    username: str
    password: str

@app.post("/api/login")
async def login(request: LoginRequest):
    # For MVP/Demo: Hardcoded credentials
    if request.username == "admin" and request.password == "admin123":
        return {"status": "success", "token": "socguard_token_12345"}
    return {"status": "error", "message": "Invalid credentials"}

# REST Endpoints
@app.get("/api/alerts")
def get_alerts(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    alerts = db.query(Alert).order_by(Alert.timestamp.desc()).offset(skip).limit(limit).all()
    return alerts

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
