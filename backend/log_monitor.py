import os
import time
import queue
import threading
import docker
from collections import deque
from backend.database import SessionLocal, AnalysisResult, ExclusionRule
from backend.llm_engine import analyze_error

ERROR_KEYWORDS = os.getenv("ERROR_KEYWORDS", "ERROR,FATAL,Exception,CRITICAL").split(',')
ERROR_KEYWORDS = [k.strip() for k in ERROR_KEYWORDS if k.strip()]

IGNORE_CONTAINERS = os.getenv("IGNORE_CONTAINERS", "log2localllm,dozzle,ollama").split(',')
IGNORE_CONTAINERS = [c.strip() for c in IGNORE_CONTAINERS if c.strip()]

# Global LLM work queue: items are (container_name, container_id, error_line)
llm_queue: queue.Queue = queue.Queue()

# Snapshot of the 5 most recently enqueued items for the API (container_name, error_line preview)
recent_queue_items: deque = deque(maxlen=5)
recent_queue_lock = threading.Lock()

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

def fetch_context_and_analyze(container_name, container_id, error_line):
    # wait 100ms to allow subsequent logs to flow into docker
    time.sleep(0.1)
    
    client = get_docker_client()
    if not client: return
    
    try:
        raw_logs = client.api.logs(container_id, tail=200, timestamps=False)
        lines = [l for l in raw_logs.decode('utf-8', errors='replace').split('\n') if l]
        
        # Try to find the exact error line in the last 200 lines
        target_idx = -1
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
        
    print(f"[LLM] Analyzing error from {container_name}...")
    investigation, resolution = analyze_error(container_name, error_line, context)
    
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
        print(f"[LLM] Analysis saved for {container_name}")
    finally:
        db.close()

def llm_queue_worker():
    """Single consumer thread — processes one error at a time from the queue."""
    print("[Queue] LLM queue worker started.")
    while True:
        try:
            container_name, container_id, error_line = llm_queue.get(timeout=5)
            print(f"[Queue] Processing: {container_name} ({llm_queue.qsize()} remaining)")
            fetch_context_and_analyze(container_name, container_id, error_line)
        except queue.Empty:
            continue
        except Exception as e:
            print(f"[Queue] Error processing item: {e}")
        finally:
            try:
                llm_queue.task_done()
            except Exception:
                pass

def get_queue_status():
    """Returns the current queue status for the API."""
    with recent_queue_lock:
        preview = list(recent_queue_items)
    return {
        "total": llm_queue.qsize(),
        "recent": preview  # List of {"container": ..., "line": ...}
    }

def monitor_container(container):
    print(f"[Monitor] Started monitoring {container.name}")
    try:
        buffer = ""
        for chunk in container.logs(stream=True, follow=True, timestamps=True, tail=0):
            buffer += chunk.decode('utf-8', errors='replace')
            while '\n' in buffer:
                raw_line, buffer = buffer.split('\n', 1)
                line = raw_line.strip()
                if not line: continue
                
                # Check keywords first to reduce DB queries
                for keyword in ERROR_KEYWORDS:
                    if keyword in line:
                        # Check exclusions only if error keyword matched
                        if is_excluded(container.name, line):
                            break
                        
                        # Enqueue for serial LLM processing
                        llm_queue.put((container.name, container.id, line))
                        with recent_queue_lock:
                            recent_queue_items.appendleft({
                                "container": container.name,
                                "line": line[:120]  # truncate for display
                            })
                        print(f"[Queue] Enqueued error from {container.name} (queue size: {llm_queue.qsize()})")
                        break
    except Exception as e:
        print(f"[Monitor] Stopped monitoring {container.name}: {e}")

def log_monitor_worker():
    client = get_docker_client()
    if not client: 
        print("Cannot start log monitor. No docker client.")
        return

    # Start the single LLM consumer thread
    threading.Thread(target=llm_queue_worker, daemon=True, name="llm-queue-worker").start()

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
            print(f"[Monitor] Error listing containers: {e}")
            
        time.sleep(10)
