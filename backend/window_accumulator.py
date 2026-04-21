import os
import threading
from dataclasses import dataclass, field
from datetime import datetime

ANALYSIS_WINDOW_MINUTES = int(os.getenv("ANALYSIS_WINDOW_MINUTES", 15))

_SEVERITY_RANK = {"FATAL": 4, "CRITICAL": 3, "ERROR": 2}


@dataclass
class FingerprintBucket:
    count: int = 0
    severity: str = "ERROR"
    first_seen: datetime = field(default_factory=datetime.utcnow)
    last_seen: datetime = field(default_factory=datetime.utcnow)
    representative_line: str = ""


class ContainerWindow:
    def __init__(self, container_name: str):
        self.container_name = container_name
        self.window_start: datetime | None = None
        self.fingerprints: dict[str, FingerprintBucket] = {}
        self.total_error_count: int = 0
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def add_error(self, raw_line: str, fingerprint_key: str, severity: str, now: datetime):
        with self._lock:
            is_first = self.total_error_count == 0
            if is_first:
                self.window_start = now

            if fingerprint_key in self.fingerprints:
                bucket = self.fingerprints[fingerprint_key]
                bucket.count += 1
                bucket.last_seen = now
                if _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(bucket.severity, 0):
                    bucket.severity = severity
            else:
                self.fingerprints[fingerprint_key] = FingerprintBucket(
                    count=1,
                    severity=severity,
                    first_seen=now,
                    last_seen=now,
                    representative_line=raw_line,
                )

            self.total_error_count += 1

            if is_first:
                self._arm_timer()

    def _arm_timer(self):
        # Late import breaks the circular dependency with window_evaluator
        from backend import window_evaluator
        self._timer = threading.Timer(
            ANALYSIS_WINDOW_MINUTES * 60,
            window_evaluator.evaluate_and_close,
            args=(self.container_name,),
        )
        self._timer.daemon = True
        self._timer.start()

    def to_snapshot(self) -> dict:
        with self._lock:
            elapsed = (datetime.utcnow() - self.window_start).total_seconds() if self.window_start else 0
            remaining = max(0, ANALYSIS_WINDOW_MINUTES * 60 - elapsed)
            return {
                "container": self.container_name,
                "error_count": self.total_error_count,
                "fingerprint_count": len(self.fingerprints),
                "window_start": self.window_start.isoformat() + "Z" if self.window_start else None,
                "seconds_remaining": int(remaining),
            }


# Module-level state
_windows: dict[str, ContainerWindow] = {}
_global_lock = threading.Lock()


def get_or_create_window(container_name: str) -> ContainerWindow:
    with _global_lock:
        if container_name not in _windows:
            _windows[container_name] = ContainerWindow(container_name)
        return _windows[container_name]


def close_window(container_name: str):
    with _global_lock:
        _windows.pop(container_name, None)


def get_active_windows_snapshot() -> list[dict]:
    with _global_lock:
        names = list(_windows.keys())
    return [_windows[n].to_snapshot() for n in names if n in _windows]
