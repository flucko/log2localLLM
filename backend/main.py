import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional

from backend.database import SessionLocal, AnalysisResult, ExclusionRule
from backend.log_monitor import log_monitor_worker, get_queue_status
from sqlalchemy.orm import Session

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start background worker
    worker_thread = threading.Thread(target=log_monitor_worker, daemon=True)
    worker_thread.start()
    yield
    # Cleanup if needed

app = FastAPI(lifespan=lifespan)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models
class AnalysisResponse(BaseModel):
    id: int
    container_name: str
    timestamp: str # Using str for simplicity on output
    error_line: str
    context_log: str
    llm_investigation: str
    llm_resolution: str

    class Config:
        from_attributes = True

class ExclusionRequest(BaseModel):
    container_name: str
    pattern: str

@app.get("/api/analyses", response_model=List[AnalysisResponse])
def get_analyses(limit: int = 50, db: Session = Depends(get_db)):
    results = db.query(AnalysisResult).order_by(AnalysisResult.timestamp.desc()).limit(limit).all()
    formatted = []
    for r in results:
        formatted.append(AnalysisResponse(
            id=r.id,
            container_name=r.container_name,
            timestamp=r.timestamp.isoformat() + "Z",
            error_line=r.error_line,
            context_log=r.context_log,
            llm_investigation=r.llm_investigation,
            llm_resolution=r.llm_resolution
        ))
    return formatted

@app.delete("/api/analyses/{analysis_id}")
def delete_analysis(analysis_id: int, db: Session = Depends(get_db)):
    record = db.query(AnalysisResult).filter(AnalysisResult.id == analysis_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(record)
    db.commit()
    return {"status": "ok"}

@app.delete("/api/analyses")
def delete_all_analyses(db: Session = Depends(get_db)):
    db.query(AnalysisResult).delete()
    db.commit()
    return {"status": "ok", "message": "All analyses cleared"}

@app.post("/api/exclusions")
def add_exclusion(req: ExclusionRequest, db: Session = Depends(get_db)):
    rule = ExclusionRule(container_name=req.container_name, pattern=req.pattern)
    db.add(rule)
    db.commit()
    return {"status": "ok", "message": f"Added exclusion for {req.container_name}"}

@app.get("/api/queue")
def get_queue():
    return get_queue_status()

@app.get("/api/exclusions")
def get_exclusions(db: Session = Depends(get_db)):
    rules = db.query(ExclusionRule).all()
    return [{"id": r.id, "container_name": r.container_name, "pattern": r.pattern} for r in rules]

# Mount frontend
import os
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
os.makedirs(frontend_dir, exist_ok=True)
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
