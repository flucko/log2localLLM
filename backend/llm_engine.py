import os
from ollama import Client

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:e4b")

client = Client(host=OLLAMA_BASE_URL)

def analyze_error(container_name: str, error_line: str, context_log: str) -> tuple[str, str]:
    prompt = f"""
You are an expert devops engineer. Analyze the following application container error.
Container Name: {container_name}

Error Line:
{error_line}

Surrounding Context (+/- 100ms):
{context_log}

Please provide your response strictly in two sections:
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
        
        # Simple extraction
        investigation = "Investigation parsing failed."
        resolution = "Resolution parsing failed."
        
        if "INVESTIGATION:" in content and "RESOLUTION:" in content:
            parts = content.split("RESOLUTION:")
            inv_part = parts[0].split("INVESTIGATION:")[1].strip()
            res_part = parts[1].strip()
            investigation = inv_part
            resolution = res_part
        else:
            investigation = content # fallback
            resolution = "Please see investigation."

        return investigation, resolution
    except Exception as e:
        print(f"Error communicating with Ollama: {e}")
        return f"Failed to contact LLM: {str(e)}", "Please check Ollama connection."
