import os
import json
import logging
from datetime import datetime, timedelta

from backend.window_accumulator import close_window, FingerprintBucket
from backend.database import SessionLocal, AnalysisResult, ErrorWindow, KnownFingerprint

log = logging.getLogger(__name__)

RATE_SPIKE_MULTIPLIER    = float(os.getenv("RATE_SPIKE_MULTIPLIER", 3))
RATE_SPIKE_ABSOLUTE      = int(os.getenv("RATE_SPIKE_ABSOLUTE", 20))
SUSTAINED_REPEAT_THRESHOLD = int(os.getenv("SUSTAINED_REPEAT_THRESHOLD", 10))
FINGERPRINT_HISTORY_HOURS  = int(os.getenv("FINGERPRINT_HISTORY_HOURS", 24))
MIN_BASELINE_WINDOWS       = int(os.getenv("MIN_BASELINE_WINDOWS", 2))


def evaluate_and_close(container_name: str):
    from backend import window_accumulator
    window = window_accumulator._windows.get(container_name)
    if window is None:
        return

    with window._lock:
        fingerprints: dict[str, FingerprintBucket] = dict(window.fingerprints)
        window_start: datetime = window.window_start
        total_error_count: int = window.total_error_count

    window_end = datetime.utcnow()
    close_window(container_name)

    if total_error_count == 0:
        return

    db = SessionLocal()
    try:
        _persist_window(db, container_name, window_start, window_end, total_error_count, fingerprints)

        signals = _check_signals(db, container_name, window_start, window_end, total_error_count, fingerprints)

        _upsert_known_fingerprints(db, container_name, fingerprints, window_end)
        db.commit()

        if not signals:
            log.info("[Evaluator] No signals for %s window ending %s", container_name, window_end)
            return

        log.info("[Evaluator] Signals %s for %s — calling LLM", signals, container_name)
        cluster_summary = build_cluster_summary(
            container_name, window_start, window_end, signals, fingerprints, total_error_count
        )

        from backend.llm_engine import analyze_window
        investigation, resolution, executive_summary = analyze_window(
            container_name, window_start, window_end, signals, cluster_summary
        )

        ar = AnalysisResult(
            container_name=container_name,
            timestamp=window_end,
            error_line=_short_summary(signals, fingerprints, total_error_count),
            context_log=cluster_summary,
            llm_executive_summary=executive_summary,
            llm_investigation=investigation,
            llm_resolution=resolution,
            window_start=window_start,
            window_end=window_end,
            signal_types=",".join(signals),
            error_count=total_error_count,
            fingerprint_count=len(fingerprints),
        )
        db.add(ar)
        db.commit()
        log.info("[Evaluator] Analysis saved for %s", container_name)

    except Exception as e:
        log.exception("[Evaluator] Error processing window for %s: %s", container_name, e)
    finally:
        db.close()


def _persist_window(db, container_name, window_start, window_end, error_count, fingerprints):
    fp_counts = {fp: b.count for fp, b in fingerprints.items()}
    ew = ErrorWindow(
        container_name=container_name,
        window_start=window_start,
        window_end=window_end,
        error_count=error_count,
        fingerprints_json=json.dumps(fp_counts),
    )
    db.add(ew)


def _check_signals(db, container_name, window_start, window_end, total_count, fingerprints) -> list[str]:
    signals = []

    # Rate spike
    from sqlalchemy import desc
    past = (
        db.query(ErrorWindow)
        .filter(ErrorWindow.container_name == container_name, ErrorWindow.window_end < window_end)
        .order_by(desc(ErrorWindow.window_end))
        .limit(MIN_BASELINE_WINDOWS)
        .all()
    )
    if len(past) < MIN_BASELINE_WINDOWS:
        if total_count >= RATE_SPIKE_ABSOLUTE:
            signals.append("RATE_SPIKE")
    else:
        avg = sum(w.error_count for w in past) / len(past)
        if avg > 0 and total_count >= RATE_SPIKE_MULTIPLIER * avg:
            signals.append("RATE_SPIKE")
        elif avg == 0 and total_count >= RATE_SPIKE_ABSOLUTE:
            signals.append("RATE_SPIKE")

    # New fingerprint
    horizon = window_end - timedelta(hours=FINGERPRINT_HISTORY_HOURS)
    for fp_key in fingerprints:
        existing = (
            db.query(KnownFingerprint)
            .filter(
                KnownFingerprint.container_name == container_name,
                KnownFingerprint.fingerprint == fp_key,
                KnownFingerprint.last_seen >= horizon,
            )
            .first()
        )
        if existing is None:
            signals.append("NEW_FINGERPRINT")
            break

    # FATAL/CRITICAL
    for bucket in fingerprints.values():
        if bucket.severity in ("FATAL", "CRITICAL"):
            signals.append("FATAL_CRITICAL")
            break

    # Sustained repetition
    for bucket in fingerprints.values():
        if bucket.count >= SUSTAINED_REPEAT_THRESHOLD:
            signals.append("SUSTAINED_REPETITION")
            break

    return signals


def _upsert_known_fingerprints(db, container_name, fingerprints, now):
    for fp_key, bucket in fingerprints.items():
        existing = (
            db.query(KnownFingerprint)
            .filter(
                KnownFingerprint.container_name == container_name,
                KnownFingerprint.fingerprint == fp_key,
            )
            .first()
        )
        if existing:
            existing.last_seen = now
        else:
            db.add(KnownFingerprint(
                container_name=container_name,
                fingerprint=fp_key,
                first_seen=bucket.first_seen,
                last_seen=now,
            ))


def _short_summary(signals: list[str], fingerprints: dict, total_count: int) -> str:
    top = sorted(fingerprints.items(), key=lambda x: x[1].count, reverse=True)
    top_fp = top[0][0] if top else "unknown"
    return f"{total_count} errors · {len(fingerprints)} clusters · signals: {', '.join(signals)} · top: {top_fp}"


def build_cluster_summary(
    container_name: str,
    window_start: datetime,
    window_end: datetime,
    signals: list[str],
    fingerprints: dict[str, FingerprintBucket],
    total_count: int,
) -> str:
    lines = [
        f"Window: {window_start.strftime('%H:%MZ')} → {window_end.strftime('%H:%MZ')}",
        f"Container: {container_name} | Total errors: {total_count} | Signals: {', '.join(signals)}",
        "",
        "Fingerprint clusters:",
    ]
    sorted_fps = sorted(fingerprints.items(), key=lambda x: x[1].count, reverse=True)
    for fp_key, bucket in sorted_fps:
        lines.append(f"  [{fp_key}] × {bucket.count} ({bucket.severity})"
                     f" — first seen {bucket.first_seen.strftime('%H:%M:%S')}")
        lines.append(f"    Example: {bucket.representative_line}")
    return "\n".join(lines)
