import os
import time
import threading
import docker
from backend.database import SessionLocal, AnalysisResult, ExclusionRule
from backend.llm_engine import analyze_error

ERROR_KEYWORDS = os.getenv("ERROR_KEYWORDS", "ERROR,FATAL,Exception,CRITICAL").split(',')
ERROR_KEYWORDS = [k.strip() for k in ERROR_KEYWORDS if k.strip()]

IGNORE_CONTAINERS = os.getenv("IGNORE_CONTAINERS", "log2localllm,dozzle,ollama").split(',')
IGNORE_CONTAINERS = [c.strip() for c in IGNORE_CONTAINERS if c.strip()]

def get_docker_client():
    try:
        return docker.from_env()
    except Exception as e:
        print(f"Failed to connect to docker: {e}")
        return None

def is_excluded(container_name, line):
    db = SessionLocal()
    try:
        rules = db.query(ExclusionRule).filter(ExclusionRule.container_name == container_name).all()
        for rule in rules:
            if rule.pattern in line:
                return True
        return False
    finally:
        db.close()

def fetch_context_and_analyze(container_name, container_id, error_line, error_timestamp=None):
    # wait 100ms to allow subsequent logs to flow into docker
    time.sleep(0.1)
    
    client = get_docker_client()
    if not client: return
    
    try:
        raw_logs = client.api.logs(container_id, tail=200, timestamps=False)
        lines = [l for l in raw_logs.decode('utf-8', errors='replace').split('\n') if l]
        
        # Try to find the exact error line in the last 200 lines
        target_idx = -1
        # error_line might have a timestamp prefix from our stream, strip if we are comparing
        # Actually it's easier to just match a substring
        clean_err = error_line.split(' ', 1)[1] if 'T' in error_line[:30] else error_line
        clean_err = clean_err.strip()
        
        for i, l in enumerate(lines):
            if clean_err in l:
                target_idx = i
                break
                
        if target_idx != -1:
            start_idx = max(0, target_idx - 15)
            end_idx = min(len(lines), target_idx + 15)
            context = "\n".join(lines[start_idx:end_idx])
        else:
            context = "\n".join(lines[-30:]) # fallback context
            
    except Exception as e:
        context = f"Could not fetch context: {e}"
        
    print(f"Found error in {container_name}, context collected. Sending to LLM...")
    investigation, resolution = analyze_error(container_name, error_line, context)
    
    # Save to db
    db = SessionLocal()
    try:
        ar = AnalysisResult(
            container_name=container_name,
            error_line=error_line,
            context_log=context,
            llm_investigation=investigation,
            llm_resolution=resolution
        )
        db.add(ar)
        db.commit()
        print(f"Analysis saved for {container_name}")
    finally:
        db.close()

def monitor_container(container):
    print(f"Started monitoring {container.name}")
    client = get_docker_client()
    try:
        buffer = ""
        for chunk in container.logs(stream=True, follow=True, timestamps=True, tail=0):
            buffer += chunk.decode('utf-8', errors='replace')
            while '\n' in buffer:
                raw_line, buffer = buffer.split('\n', 1)
                line = raw_line.strip()
                if not line: continue
                
                # Check keywords first to drastically reduce DB queries
                for keyword in ERROR_KEYWORDS:
                    if keyword in line:
                        # Check exclusions only if an error is detected
                        if is_excluded(container.name, line):
                            break
                        
                        # Found error, spin off analyzer
                        threading.Thread(
                            target=fetch_context_and_analyze, 
                            args=(container.name, container.id, line),
                            daemon=True
                        ).start()
                        break # Don't trigger multiple times for one line
    except Exception as e:
        print(f"Stopped monitoring {container.name}: {e}")

def log_monitor_worker():
    client = get_docker_client()
    if not client: 
        print("Cannot start log monitor. No docker client.")
        return
        
    monitored_ids = set()
    
    while True:
        try:
            containers = client.containers.list()
            for c in containers:
                if c.name in IGNORE_CONTAINERS:
                    continue
                if c.id not in monitored_ids:
                    monitored_ids.add(c.id)
                    threading.Thread(target=monitor_container, args=(c,), daemon=True).start()
        except Exception as e:
            print(f"Error listing containers: {e}")
            
        time.sleep(10) # check for new containers every 10 seconds
