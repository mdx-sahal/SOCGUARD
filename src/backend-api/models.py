from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Boolean
from database import Base
import datetime

class Alert(Base):
    __tablename__ = 'alerts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    content_id = Column(String, unique=True, nullable=False)
    timestamp = Column(DateTime, nullable=False)
    platform = Column(String, nullable=False)
    threat_category = Column(String, nullable=False)
    severity_score = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    original_url = Column(Text, nullable=True)
    audio_url = Column(Text, nullable=True)
    content_type = Column(String, nullable=True)
    original_text = Column(Text, nullable=True)
    explanation_image = Column(Text, nullable=True)
    author = Column(String, nullable=True)
    is_resolved = Column(Boolean, default=False)

    def __repr__(self):
        return f"<Alert(id={self.id}, content_id='{self.content_id}', category='{self.threat_category}', score={self.severity_score})>"


class Feedback(Base):
    __tablename__ = 'feedback'

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_content_id = Column(String, nullable=False, index=True)
    alert_category = Column(String, nullable=True)
    feedback_type = Column(String, nullable=False)        # 'confirm' | 'dispute'
    dispute_reason = Column(String, nullable=True)         # null when confirming
    analyst_notes = Column(Text, nullable=True)
    submitted_at = Column(DateTime, default=datetime.datetime.utcnow)

    def __repr__(self):
        return f"<Feedback(id={self.id}, alert='{self.alert_content_id}', type='{self.feedback_type}')>"
