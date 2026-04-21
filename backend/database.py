import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/log2llm.db")

# Ensure directory exists
os.makedirs(os.path.dirname(DATABASE_URL.replace("sqlite:///", "")), exist_ok=True)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, index=True)
    container_name = Column(String, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    error_line = Column(Text)
    context_log = Column(Text)       # The +/- 100ms context
    llm_investigation = Column(Text)
    llm_resolution = Column(Text)

class ExclusionRule(Base):
    __tablename__ = "exclusion_rules"

    id = Column(Integer, primary_key=True, index=True)
    container_name = Column(String, index=True)
    pattern = Column(String)  # Simple string match or basic regex

Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
