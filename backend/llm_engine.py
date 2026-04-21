import os
from ollama import Client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

client = Client(host=OLLAMA_BASE_URL)

def analyze_error(container_name: str, error_line: str, context_log: str) -> tuple[str, str, str]:
    prompt = f"""
You are an expert devops engineer. Analyze the following application container error.
Container Name: {container_name}

Error Line:
{error_line}

Surrounding Context (+/- 100ms):
{context_log}

Please provide your response strictly in three sections:
EXECUTIVE_SUMMARY:
<one or two sentences. Start with either "NEEDS INTERVENTION:" or "LIKELY TRANSIENT:" then briefly state what happened and whether action is required.>

INVESTIGATION:
<your analysis of why this error happened based on the context>

RESOLUTION:
<your proposed solution or mitigation>
"""

    try:
        response = client.chat(model=OLLAMA_MODEL, messages=[
            {
                'role': 'user',
                'content': prompt
            }
        ])
        content = response['message']['content']

        executive_summary = ""
        investigation = "Investigation parsing failed."
        resolution = "Resolution parsing failed."

        if "EXECUTIVE_SUMMARY:" in content:
            parts = content.split("EXECUTIVE_SUMMARY:", 1)[1]
            if "INVESTIGATION:" in parts:
                executive_summary = parts.split("INVESTIGATION:")[0].strip()
                rest = parts.split("INVESTIGATION:", 1)[1]
            else:
                executive_summary = parts.strip()
                rest = ""
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
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")
        return f"Failed to contact LLM: {str(e)}", "Please check Ollama connection.", ""
