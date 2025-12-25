# transcriptProcessing.py
import json
import logging
import os
import shlex
from multiprocessing import process
from pathlib import Path

import subprocess
import paramiko
from dotenv import load_dotenv

from logging_config import setup_logging

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
        check=False # Do not raise CalledProcessError automatically
    )

    if result.returncode != 0:
        error_message = result.stderr.strip()
        if "quota" in error_message.lower() or "limit" in error_message.lower():
            raise GeminiQuotaExceededError(f"Gemini API quota exceeded: {error_message}")
        else:
            raise RuntimeError(f"Gemini CLI error: {error_message}")
    return result.stdout.strip()

class TranscriptProcessor:
    """
    Connects to a remote server to process transcripts using Ollama.
    """
    def __init__(self, model="llama3.1:8b"):
        """
        Initializes the TranscriptProcessor, loading SSH credentials and setting the model.
        """
        load_dotenv(dotenv_path=Path(__file__).resolve().parent / '.env')

        self.ssh_host = os.getenv("SSH_HOST")
        self.ssh_user = os.getenv("SSH_USER")
        self.ssh_password = os.getenv("SSH_PASSWORD")
        self.ssh_port = int(os.getenv("SSH_PORT", 22))
        self.model = model
        logger.info("TranscriptProcessor initialized with model: %s", self.model)

        # build paths to the prompts
        self.BASE_DIR = Path(__file__).resolve().parent
        self.PROMPTS_DIR = self.BASE_DIR / "prompts"

        self._validate_credentials()

    def standard_flow(self, transcript_path: Path):
        # make instance of this class, then feed this method the path to the 
        # transcript and let it run through the full process

        # first build a nice formated version of the script
        self._format_text(transcript_path)

        # next, build the json file with all the metadata  in it.
        self.process_and_save(transcript_path)

    def _validate_credentials(self):
        """
        Validates that all required SSH credentials are present.
        """
        for var_name, var_value in [
            ("SSH_HOST", self.ssh_host),
            ("SSH_USER", self.ssh_user),
            ("SSH_PASSWORD", self.ssh_password)
        ]:
            if not var_value:
                logger.error("Missing required environment variable: %s", var_name)
                raise ValueError(f"Missing required environment variable: {var_name}")

    def _make_client(self):
        """
        Creates and returns a configured Paramiko SSH client.
        """
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
        """
        Runs a command on the remote server and returns stdout.
        """
        logger.debug("Running remote command: %s", cmd)
        client = self._make_client()
        try:
            stdin, stdout, stderr = client.exec_command(cmd)
            # wait until command finishes
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode().strip()
            err = stderr.read().decode().strip()
            if err:
                logger.warning("Remote command stderr: %s", err)
            return out
        finally:
            client.close()

    def _get_prompts_to_process(self):
        """
        Returns a dictionary mapping prompt names to their file paths.
        This is the central place to define which prompts to run.
        """
        BASE_DIR = Path(__file__).resolve().parent
        PROMPTS_DIR = BASE_DIR / "prompts"

        # just add to this dict as I make more prompts
        # set to True if you want the 5x prompt where it choses the winner
        prompt_dict = {
            "outline": (PROMPTS_DIR / "outline_prompt.txt", False),
            "summary": (PROMPTS_DIR / 'summary_prompt.txt', False),
            'thesis': (PROMPTS_DIR / 'thesis_prompt.txt', True),
            'main_passage': (PROMPTS_DIR / 'extract_main_passage.txt', False),
            'title': (PROMPTS_DIR / "title_prompt.txt", True),
            'applications': (PROMPTS_DIR / "applications.txt", False),
            'characters': (PROMPTS_DIR / "characters_mentioned.txt", False),
            'issues': (PROMPTS_DIR / "issues_raised.txt", False),
            'key_topics': (PROMPTS_DIR / "key_topics.txt", False),
            'quotes': (PROMPTS_DIR / "quotes.txt", False),
            'secondary_reference': (PROMPTS_DIR / "secondary_supporting_passages.txt", False),
            'tone': (PROMPTS_DIR / "tone.txt", False),
            'visials': (PROMPTS_DIR / "visuals.txt", False)
        }
        return prompt_dict

    def _execute_prompt(self, transcript_text, prompt_path: Path):
        """
        Formats a prompt with transcript text and gets a response from a remote Ollama model.
        """
        logger.debug('activating _execute_prompt method')
        if not prompt_path.exists():
            logger.error("Prompt file not found at: %s", prompt_path)
            raise FileNotFoundError(f"Prompt file not found at: {prompt_path}")

        prompt_template = prompt_path.read_text(encoding="utf-8")
        final_prompt = prompt_template.format(TRANSCRIPT=transcript_text)

        payload = {
            "model": self.model,
            "prompt": final_prompt,
            "stream": False,  # Important: Get a single response object
        }

        logger.debug(f'payload:\n{payload}')
        json_payload = json.dumps(payload)
        safe_payload = shlex.quote(json_payload)
        cmd = f"curl -s http://localhost:11434/api/generate -d {safe_payload}"
        logger.debug('fixing to _run_remote_cmp')
        response_json = self._run_remote_cmd(cmd)
        logger.debug(f'ok, command has run. response_json:\n{response_json}')

        try:
            response_data = json.loads(response_json)
            response_content = response_data.get("response", "").strip()
            return response_content
        except json.JSONDecodeError:
            logger.error("Could not decode JSON response from Ollama API. Raw response: %s", response_json)
            return None

    def _execute_generative_consolidation(self, transcript_text: str, original_prompt_path: Path, category_name: str):
        """
        Executes a prompt 5 times, then uses a consolidation prompt to pick the best response.
        Returns a dictionary with the 'best' response and 'alternatives'.
        """
        BASE_DIR = Path(__file__).resolve().parent
        PROMPTS_DIR = BASE_DIR / "prompts"
        consolidation_prompt_path = PROMPTS_DIR / "consolidation_prompt.txt"

        if not consolidation_prompt_path.exists():
            logger.error("Consolidation prompt file not found at: %s", consolidation_prompt_path)
            raise FileNotFoundError(f"Consolidation prompt file not found at: {consolidation_prompt_path}")

        responses = []
        logger.info("Generating 5 responses for '%s'...", category_name)
        for i in range(5):
            logger.debug("Generating response %d for '%s'...", i + 1, category_name)
            response = self._execute_prompt(transcript_text, original_prompt_path)
            if response:
                responses.append(response)
            else:
                logger.warning("Failed to generate response %d for '%s'.", i + 1, category_name)

        if not responses:
            logger.error("No responses generated for '%s'. Cannot perform consolidation.", category_name)
            return {"best": None, "alternatives": []}

        # Format the consolidation prompt
        consolidation_template = consolidation_prompt_path.read_text(encoding="utf-8")
        
        # Prepare responses for formatting
        response_placeholders = {f"RESPONSE_{i+1}": responses[i] if i < len(responses) else "" for i in range(5)}
        
        final_consolidation_prompt = consolidation_template.format(
            TRANSCRIPT=transcript_text,
            CATEGORY=category_name,
            **response_placeholders
        )

        logger.info("Selecting best response for '%s'...", category_name)
        payload = {
            "model": self.model,
            "prompt": final_consolidation_prompt,
            "stream": False,
        }
        json_payload = json.dumps(payload)
        safe_payload = shlex.quote(json_payload)
        cmd = f"curl -s http://localhost:11434/api/generate -d {safe_payload}"
        
        choice_response_json = self._run_remote_cmd(cmd)

        try:
            choice_data = json.loads(choice_response_json)
            choice_content = choice_data.get("response", "").strip()
            chosen_index = int(choice_content) - 1
            
            if 0 <= chosen_index < len(responses):
                best_response = responses[chosen_index]
                alternatives = [r for i, r in enumerate(responses) if i != chosen_index]
                logger.info("Best response selected for '%s'.", category_name)
                return {"best": best_response, "alternatives": alternatives}
            else:
                logger.warning("Invalid choice from LLM (%s) for '%s'. Returning first response as best.", choice_content, category_name)
                return {"best": responses[0], "alternatives": responses[1:]}
        except (json.JSONDecodeError, ValueError):
            logger.error("Could not parse LLM choice from consolidation. Raw response: %s. Returning first response as best.", choice_response_json)
            return {"best": responses[0], "alternatives": responses[1:]}

    def _format_text(self, transcript_path):
        '''clean up text into a block, then get llm to insert  paragraphs'''
        if not transcript_path.exists():
            logger.error(f'Transcript file not fout: {transcript_path}')
            raise FileNotFoundError(f'Transcript file not found: {transcript_path}')
        
        transcript_text = transcript_path.read_text(encoding='utf-8')
        transcript_block = " ".join(transcript_text.split())
        transcript_wc = len(transcript_block.split()) # get word count for reference later

        prompt_path = self.PROMPTS_DIR / 'build_paragraphs.txt'
        if not prompt_path.exists():
            logger.error(f'The prompt to format the text block is not at the given path. Exiting.')
            raise FileNotFoundError(f'Prompt file not found: {prompt_path}')
        
        prompt_template = prompt_path.read_text(encoding='utf-8')
        final_prompt = prompt_template.format(TRANSCRIPT=transcript_text)

        logger.info(f'---Processing transcript into paragraphs: {transcript_path.name} using Gemini ---')

        attempt_number = 1
        max_attempts = 5
        attempt_successful = False

        while not attempt_successful:
            if attempt_number > max_attempts:
                logger.error(f'Max attempts reached. Failed to successfully build formatted text block for {transcript_path.name}')
                return

            logger.info(f'Running attempt {attempt_number} / 5...')
            try:
                response_content = _call_gemini(final_prompt)

                if response_content:
                    response_wc = len(response_content.split())
                    ratio = response_wc / transcript_wc
                    within_2_percent = 0.98 <= ratio <= 1.02

                    if within_2_percent:
                        attempt_successful = True
                        logger.info(f'Successfully formatted text block with {ratio:.2f}% difference in word count')
                    else:
                        logger.info(f'Failed to format text block. Ratio was {ratio:.2f}% difference in word count.\nStarting word count: {transcript_wc}\nFormatted word count: {response_wc}')
                        attempt_number += 1
                else:
                    logger.warning(f"Gemini returned no content for {transcript_path.name}. Retrying.")
                    attempt_number += 1
                
            except GeminiQuotaExceededError as e:
                logger.error(f"Gemini quota exceeded: {e}")
                # Decide if you want to retry on quota errors or just stop.
                # For now, we'll stop.
                return
            except Exception as e:
                logger.error(f'Ran into an error trying to format the text block {transcript_path.name}: {e}')
                attempt_number += 1
            
        output_path = transcript_path.with_name(
            transcript_path.stem + "_formatted" + transcript_path.suffix
            )
        logger.info(f"Saving results to {output_path}...")
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(response_content)
        logger.info("Save complete.")

    def process_and_save(self, transcript_path: Path, save_to_json=True):
        """
        Processes a transcript with all defined prompts and saves the result to JSON.
        """
        if not transcript_path.exists():
            logger.error("Transcript file not found: %s", transcript_path)
            raise FileNotFoundError(f"Transcript file not found: {transcript_path}")

        transcript_text = transcript_path.read_text(encoding="utf-8")
        prompts_dict = self._get_prompts_to_process()
        results = {}

        logger.info("--- Processing transcript: %s ---", transcript_path.name)
        for name, (prompt_path, use_generative_consolidation) in prompts_dict.items():
            logger.info("Running prompt: '%s'...", name)
            try:
                if use_generative_consolidation:
                    logger.info("Using generative consolidation for '%s'.", name)
                    response_content = self._execute_generative_consolidation(
                        transcript_text=transcript_text,
                        original_prompt_path=prompt_path,
                        category_name=name
                    )
                else:
                    response_content = self._execute_prompt(
                        transcript_text=transcript_text,
                        prompt_path=prompt_path
                    )
                results[name] = response_content
                logger.info("Finished prompt: '%s'.", name)
            except FileNotFoundError as e:
                logger.error("Skipping prompt '%s' because a file was not found: %s", name, e)
                results[name] = None  # Or some other indicator of failure

        if save_to_json:
            output_path = transcript_path.with_suffix('.json')
            logger.info("Saving results to %s...", output_path)
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            logger.info("Save complete.")

        return results

if __name__ == "__main__":
    # This block will only run when the script is executed directly
    # It's a good way to test the class's functionality.
    setup_logging()
    logging.info(f'\n\n****Beginning transcript processing attempt****')
    try:
        BASE_DIR = Path(__file__).resolve().parent
        TEXT_TEST_PATH = BASE_DIR / 'test.txt'

        # Initialize the processor. The model is set here.
        # You can override the default like this:
        # processor = TranscriptProcessor(model="another-model:latest")
        processor = TranscriptProcessor()
        processor.standard_flow(TEXT_TEST_PATH)
        
        # all_results = processor.process_and_save(
        #     transcript_path=TEXT_TEST_PATH
        # )

        # logger.info("--- Final Results ---")
        # # Pretty-print the final JSON to the log
        # logger.info(json.dumps(all_results, indent=2))

    except FileNotFoundError as e:
        logger.error("A required file was not found: %s", e)
    except ValueError as e:
        logger.error("Configuration Error: %s", e)
    except Exception:
        logger.exception("An unexpected error occurred:")

