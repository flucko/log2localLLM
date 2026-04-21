import os
import time
import threading
import docker
from datetime import datetime
from backend.database import SessionLocal, ExclusionRule
from backend.fingerprint import fingerprint, classify_severity
from backend.window_accumulator import get_or_create_window, get_active_windows_snapshot

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


def get_queue_status():
    return {"active_windows": get_active_windows_snapshot()}


def monitor_container(container):
    print(f"[Monitor] Started monitoring {container.name}")
    try:
        buffer = ""
        for chunk in container.logs(stream=True, follow=True, timestamps=True, tail=0):
            buffer += chunk.decode('utf-8', errors='replace')
            while '\n' in buffer:
                raw_line, buffer = buffer.split('\n', 1)
                line = raw_line.strip()
                if not line:
                    continue

                for keyword in ERROR_KEYWORDS:
                    if keyword in line:
                        if is_excluded(container.name, line):
                            break
                        severity = classify_severity(line)
                        fp_key = fingerprint(line)
                        window = get_or_create_window(container.name)
                        window.add_error(line, fp_key, severity, datetime.utcnow())
                        break
    except Exception as e:
        print(f"[Monitor] Stopped monitoring {container.name}: {e}")


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
            print(f"[Monitor] Error listing containers: {e}")

        time.sleep(10)
