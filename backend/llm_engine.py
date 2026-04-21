import os
from datetime import datetime
from ollama import Client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

client = Client(host=OLLAMA_BASE_URL)


def _parse_llm_response(content: str) -> tuple[str, str, str]:
    executive_summary = ""
    investigation = "Investigation parsing failed."
    resolution = "Resolution parsing failed."
    rest = ""

    if "EXECUTIVE_SUMMARY:" in content:
        parts = content.split("EXECUTIVE_SUMMARY:", 1)[1]
        if "INVESTIGATION:" in parts:
            executive_summary = parts.split("INVESTIGATION:")[0].strip()
            rest = parts.split("INVESTIGATION:", 1)[1]
        else:
            executive_summary = parts.strip()
    elif "INVESTIGATION:" in content:
        rest = content.split("INVESTIGATION:", 1)[1]
    else:
        rest = content

    if rest and "RESOLUTION:" in rest:
        investigation = rest.split("RESOLUTION:")[0].strip()
        resolution = rest.split("RESOLUTION:", 1)[1].strip()
    elif rest:
        investigation = rest.strip()

    return investigation, resolution, executive_summary


def analyze_window(
    container_name: str,
    window_start: datetime,
    window_end: datetime,
    signals: list[str],
    cluster_summary: str,
) -> tuple[str, str, str]:
    prompt = f"""You are an expert DevOps engineer performing batch error analysis.

Container: {container_name}
Window: {window_start.strftime('%Y-%m-%dT%H:%MZ')} → {window_end.strftime('%Y-%m-%dT%H:%MZ')}
Anomaly signals detected: {', '.join(signals)}

Error cluster summary:
{cluster_summary}

Analyze this error window and respond in exactly three sections:

EXECUTIVE_SUMMARY:
<One or two sentences. Begin with "NEEDS INTERVENTION:" or "LIKELY TRANSIENT:". State which signals fired and what the dominant failure pattern is.>

INVESTIGATION:
<Analysis of why these error clusters occurred, noting any patterns, escalations, or correlations across fingerprints.>

RESOLUTION:
<Concrete steps to investigate or remediate the dominant issues, prioritised by signal severity.>
"""

    try:
        response = client.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
        return _parse_llm_response(response["message"]["content"])
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")
        return f"Failed to contact LLM: {str(e)}", "Please check Ollama connection.", ""
