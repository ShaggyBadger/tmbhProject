# transcriptProcessing.py
import json
import logging
import os
import shlex
from pathlib import Path
import subprocess
import paramiko
from dotenv import load_dotenv

# Initialize logger
logger = logging.getLogger(__name__)

class GeminiQuotaExceededError(Exception):
    """Custom exception for Gemini API quota errors."""
    pass

def _call_gemini(prompt):
    """Runs the Gemini CLI with a given prompt, handling quota errors."""
    result = subprocess.run(
        ["gemini", "-p", prompt],
        capture_output=True,
        text=True,
        check=False  # Do not raise CalledProcessError automatically
    )

    if result.returncode != 0:
        error_message = result.stderr.strip()
        if "quota" in error_message.lower() or "limit" in error_message.lower():
            raise GeminiQuotaExceededError(f"Gemini API quota exceeded: {error_message}")
        else:
            raise RuntimeError(f"Gemini CLI error: {error_message}")
    return result.stdout.strip()

class GeminiProcessor:
    """
    Processes raw transcripts to format them using the Gemini API.
    """
    def __init__(self):
        self.BASE_DIR = Path(__file__).resolve().parent
        self.PROMPTS_DIR = self.BASE_DIR / "prompts"
        self.gemini_status = 'good'
        logger.info("GeminiProcessor initialized.")

    def format_transcript(self, transcript_path: Path):
        """
        Cleans up a transcript file and uses Gemini to insert paragraphs.
        Returns the status of the operation.
        """
        if not transcript_path.exists():
            logger.error(f'Transcript file not found: {transcript_path}')
            raise FileNotFoundError(f'Transcript file not found: {transcript_path}')

        transcript_text = transcript_path.read_text(encoding='utf-8')
        transcript_block = " ".join(transcript_text.split())
        transcript_wc = len(transcript_block.split())

        prompt_path = self.PROMPTS_DIR / 'build_paragraphs.txt'
        if not prompt_path.exists():
            logger.error('The prompt to format the text block is not at the given path. Exiting.')
            raise FileNotFoundError(f'Prompt file not found: {prompt_path}')

        prompt_template = prompt_path.read_text(encoding='utf-8')
        final_prompt = prompt_template.format(TRANSCRIPT=transcript_text)

        logger.info(f'--- Processing transcript into paragraphs: {transcript_path.name} using Gemini ---')

        # Retry logic
        max_attempts = 5
        for attempt_number in range(1, max_attempts + 1):
            logger.info(f'Running attempt {attempt_number} / {max_attempts}...')
            try:
                response_content = _call_gemini(final_prompt)

                if response_content:
                    response_wc = len(response_content.split())
                    ratio = response_wc / transcript_wc
                    if 0.98 <= ratio <= 1.02:
                        logger.info(f'Successfully formatted text block with {ratio:.2f} ratio in word count')
                        output_path = transcript_path.with_name(transcript_path.stem + "_formatted" + transcript_path.suffix)
                        logger.info(f"Saving results to {output_path}...")
                        with open(output_path, 'w', encoding='utf-8') as f:
                            f.write(response_content)
                        logger.info("Save complete.")
                        self.gemini_status = 'good'
                        return self.gemini_status
                    else:
                        logger.warning(f'Word count ratio failed. Ratio was {ratio:.2f}. Expected between 0.98 and 1.02.')
                else:
                    logger.warning(f"Gemini returned no content for {transcript_path.name}.")

            except GeminiQuotaExceededError as e:
                logger.error(f"Gemini quota exceeded: {e}")
                self.gemini_status = 'out of quota'
                return self.gemini_status
            except Exception as e:
                logger.error(f'Error on attempt {attempt_number} for {transcript_path.name}: {e}')

        logger.error(f'Max attempts reached. Failed to format {transcript_path.name}')
        self.gemini_status = 'error'
        return self.gemini_status

class OllamaProcessor:
    """
    Connects to a remote server to process transcripts using Ollama.
    """
    def __init__(self, model="llama3.1:8b"):
        load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env')
        self.ssh_host = os.getenv("SSH_HOST")
        self.ssh_user = os.getenv("SSH_USER")
        self.ssh_password = os.getenv("SSH_PASSWORD")
        self.ssh_port = int(os.getenv("SSH_PORT", 22))
        self.model = model
        self.BASE_DIR = Path(__file__).resolve().parent
        self.PROMPTS_DIR = self.BASE_DIR / "prompts"
        self._validate_credentials()
        logger.info("OllamaProcessor initialized with model: %s", self.model)

    def _validate_credentials(self):
        for var_name, var_value in [
            ("SSH_HOST", self.ssh_host),
            ("SSH_USER", self.ssh_user),
            ("SSH_PASSWORD", self.ssh_password)
        ]:
            if not var_value:
                raise ValueError(f"Missing required environment variable: {var_name}")

    def _make_client(self):
        client = paramiko.SSHClient()
        client.load_system_host_keys()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.ssh_host,
            username=self.ssh_user,
            password=self.ssh_password,
            port=self.ssh_port,
            allow_agent=False,
            look_for_keys=False,
            timeout=10,
        )
        return client

    def _run_remote_cmd(self, cmd: str):
        logger.debug("Running remote command: %s", cmd)
        client = self._make_client()
        try:
            stdin, stdout, stderr = client.exec_command(cmd)
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if err:
                logger.warning("Remote command stderr: %s", err)
            return out
        finally:
            client.close()

    def _get_prompts_to_process(self):
        prompt_files = {
            "outline": "outline_prompt.txt", "summary": "summary_prompt.txt",
            "thesis": "thesis_prompt.txt", "main_passage": "extract_main_passage.txt",
            "title": "title_prompt.txt", "applications": "applications.txt",
            "characters": "characters_mentioned.txt", "issues": "issues_raised.txt",
            "key_topics": "key_topics.txt", "quotes": "quotes.txt",
            "secondary_reference": "secondary_supporting_passages.txt",
            "tone": "tone.txt", "visials": "visuals.txt"
        }
        use_consolidation = {"thesis", "title"}
        
        prompt_dict = {}
        for name, filename in prompt_files.items():
            prompt_dict[name] = (self.PROMPTS_DIR / filename, name in use_consolidation)
        return prompt_dict

    def _execute_prompt(self, transcript_text, prompt_path: Path):
        if not prompt_path.exists():
            raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding="utf-8")
        final_prompt = prompt_template.format(TRANSCRIPT=transcript_text)
        payload = {"model": self.model, "prompt": final_prompt, "stream": False}
        json_payload = json.dumps(payload)
        safe_payload = shlex.quote(json_payload)
        cmd = f"curl -s http://localhost:11434/api/generate -d {safe_payload}"
        
        response_json = self._run_remote_cmd(cmd)
        try:
            response_data = json.loads(response_json)
            return response_data.get("response", "").strip()
        except json.JSONDecodeError:
            logger.error("Could not decode JSON from Ollama. Raw response: %s", response_json)
            return None

    def _execute_generative_consolidation(self, transcript_text: str, original_prompt_path: Path, category_name: str):
        consolidation_prompt_path = self.PROMPTS_DIR / "consolidation_prompt.txt"
        if not consolidation_prompt_path.exists():
            raise FileNotFoundError(f"Consolidation prompt file not found: {consolidation_prompt_path}")

        responses = [self._execute_prompt(transcript_text, original_prompt_path) for _ in range(5)]
        responses = [r for r in responses if r]

        if not responses:
            logger.error("No responses generated for '%s'. Cannot consolidate.", category_name)
            return {"best": None, "alternatives": []}

        consolidation_template = consolidation_prompt_path.read_text(encoding="utf-8")
        response_placeholders = {f"RESPONSE_{i+1}": responses[i] if i < len(responses) else "" for i in range(5)}
        final_consolidation_prompt = consolidation_template.format(
            TRANSCRIPT=transcript_text, CATEGORY=category_name, **response_placeholders
        )
        
        payload = {"model": self.model, "prompt": final_consolidation_prompt, "stream": False}
        json_payload = json.dumps(payload)
        safe_payload = shlex.quote(json_payload)
        cmd = f"curl -s http://localhost:11434/api/generate -d {safe_payload}"
        choice_response_json = self._run_remote_cmd(cmd)

        try:
            choice_data = json.loads(choice_response_json)
            choice_content = choice_data.get("response", "").strip()
            chosen_index = int(choice_content) - 1
            if 0 <= chosen_index < len(responses):
                best = responses.pop(chosen_index)
                return {"best": best, "alternatives": responses}
        except (json.JSONDecodeError, ValueError, IndexError):
            logger.warning("Could not parse LLM choice. Defaulting to first response.")
        
        return {"best": responses[0], "alternatives": responses[1:]} if responses else {"best": None, "alternatives": []}

    def generate_metadata(self, transcript_path: Path, save_to_json=True):
        if not transcript_path.exists():
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

        transcript_text = transcript_path.read_text(encoding="utf-8")
        prompts_dict = self._get_prompts_to_process()
        results = {}

        logger.info("--- Processing transcript with Ollama: %s ---", transcript_path.name)
        for name, (prompt_path, use_consolidation) in prompts_dict.items():
            logger.info("Running prompt: '%s'...", name)
            try:
                if use_consolidation:
                    response_content = self._execute_generative_consolidation(transcript_text, prompt_path, name)
                else:
                    response_content = self._execute_prompt(transcript_text, prompt_path)
                results[name] = response_content
            except FileNotFoundError as e:
                logger.error("Skipping prompt '%s': %s", name, e)
                results[name] = None

        if save_to_json:
            output_path = transcript_path.with_suffix('.json')
            logger.info("Saving Ollama results to %s...", output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            logger.info("Save complete.")

        return results

if __name__ == "__main__":
    from logging_config import setup_logging
    setup_logging()
    logging.info(f'\n\n****Beginning transcript processing test****')
    try:
        BASE_DIR = Path(__file__).resolve().parent
        # NOTE: This test now expects a 'test_formatted.txt' for the Ollama part.
        TEST_TRANSCRIPT_PATH = BASE_DIR / 'test.txt'

        # Test GeminiProcessor
        logger.info("--- Testing GeminiProcessor ---")
        gemini_proc = GeminiProcessor()
        gemini_proc.format_transcript(TEST_TRANSCRIPT_PATH)
        
        FORMATTED_TEXT_PATH = TEST_TRANSCRIPT_PATH.with_name('test_formatted.txt')

        # Test OllamaProcessor (if the formatted file was created)
        if FORMATTED_TEXT_PATH.exists():
            logger.info("\n--- Testing OllamaProcessor ---")
            ollama_proc = OllamaProcessor()
            ollama_proc.generate_metadata(FORMATTED_TEXT_PATH)
        else:
            logger.warning("Formatted transcript not found. Skipping OllamaProcessor test.")

    except FileNotFoundError as e:
        logger.error("A required file was not found: %s", e)
    except ValueError as e:
        logger.error("Configuration Error: %s", e)
    except Exception:
        logger.exception("An unexpected error occurred:")

