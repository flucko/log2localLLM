import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///data/log2llm.db")

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
    context_log = Column(Text)
    llm_executive_summary = Column(Text, default="")
    llm_investigation = Column(Text)
    llm_resolution = Column(Text)
    window_start = Column(DateTime, nullable=True)
    window_end = Column(DateTime, nullable=True)
    signal_types = Column(String, nullable=True)
    error_count = Column(Integer, nullable=True)
    fingerprint_count = Column(Integer, nullable=True)

class ExclusionRule(Base):
    __tablename__ = "exclusion_rules"

    id = Column(Integer, primary_key=True, index=True)
    container_name = Column(String, index=True)
    pattern = Column(String)

class ErrorWindow(Base):
    __tablename__ = "error_windows"

    id = Column(Integer, primary_key=True, index=True)
    container_name = Column(String, index=True)
    window_start = Column(DateTime)
    window_end = Column(DateTime)
    error_count = Column(Integer)
    fingerprints_json = Column(Text)

class KnownFingerprint(Base):
    __tablename__ = "known_fingerprints"

    id = Column(Integer, primary_key=True, index=True)
    container_name = Column(String, index=True)
    fingerprint = Column(String, index=True)
    first_seen = Column(DateTime)
    last_seen = Column(DateTime)

Base.metadata.create_all(bind=engine)

with engine.connect() as conn:
    from sqlalchemy import text, inspect
    cols = [c["name"] for c in inspect(engine).get_columns("analysis_results")]
    migrations = [
        ("llm_executive_summary", "TEXT DEFAULT ''"),
        ("window_start",          "DATETIME"),
        ("window_end",            "DATETIME"),
        ("signal_types",          "TEXT"),
        ("error_count",           "INTEGER"),
        ("fingerprint_count",     "INTEGER"),
    ]
    for col_name, col_def in migrations:
        if col_name not in cols:
            conn.execute(text(f"ALTER TABLE analysis_results ADD COLUMN {col_name} {col_def}"))
    conn.commit()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
