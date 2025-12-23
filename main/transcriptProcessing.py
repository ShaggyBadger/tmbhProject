# transcriptProcessing_remote.py
import paramiko
from pathlib import Path
from dotenv import load_dotenv
import os
import shlex
import json

# -------------------------
# Load SSH credentials from .env
# -------------------------
load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env')

SSH_HOST = os.getenv("SSH_HOST")
SSH_USER = os.getenv("SSH_USER")
SSH_PASSWORD = os.getenv("SSH_PASSWORD")
SSH_PORT = int(os.getenv("SSH_PORT", 22))

# Validate env
for var_name, var_value in [("SSH_HOST", SSH_HOST), ("SSH_USER", SSH_USER), ("SSH_PASSWORD", SSH_PASSWORD)]:
    if not var_value:
        raise ValueError(f"Missing required environment variable: {var_name}")

# -------------------------
# SSH helper functions
# -------------------------
def _make_client():
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=SSH_HOST,
        username=SSH_USER,
        password=SSH_PASSWORD,
        port=SSH_PORT,
        allow_agent=False,
        look_for_keys=False,
        timeout=10,
    )
    return client

def run_remote_cmd(cmd: str):
    """Run a remote command and wait until it completes, returning stdout."""
    client = _make_client()
    try:
        stdin, stdout, stderr = client.exec_command(cmd)
        # wait until command finishes
        exit_status = stdout.channel.recv_exit_status()
        out = stdout.read().decode().strip()
        err = stderr.read().decode().strip()
        if err:
            print("[stderr]", err)
        return out
    finally:
        client.close()

# -------------------------
# Main logic
# -------------------------

# Read the content from the text file
try:
    # Get directory of THIS script
    BASE_DIR = Path(__file__).resolve().parent

    # prompts/whatever.txt (same directory as this script)
    PROMPT_PATH = BASE_DIR / "prompts" / "outline_prompt.txt"
    TEXT_TEST_PATH = BASE_DIR / 'test.txt'

    prompt_template = PROMPT_PATH.read_text(encoding="utf-8")
    transcript_text = TEXT_TEST_PATH.read_text(encoding='utf-8')

    # Inject transcript into prompt
    final_prompt = prompt_template.format(
        TRANSCRIPT=transcript_text
    )

    # text_to_summarize = Path("main/test.txt").read_text()
    # prompt = Path('main/thesis_prompt.txt').read_text()
except FileNotFoundError:
    print("Error: main/test.txt not found.")
    exit()

MODEL = "llama3.1:8b"

# Create the JSON payload for the Ollama API
payload = {
    "model": MODEL,
    "prompt": final_prompt,
    "stream": False,  # Important: Get a single response object
}
json_payload = json.dumps(payload)

# Quote the payload for safe transport over the remote shell
safe_payload = shlex.quote(json_payload)

# Build the remote command to call the Ollama API using curl
# The -s flag silences curl's progress meter
cmd = f"curl -s http://localhost:11434/api/generate -d {safe_payload}"

# Run remotely and capture the JSON response
response_json = run_remote_cmd(cmd)

# Parse the JSON response and extract the summary
try:
    response_data = json.loads(response_json)
    summary = response_data.get("response", "").strip()
    print("Summary:", summary)
except json.JSONDecodeError:
    print("Error: Could not decode JSON response from Ollama API.")
    print("Raw response:", response_json)
