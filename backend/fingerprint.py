import re

_SEVERITY_MAP = {
    "FATAL": 4,
    "CRITICAL": 3,
    "ERROR": 2,
    "Exception": 1,
}

_NORMALIZATION_STEPS = [
    # Leading Docker/ISO timestamps: 2024-01-01T12:34:56.789Z or 2024-01-01 12:34:56
    (re.compile(r'^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[\.\d]*Z?\s*'), ''),
    # UUIDs before generic hex
    (re.compile(r'[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}'), '<UUID>'),
    # 0x-prefixed hex
    (re.compile(r'0x[0-9a-fA-F]+'), '<HEX>'),
    # Long standalone hex strings (8+ chars) — e.g. container IDs
    (re.compile(r'\b[0-9a-fA-F]{8,}\b'), '<HEX>'),
    # IPv4 addresses before standalone numbers
    (re.compile(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b'), '<IP>'),
    # file.py:42 or module.go:123 style refs
    (re.compile(r'\b\w+\.\w{1,6}:\d+\b'), '<FILE:LINE>'),
    # Standalone integers
    (re.compile(r'\b\d+\b'), '<N>'),
]


def fingerprint(line: str) -> str:
    result = line
    for pattern, replacement in _NORMALIZATION_STEPS:
        result = pattern.sub(replacement, result)
    return ' '.join(result.lower().split())


def classify_severity(line: str) -> str:
    best = "ERROR"
    best_rank = 0
    for keyword, rank in _SEVERITY_MAP.items():
        if keyword in line and rank > best_rank:
            best = keyword if keyword != "Exception" else "ERROR"
            best_rank = rank
    return best
