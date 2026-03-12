import sys
import time
import logging
import re
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
)

# Ensure the 'main' directory is in sys.path
main_dir = Path(__file__).resolve().parents[2]
if str(main_dir) not in sys.path:
    sys.path.insert(0, str(main_dir))

from processor.services.database import PipelineDatabase
from processor.services.initializer import PipelineInitializer
from processor.services.reorganizer import PodcastReorganizer
from processor.config import config
from processor.models import JobData
from joshlib.gemini import GeminiClient  # Import GeminiClient and GeminiResult
from joshlib.ollama import OllamaClient  # Import OllamaClient and OllamaResult

console = Console()


class PipelineController:
    """Manages the TUI for the editing pipeline with a Tactical Terminal aesthetic."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initializing PipelineController.")

        # Silence noisy libraries
        logging.getLogger("paramiko").setLevel(logging.WARNING)

        self.db = PipelineDatabase()
        self.initializer = PipelineInitializer(self.db)
        self.reorganizer = PodcastReorganizer(self.db)

        # Initialize specialized clients
        self.gemini_client = GeminiClient()
        self.ollama_client = OllamaClient(
            model="llama3.2:3b", num_ctx=16384, temperature=0.1
        )
        self.eval_client = OllamaClient(
            model="llama3.2:3b", num_ctx=16384, temperature=0.4
        )

        # Metadata defaults to Ollama
        self.metadata_llm_type = "ollama"
        self.metadata_llm_client = self.ollama_client

        self._metadata_fields_to_process = {
            "primary_text": Path(__file__).parent
            / "prompts/metadata/extract-primary-text.txt",
            "thesis": Path(__file__).parent / "prompts/metadata/extract-thesis.txt",
            "outline": Path(__file__).parent / "prompts/metadata/extract-outline.txt",
            "summary": Path(__file__).parent / "prompts/metadata/extract-summary.txt",
            "tone": Path(__file__).parent / "prompts/metadata/extract-tone.txt",
            "keywords": Path(__file__).parent / "prompts/metadata/extract-keywords.txt",
            "quotes": Path(__file__).parent / "prompts/metadata/extract-quotes.txt",
            "audience": Path(__file__).parent / "prompts/metadata/extract-audience.txt",
            "takeaways": Path(__file__).parent
            / "prompts/metadata/extract-takeaways.txt",
        }

    def start(self):
        """Entry point for the editing pipeline."""
        console.clear()
        console.print(
            Panel(
                "PODCAST EDITING - INITIALIZING TACTICAL DATA STREAM",
                style=config.header,
                border_style=config.panel_border,
            )
        )

        # Step 1: Initialization Scan with Rich Spinner
        with console.status(
            f"[{config.primary}]SCANNING JOB DIRECTORIES...[/]",
            spinner=config.spinner_type,
            spinner_style=config.spinner_color,
        ) as status:
            self.initializer.sync_all_episodes(status=status)

        console.print(
            f"[{config.success}]DATA SYNC COMPLETE - SECURE CONNECTION ESTABLISHED[/]"
        )
        console.input(f"\n[{config.info}]PRESS ENTER TO ACCESS INTERFACE...[/]")

        # Step 2: Enter the editing menu
        self.main_menu()

    def main_menu(self):
        """Rich TUI editing menu."""
        while True:
            console.clear()
            console.print(
                Panel(
                    "TACTICAL PODCAST PROCESSOR - MAIN INTERFACE",
                    style=config.header,
                    border_style=config.panel_border,
                )
            )

            table = Table(show_header=False, box=None)
            table.add_row(f"[{config.primary}]1.[/] DEPLOY SELECTION MODULE")
            table.add_row(f"[{config.warning}]2.[/] MANUAL FAILURE REVIEW (MANUSCRIPT)")
            table.add_row(f"[{config.warning}]3.[/] REORGANIZE UNKNOWN SEASONS")
            table.add_row(f"[{config.warning}]Q.[/] ABORT TO BASE")

            console.print(table)

            choice = (
                console.input(f"\n[{config.secondary}]EXECUTE COMMAND > [/]")
                .strip()
                .lower()
            )

            if choice == "1":
                self.select_episode()
            elif choice == "2":
                self._manual_failure_review()
            elif choice == "3":
                self.reorganizer.start()
            elif choice == "q":
                break

    def _manual_failure_review(self):
        """Identifies and allows manual review of manuscript failures."""
        self.logger.info("Initiating manual failure review scan.")
        console.clear()
        console.print(
            Panel(
                "MANUAL FAILURE REVIEW - SCANNING ASSETS...",
                style=config.header,
                border_style=config.panel_border,
            )
        )

        all_episodes = self.db.get_completed_episodes()
        failed_episodes = []

        with console.status(
            f"[{config.primary}]SCANNING JOB DATA FOR FAILURES...[/]",
            spinner=config.spinner_type,
            spinner_style=config.spinner_color,
        ):
            for ep in all_episodes:
                ep_dir = self.db.get_episode_directory(ep.id)
                if ep_dir:
                    job_data = self.db.load_job_data(ep_dir)
                    if job_data.manuscript_is_failure:
                        self.logger.info(
                            f"Detected failure for episode: {ep.title} (ID: {ep.id})"
                        )
                        failed_episodes.append((ep, job_data, ep_dir))

        if not failed_episodes:
            self.logger.info("No manuscript failures found during scan.")
            console.print(
                f"[{config.success}]NO MANUSCRIPT FAILURES DETECTED. ALL SYSTEMS NOMINAL.[/]"
            )
            console.input("\nCONTINUE...")
            return

        self.logger.info(f"Found {len(failed_episodes)} failures for review.")
        total_fails = len(failed_episodes)
        for idx, (ep, job_data, ep_dir) in enumerate(failed_episodes, start=1):
            console.clear()
            console.print(
                Panel(
                    f"FAILURE REVIEW [{idx}/{total_fails}]: {ep.title}",
                    style=config.warning,
                    border_style=config.panel_border,
                )
            )

            # Calculate stats for display
            original_text = ""
            if job_data.paragraphs:
                original_text = "\n\n".join(
                    [p["original"] for p in job_data.paragraphs]
                )

            orig_wc = len(original_text.split()) if original_text else 0
            manu_wc = len(job_data.manuscript.split()) if job_data.manuscript else 0
            ratio = manu_wc / orig_wc if orig_wc > 0 else 0

            stats_table = Table(title="ASSET STATS", show_header=True, box=None)
            stats_table.add_column("METRIC", style=config.primary)
            stats_table.add_column("VALUE")
            stats_table.add_row("ORIGINAL WORD COUNT", str(orig_wc))
            stats_table.add_row("MANUSCRIPT WORD COUNT", str(manu_wc))
            stats_table.add_row("CURRENT RATIO", f"{ratio:.2f}")
            stats_table.add_row(
                "FAILURE REASON",
                f"[{config.error}]{job_data.manuscript_failure_reason}[/]",
            )

            console.print(stats_table)

            if job_data.manuscript_eval:
                console.print(f"\n[{config.secondary}]LATEST EVALUATION REPORT:[/]")
                # Trim long reports for display
                report = job_data.manuscript_eval
                if len(report) > 1000:
                    report = report[:1000] + "..."
                console.print(
                    Panel(report, style=config.info, border_style=config.panel_border)
                )

            console.print(f"\n[{config.primary}]OPTIONS:[/]")
            console.print(f"[{config.success}]1.[/] ACCEPT AS-IS (Clear Failure Flag)")
            console.print(f"[{config.warning}]2.[/] RE-RUN POLISH (Stage 6)")
            console.print(f"[{config.secondary}]S.[/] SKIP FOR NOW")
            console.print(f"[{config.error}]Q.[/] ABORT REVIEW")

            choice = ""
            while choice not in ["1", "2", "s", "q"]:
                choice = (
                    console.input(f"\n[{config.secondary}]SELECT RESPONSE > [/]")
                    .strip()
                    .lower()
                )

            if choice == "1":
                job_data.manuscript_is_failure = False
                job_data.manuscript_failure_reason = None
                self.db.save_job_data(ep_dir, job_data)
                console.print(
                    f"[{config.success}]ASSET ACCEPTED. FAILURE FLAG REMOVED.[/]"
                )
                time.sleep(1)
            elif choice == "2":
                # Clear current manuscript to trigger re-run
                job_data.manuscript = None
                job_data.manuscript_is_failure = False
                job_data.manuscript_failure_reason = None
                self.db.save_job_data(ep_dir, job_data)

                console.print(f"[{config.warning}]TRIGGERING STAGE 6 RE-RUN...[/]")
                status, message = self._perform_manuscript_assembly(
                    ep_dir, job_data, ep
                )

                if status == "success":
                    console.print(f"[{config.success}]RE-RUN COMPLETE: {message}[/]")
                    # Also re-run evaluation if it was successful
                    self._perform_manuscript_evaluation(ep_dir, job_data, ep)
                else:
                    console.print(f"[{config.error}]RE-RUN FAILED: {message}[/]")
                console.input("\nPRESS ENTER TO CONTINUE...")
            elif choice == "s":
                continue
            elif choice == "q":
                break

    def select_episode(self):
        """Display tactical selection modes."""
        while True:
            console.clear()
            console.print(
                Panel(
                    "ASSET SELECTION MODULE - SELECT TARGETING MODE",
                    style=config.header,
                    border_style=config.panel_border,
                )
            )

            menu = Table(show_header=False, box=None)
            menu.add_row(f"[{config.primary}]1.[/] SINGLE ASSET (BY ID)")
            menu.add_row(f"[{config.primary}]2.[/] ASSET RANGE (START_ID - END_ID)")
            menu.add_row(f"[{config.primary}]3.[/] DIVISIONAL SYNC (BY SEASON)")
            menu.add_row(f"[{config.primary}]4.[/] TOTAL DEPLOYMENT (ALL COMPLETED)")
            menu.add_row(f"[{config.primary}]5.[/] IN PROGRESS (BY STATUS)")
            menu.add_row(f"[{config.warning}]B.[/] PREVIOUS INTERFACE")

            console.print(menu)

            choice = (
                console.input(f"\n[{config.secondary}]SELECT MODE > [/]")
                .strip()
                .lower()
            )

            if choice == "1":
                self._select_single()
            elif choice == "2":
                self._select_range()
            elif choice == "3":
                self._select_season()
            elif choice == "4":
                self._select_all()
            elif choice == "5":
                self._select_in_progress()
            elif choice == "b":
                return

    def _select_single(self):
        ep_id = (
            console.input(
                f"\n[{config.primary}]ENTER ASSET UID (or 'B' to go back) > [/]"
            )
            .strip()
            .lower()
        )
        if ep_id == "b":
            return

        if ep_id.isdigit():
            episode = self.db.get_episode_by_id(int(ep_id))
            if episode:
                self.episode_menu(episode)
            else:
                console.print(
                    f"[{config.error}]ERROR: ASSET {ep_id} NOT FOUND OR INCOMPLETE.[/]"
                )
                console.input("\nCONTINUE...")
        else:
            console.print(f"[{config.error}]ERROR: INVALID UID FORMAT.[/]")
            console.input("\nCONTINUE...")

    def _select_range(self):
        start = (
            console.input(
                f"\n[{config.primary}]ENTER START UID (or 'B' to go back) > [/]"
            )
            .strip()
            .lower()
        )
        if start == "b":
            return

        end = (
            console.input(
                f"[{config.primary}]ENTER END UID (or 'B' to go back)   > [/]"
            )
            .strip()
            .lower()
        )
        if end == "b":
            return

        if start.isdigit() and end.isdigit():
            episodes = self.db.get_episodes_by_range(int(start), int(end))
            self._batch_results_screen(episodes, f"RANGE: {start} - {end}")
        else:
            console.print(f"[{config.error}]ERROR: INVALID UID RANGE.[/]")
            console.input("\nCONTINUE...")

    def _select_season(self):
        seasons = self.db.get_available_seasons()
        if not seasons:
            console.print(
                f"[{config.error}]ERROR: NO DIVISION DATA DETECTED IN DATABASE.[/]"
            )
            console.input("\nCONTINUE...")
            return

        while True:
            console.clear()
            console.print(
                Panel(
                    "DIVISIONAL SYNC - SELECT OPERATIONAL SECTOR",
                    style=config.header,
                    border_style=config.panel_border,
                )
            )

            table = Table(header_style=config.primary, border_style=config.panel_border)
            table.add_column("IDX", justify="right")
            table.add_column("DIVISION CODE")

            for i, s in enumerate(seasons, start=1):
                table.add_row(str(i), s.code)

            console.print(table)
            console.print(f"[{config.warning}]B.[/] BACK")

            choice = (
                console.input(f"\n[{config.secondary}]SELECT DIVISION IDX > [/]")
                .strip()
                .lower()
            )

            if choice == "b":
                return

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(seasons):
                    season_code = seasons[idx].code
                    episodes = self.db.get_episodes_by_season(season_code)
                    self._batch_results_screen(episodes, f"DIVISION: {season_code}")
                    return  # Exit the season selection after finding episodes
                else:
                    console.print(f"[{config.error}]ERROR: INVALID INDEX.[/]")
                    console.input("\nCONTINUE...")
            else:
                # Also allow manual entry if they want to type the code
                episodes = self.db.get_episodes_by_season(choice.upper())
                if episodes:
                    self._batch_results_screen(episodes, f"DIVISION: {choice.upper()}")
                    return
                else:
                    console.print(
                        f"[{config.error}]ERROR: UNRECOGNIZED DIVISION OR NO ASSETS FOUND.[/]"
                    )
                    console.input("\nCONTINUE...")

    def _select_all(self):
        with console.status(f"[{config.primary}]RETRIEVING ALL COMPLETED ASSETS...[/]"):
            episodes = self.db.get_completed_episodes()
        self._batch_results_screen(episodes, "TOTAL DEPLOYMENT")

    def _select_in_progress(self):
        with console.status(f"[{config.primary}]SCANNING FOR ASSETS IN PROGRESS...[/]"):
            all_episodes = self.db.get_completed_episodes()
            in_progress_episodes = []
            for ep in all_episodes:
                # Check for "IN PROGRESS" status
                status = self._get_status_label(ep)
                if "IN PROGRESS" in status:
                    in_progress_episodes.append(ep)

        self._batch_results_screen(in_progress_episodes, "IN PROGRESS SYNC")

    def _get_status_label(self, episode):
        """Returns a condensed status string for an episode."""
        episode_dir = self.db.get_episode_directory(episode.id)
        if not episode_dir:
            return "[red]ERR: NO DIR[/]"

        job_data = self.db.load_job_data(episode_dir)

        # Determine overall status
        if job_data.manuscript:
            return "[green]DONE[/]"

        # Check if all metadata fields are present
        if (
            job_data.metadata.title
            and job_data.metadata.thesis
            and job_data.metadata.tone
            and job_data.metadata.summary
        ):
            return "[green]METADATA_COMPILED[/]"

        # Check if any metadata fields are present, indicating in-progress
        if (
            job_data.metadata.title
            or job_data.metadata.thesis
            or job_data.metadata.tone
            or job_data.metadata.summary
        ):
            return f"[{config.status_in_progress}]METADATA_IN_PROGRESS[/]"

        if job_data.formatted_txt:
            return "[green]FORMATTED[/]"
        if (
            job_data.paragraphs
        ):  # This check should ideally come after formatted_txt, as paragraphs are derived from formatted_txt
            return f"[{config.status_in_progress}]FORMATTING_IN_PROGRESS[/]"  # Re-labeling to be more specific
        if job_data.transcript_txt:
            return "[blue]LOADED[/]"
        return "[dim]PENDING[/]"

    def _batch_results_screen(self, episodes, mode_desc):
        """Displays results of a batch selection and allows entering single episode menu or batch actions."""
        if not episodes:
            console.print(
                f"[{config.warning}]ALERT: NO ASSETS MATCHING CRITERIA ({mode_desc}).[/]"
            )
            console.input("\nCONTINUE...")
            return

        while True:
            console.clear()
            console.print(
                Panel(
                    f"BATCH SELECTION: {mode_desc} ({len(episodes)} ASSETS)",
                    style=config.header,
                    border_style=config.panel_border,
                )
            )

            table = Table(header_style=config.primary, border_style=config.panel_border)
            table.add_column("IDX", justify="right")
            table.add_column("UID")
            table.add_column("DIV")
            table.add_column("STATUS")
            table.add_column("DESIGNATION")

            # Show top 20 if too many
            display_limit = 20
            for i, ep in enumerate(episodes[:display_limit], start=1):
                season_code = ep.season.code if ep.season else "N/A"
                status = self._get_status_label(ep)
                table.add_row(str(i), str(ep.id), season_code, status, ep.title)

            console.print(table)
            if len(episodes) > display_limit:
                console.print(
                    f"[{config.info}]... AND {len(episodes) - display_limit} MORE ASSETS[/]"
                )

            console.print(
                f"\n[{config.primary}]1.[/] INSPECT INDIVIDUAL ASSET (BY IDX)"
            )
            console.print(f"[{config.primary}]2.[/] INITIATE PIPELINE FOR BATCH")
            console.print(f"[{config.warning}]B.[/] BACK TO MODES")

            choice = (
                console.input(f"\n[{config.secondary}]EXECUTE > [/]").strip().lower()
            )

            if choice == "b":
                break
            elif choice == "1":
                idx_str = (
                    console.input(
                        f"[{config.primary}]ENTER IDX TO INSPECT (or 'B' to go back) > [/]"
                    )
                    .strip()
                    .lower()
                )
                if idx_str == "b":
                    continue

                if idx_str.isdigit():
                    idx = int(idx_str) - 1
                    if 0 <= idx < len(episodes):
                        self.episode_menu(episodes[idx])
                    else:
                        console.print(f"[{config.error}]ERROR: INVALID INDEX.[/]")
                        console.input("\nCONTINUE...")
            elif choice == "2":
                self._batch_run_pipeline(episodes)

    def _display_episode_status(self, episode, job_data):
        """Helper to render the current status of an episode in the TUI."""
        console.clear()
        header_text = f"ASSET UNDER REVIEW: {episode.title}"
        console.print(
            Panel(header_text, style=config.header, border_style=config.panel_border)
        )

        status_table = Table(show_header=False, box=None)

        # Transcript Stream Status
        ts_status = "[green]ACTIVE[/]" if job_data.transcript_txt else "[red]OFFLINE[/]"
        status_table.add_row(f"[{config.info}]TRANSCRIPT_STREAM:[/] {ts_status}")

        # Formatted Sync Status
        if job_data.formatted_txt:
            # Check if all paragraphs are edited
            total_p = len(job_data.paragraphs)
            edited_p = sum(
                1 for p in job_data.paragraphs if p.get("edited") is not None
            )

            if total_p > 0 and edited_p == total_p:
                fmt_status = "[green]COMPILED[/]"
            elif total_p > 0:
                fmt_status = (
                    f"[{config.status_in_progress}]REFINING ({edited_p}/{total_p})[/]"
                )
            else:
                fmt_status = "[green]FORMATTED[/]"
        else:
            fmt_status = "[dim]PENDING[/]"

        status_table.add_row(f"[{config.info}]FORMATTED_SYNC:   [/] {fmt_status}")

        # Manuscript Generation Status
        mg_status = "[green]DEPLOYED[/]" if job_data.manuscript else "[dim]PENDING[/]"
        status_table.add_row(f"[{config.info}]MANUSCRIPT_GEN:  [/] {mg_status}")

        console.print(status_table)
        console.print(f"[{config.primary}]" + "-" * 40 + "[/]")

    def episode_menu(self, episode):
        """Menu for processing a specific episode."""
        episode_dir = self.db.get_episode_directory(episode.id)
        if not episode_dir:
            console.print(
                f"[{config.error}]ERROR: ASSET DIRECTORY NOT FOUND {episode.id}.[/]"
            )
            console.input("\nCONTINUE...")
            return

        while True:
            # Re-load job data each time we return to this menu to ensure it's fresh
            job_data = self.db.load_job_data(episode_dir)

            self._display_episode_status(episode, job_data)

            menu_table = Table(show_header=False, box=None)
            menu_table.add_row(f"[{config.primary}]1.[/] RUN PIPELINE")
            menu_table.add_row(f"[{config.warning}]B.[/] RETURN TO SELECTION")

            console.print(menu_table)

            choice = (
                console.input(f"\n[{config.secondary}]INPUT COMMAND > [/]")
                .strip()
                .lower()
            )

            if choice == "1":
                status, message = self._run_pipeline_for_episode(episode)
                if status == "failed":
                    console.print(f"[{config.error}]{message}[/]")
                elif status == "skipped":
                    console.print(f"[{config.info}]{message}[/]")
                else:
                    console.print(f"[{config.success}]{message}[/]")
                console.input("\nCONTINUE...")
            elif choice == "b":
                break

    def _perform_transcript_extraction(self, episode) -> tuple[bool, str]:
        """
        Core logic to find the .txt transcript for an episode, load it into job_data,
        and save the job_data. Does not handle UI.
        """
        episode_dir = self.db.get_episode_directory(episode.id)
        if not episode_dir:
            return False, f"ERROR: Directory not found for episode UID {episode.id}"

        job_data = self.db.load_job_data(episode_dir)

        txt_files = list(episode_dir.glob("*.txt"))
        transcript_files = [f for f in txt_files if "formatted" not in f.name.lower()]

        if not transcript_files:
            return (
                False,
                f"ERROR: RAW TRANSCRIPT DATA NOT FOUND IN {episode_dir} for episode UID {episode.id}",
            )

        transcript_file = transcript_files[0]
        try:
            content = transcript_file.read_text(encoding="utf-8")
            job_data.transcript_txt = content
            self.db.save_job_data(episode_dir, job_data)
            return True, f"SUCCESS: {transcript_file.name} for episode UID {episode.id}"
        except Exception as e:
            return (
                False,
                f"ERROR: Failed to read or save transcript for episode UID {episode.id}: {e}",
            )

    def _run_pipeline_for_episode(self, episode) -> tuple[str, str]:
        """
        Runs the full processing pipeline for a single episode, skipping steps that are already done.
        Returns a status ('success', 'skipped', 'failed') and a message.
        """
        self.logger.info(
            f"STARTING PIPELINE FOR EPISODE: {episode.title} (ID: {episode.id})"
        )
        episode_dir = self.db.get_episode_directory(episode.id)
        if not episode_dir:
            self.logger.error(f"Directory not found for episode ID: {episode.id}")
            return "failed", f"ERROR: Directory not found for episode UID {episode.id}"

        job_data = self.db.load_job_data(episode_dir)

        # Stage 1: Raw Transcript Extraction
        if not job_data.transcript_txt:
            self.logger.info("Stage 1: Extracting raw transcript.")
            success, message = self._perform_transcript_extraction(episode)
            if not success:
                self.logger.error(f"Stage 1 failed: {message}")
                return "failed", f"RAW TRANSCRIPT EXTRACTION FAILED: {message}"
            job_data = self.db.load_job_data(episode_dir)
            self._display_episode_status(episode, job_data)
        else:
            self.logger.debug("Stage 1: Transcript already exists.")

        # Stage 2: Formatting Protocol
        if not job_data.formatted_txt and job_data.transcript_txt:
            self.logger.info("Stage 2: Formatting transcript with Gemini.")
            # Load prompt
            FORMAT_PROMPT_PATH = (
                Path(__file__).parent / "prompts/formatting/format-transcript.txt"
            )
            if not FORMAT_PROMPT_PATH.exists():
                return (
                    "failed",
                    f"FORMATTING FAILED: Prompt file not found: {FORMAT_PROMPT_PATH}",
                )

            prompt_template = FORMAT_PROMPT_PATH.read_text(encoding="utf-8")

            # Preprocess raw transcript
            # Remove all paragraph breaks and extra spaces
            clean_transcript = " ".join(job_data.transcript_txt.split())
            original_word_count = len(clean_transcript.split())

            for attempt in range(1, 4):  # Max 3 attempts initially
                self.logger.info(f"Stage 2: Formatting Attempt {attempt}/3 starting.")
                with console.status(
                    f"[{config.primary}]FORMATTING (Attempt {attempt}) for {episode.title} using GEMINI...[/]",
                    spinner=config.spinner_type,
                    spinner_style=config.spinner_color,
                ):
                    final_prompt = prompt_template.format(
                        TRANSCRIPT_TEXT=clean_transcript
                    )
                    self.logger.debug(
                        f"Submitting formatting prompt to Gemini. Prompt length: {len(final_prompt)} chars."
                    )
                    gemini_result = self.gemini_client.submit_prompt(
                        final_prompt, retries=1
                    )  # Client has its own retry

                    if not gemini_result.ok:
                        self.logger.error(
                            f"Gemini formatting FAILED (Attempt {attempt}): {gemini_result.error_message}"
                        )
                        if gemini_result.error_type == "quota":
                            self.logger.critical(
                                "GEMINI QUOTA EXCEEDED. Halting Stage 2."
                            )
                            console.print(
                                f"[{config.error}]GEMINI QUOTA EXCEEDED. HALTING ALL OPERATIONS.[/]"
                            )
                            return "failed", "GEMINI QUOTA EXCEEDED"
                        else:
                            console.print(
                                f"[{config.warning}]GEMINI formatting failed (Attempt {attempt}): {gemini_result.error_message}[/]"
                            )
                            # Store failed attempt
                            job_data.failed_formatting_attempts.append(
                                {
                                    "attempt_number": attempt,
                                    "error_message": gemini_result.error_message,
                                    "word_count_ratio": "N/A",  # Not applicable for API failure
                                    "formatted_text_preview": "API Failure",
                                }
                            )
                            self.db.save_job_data(episode_dir, job_data)
                            continue  # Try again

                    formatted_text = gemini_result.output
                    if not formatted_text:
                        self.logger.warning(
                            f"Gemini returned empty output on Attempt {attempt}."
                        )
                        console.print(
                            f"[{config.warning}]Gemini returned no formatted content (Attempt {attempt}).[/]"
                        )
                        continue

                    self.logger.debug(
                        f"Received formatted text. Length: {len(formatted_text)} chars."
                    )
                    # Validate word count
                    formatted_word_count = len(formatted_text.split())
                    word_count_ratio = formatted_word_count / original_word_count
                    self.logger.info(
                        f"Attempt {attempt}: Word count: {formatted_word_count}, Ratio: {word_count_ratio:.2f}"
                    )

                    if 0.98 <= word_count_ratio <= 1.02:  # Within 2%
                        self.logger.info(
                            f"Formatting SUCCESSFUL on attempt {attempt} (Ratio: {word_count_ratio:.2f})."
                        )
                        job_data.formatted_txt = formatted_text
                        job_data.paragraphs = [
                            {"index": i, "original": p.strip(), "edited": None}
                            for i, p in enumerate(formatted_text.split("\n\n"))
                            if p.strip()
                        ]
                        self.logger.info(
                            f"Generated {len(job_data.paragraphs)} paragraphs for refinement."
                        )
                        self.db.save_job_data(episode_dir, job_data)
                        # Instead of returning, set a status message and continue
                        console.print(
                            f"[{config.success}]TRANSCRIPT FORMATTED (Original: {original_word_count} words, Formatted: {formatted_word_count} words, Ratio: {word_count_ratio:.2f}, Paragraphs: {len(job_data.paragraphs)})![/]"
                        )
                        self._display_episode_status(episode, job_data)
                        break  # Exit the retry loop on success
                    else:
                        self.logger.warning(
                            f"Formatting Word Count Mismatch (Attempt {attempt}): Ratio {word_count_ratio:.2f}."
                        )
                        console.print(
                            f"[{config.warning}]Word count mismatch (Attempt {attempt}): Ratio {word_count_ratio:.2f}. Retrying...[/]"
                        )
                        # Store failed attempt for word count mismatch
                        job_data.failed_formatting_attempts.append(
                            {
                                "attempt_number": attempt,
                                "error_message": "Word count mismatch",
                                "word_count_ratio": f"{word_count_ratio:.2f}",
                                "formatted_text_preview": (
                                    formatted_text[:500]
                                    if formatted_text
                                    else "No content returned"
                                ),
                            }
                        )
                        self.db.save_job_data(episode_dir, job_data)
                        if attempt == 3:  # After 3 failed attempts, prompt user
                            self.logger.warning(
                                "Formatting FAILED after 3 attempts. Entering manual intervention."
                            )
                            while True:
                                console.print(
                                    f"[{config.warning}]FORMATTING FAILED AFTER 3 ATTEMPTS FOR {episode.title}. WORD COUNT RATIO: {word_count_ratio:.2f}.[/]"
                                )
                                user_choice = (
                                    console.input(
                                        f"[{config.primary}]Continue with 3 more attempts (Y/N)? [/]"
                                    )
                                    .strip()
                                    .lower()
                                )
                                if user_choice == "y":
                                    attempt = 0  # Reset attempt counter for next set of retries
                                    break
                                elif user_choice == "n":
                                    console.print(
                                        f"[{config.warning}]Formatting aborted by user for {episode.title}.[/]"
                                    )
                                    print_out = (
                                        console.input(
                                            f"[{config.primary}]Print out original and failed attempts for debugging (Y/N)? [/]"
                                        )
                                        .strip()
                                        .lower()
                                    )
                                    if print_out == "y":
                                        console.print(
                                            f"[{config.info}]Original Transcript (clean):[/]\n{clean_transcript}\n"
                                        )
                                        console.print(
                                            f"[{config.info}]Failed attempts details:[/]"
                                        )
                                        for i, failure in enumerate(
                                            job_data.failed_formatting_attempts
                                        ):
                                            console.print(
                                                f"[{config.info}]  Attempt {i+1}:[/]"
                                            )
                                            for key, value in failure.items():
                                                console.print(
                                                    f"[{config.info}]    {key}: {value}[/]"
                                                )
                                    return "failed", "FORMATTING ABORTED BY USER"
                                else:
                                    console.print(
                                        f"[{config.error}]INVALID INPUT. Please enter Y or N.[/]"
                                    )
            # If the loop finishes without success
            if not job_data.formatted_txt:
                return "failed", "FORMATTING FAILED AFTER MAX RETRIES"
        elif job_data.formatted_txt:
            # Formatting already done, just print a skipped message and continue
            console.print(f"[{config.info}]TRANSCRIPT ALREADY FORMATTED (SKIPPED)[/]")

        # Stage 3a: Metadata - Title Extraction (Specific Handling)
        if not job_data.metadata.title:
            if episode.title:
                job_data.metadata.title = episode.title
                self.db.save_job_data(episode_dir, job_data)
                # No return here, allow pipeline to continue
            else:
                console.print(
                    f"[{config.warning}]METADATA - TITLE NOT FOUND IN DB FOR EPISODE UID {episode.id}.[/]"
                )
                console.print(f"[{config.info}]Episode Details:[/]")
                console.print(f"  [{config.info}]- UID: {episode.id}[/]")
                console.print(
                    f"  [{config.info}]- Season: {episode.season.code if episode.season else 'N/A'}[/]"
                )
                console.print(
                    f"  [{config.info}]- Original Title (if available): {episode.title or 'N/A'}[/]"
                )

                user_title = console.input(
                    f"[{config.primary}]Please enter the title for this episode: [/]"
                ).strip()
                if user_title:
                    job_data.metadata.title = user_title
                    self.db.save_job_data(episode_dir, job_data)
                    # No return here, allow pipeline to continue
                else:
                    return (
                        "failed",
                        "METADATA - TITLE EXTRACTION FAILED: User provided no title.",
                    )
        # If title is extracted or provided by user, or was already present, then consider this stage completed successfully.
        # No explicit success message here, as it's part of a larger metadata stage.

        # Stage 3b, 3c, 3d...: Dynamic Metadata Extraction
        for field_name, prompt_path in self._metadata_fields_to_process.items():
            status, message = self._process_metadata_field(
                episode_dir,
                job_data,
                episode,
                field_name,
                prompt_path,
                "formatted_txt",
            )
            if status == "failed":
                return status, message

        # Update TUI after metadata pass
        self._display_episode_status(episode, job_data)

        # Check for any unhandled metadata fields that are still None
        all_metadata_fields = set(job_data.metadata.__dataclass_fields__.keys())
        handled_metadata_fields = set(self._metadata_fields_to_process.keys())
        handled_metadata_fields.add("title")  # Title is handled separately

        unprocessed_metadata_fields = []
        for field_name in all_metadata_fields:
            if (
                field_name not in handled_metadata_fields
                and getattr(job_data.metadata, field_name) is None
            ):
                unprocessed_metadata_fields.append(field_name)

        if unprocessed_metadata_fields:
            console.print(
                f"[{config.warning}]WARNING: The following metadata fields were not processed and are still empty:[/]"
            )
            for field in unprocessed_metadata_fields:
                console.print(f"  [{config.warning}]- {field}[/]")
            console.print(
                f"[{config.info}]This indicates that either there's no processing logic for these fields yet, or an issue prevented their extraction.[/]"
            )
            console.input(
                f"\n[{config.primary}]Press ENTER to acknowledge and continue...[/]"
            )

        # Stage 4: Paragraph Refinement (Editing) & Stage 6: Assembly
        while True:
            # Stage 4: Refinement
            status, message = self._perform_paragraph_editing(
                episode_dir, job_data, episode
            )
            if status == "failed":
                return status, message

            # Update TUI after refinement pass
            self._display_episode_status(episode, job_data)

            # Stage 6: Manuscript Assembly & Final Polish
            status, message = self._perform_manuscript_assembly(
                episode_dir, job_data, episode
            )

            if status == "retry_refinement":
                # Jump back to start of while loop to re-run paragraph editing
                # But we must first reset the failed paragraphs in job_data
                # or the editing stage will just skip them if they have an 'edited' version
                # Actually, our _perform_paragraph_editing checks for evaluation_score < 7, so it will re-process them anyway.
                continue

            if status == "failed":
                return status, message

            # If status is success/completed, break the loop
            break

        # Stage 7: Final Pipeline Quality Audit
        status, message = self._perform_manuscript_evaluation(
            episode_dir, job_data, episode
        )
        if status == "failed":
            return status, message

        # Final TUI update
        self._display_episode_status(episode, job_data)

        return (
            "completed",
            "PIPELINE COMPLETED FOR EPISODE",
        )

    def _perform_paragraph_editing(
        self, episode_dir: Path, job_data: JobData, episode
    ) -> tuple[str, str]:
        """Iterates through paragraphs, edits them, and evaluates them using Ollama."""
        self.logger.info("Starting paragraph editing pass.")
        if not job_data.paragraphs:
            self.logger.warning("No paragraphs found for editing.")
            return "skipped", "NO PARAGRAPHS FOUND FOR EDITING"

        # A paragraph needs work if it hasn't passed evaluation (score < 7)
        to_process = [
            p
            for p in job_data.paragraphs
            if p.get("evaluation_score") is None or p.get("evaluation_score") < 7
        ]
        if not to_process:
            self.logger.info("All paragraphs already passed validation.")
            console.print(f"[{config.info}]ALL PARAGRAPHS ALREADY PASSED (SKIPPED)[/]")
            return "success", "ALL PARAGRAPHS ALREADY PROCESSED"

        self.logger.info(f"Processing {len(to_process)} paragraphs for refinement.")

        # Prompt Paths
        edit_prompt_dir = Path(__file__).parent / "prompts/editing"
        eval_prompt_dir = Path(__file__).parent / "prompts/evaluation"

        edit_prompts = {
            "first": edit_prompt_dir / "first-paragraph-edit.txt",
            "standard": edit_prompt_dir / "standard-paragraph-edit.txt",
            "last": edit_prompt_dir / "last-paragraph-edit.txt",
        }
        eval_prompts = {
            "first": eval_prompt_dir / "first-paragraph-evaluation.txt",
            "standard": eval_prompt_dir / "standard-evaluation.txt",
            "last": eval_prompt_dir / "last-paragraph-evaluation.txt",
        }

        # Context for prompts
        speaker_tone = job_data.metadata.tone or "Professional and Informative"
        thesis = job_data.metadata.thesis or "Not specified"

        # Use a local progress bar
        with Progress(
            SpinnerColumn(spinner_name=config.spinner_type, style=config.spinner_color),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=None, style="black", complete_style=config.primary),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                f"[{config.secondary}]REFINING ASSET...[/]", total=total_paragraphs
            )

            for i, p_dict in enumerate(job_data.paragraphs):
                self.logger.debug(f"Processing paragraph {i+1}/{total_paragraphs}.")
                # Check if already passed
                if (
                    p_dict.get("evaluation_score") is not None
                    and p_dict.get("evaluation_score") >= 7
                ):
                    self.logger.debug(
                        f"Paragraph {i+1} already passed with score {p_dict['evaluation_score']}. Skipping."
                    )
                    progress.advance(task)
                    continue

                # Paragraph context
                p_prev = (
                    job_data.paragraphs[i - 1]["original"] if i > 0 else "START OF TEXT"
                )
                p_target = p_dict["original"]
                p_next = (
                    job_data.paragraphs[i + 1]["original"]
                    if i < total_paragraphs - 1
                    else "END OF TEXT"
                )
                p_type = (
                    "first"
                    if i == 0
                    else "last" if i == total_paragraphs - 1 else "standard"
                )

                self.logger.debug(
                    f"Paragraph {i+1} type: {p_type}. Source length: {len(p_target)} chars."
                )

                # --- MULTI-ATTEMPT LOOP (Max 3 Tries) ---
                passed = False
                for attempt in range(1, 4):
                    self.logger.info(f"Paragraph {i+1}, Attempt {attempt}/3 starting.")
                    progress.update(
                        task,
                        description=f"[{config.primary}]PROCESSING SEGMENT {i+1}/{total_paragraphs} (Attempt {attempt})...[/]",
                    )

                    # 1. EDITING
                    self.logger.debug(f"Loading edit template for type: {p_type}")
                    edit_template = edit_prompts[p_type].read_text(encoding="utf-8")
                    base_prompt = edit_template.format(
                        SPEAKER_TONE=speaker_tone,
                        PARAGRAPH_PREV=p_prev,
                        PARAGRAPH_TARGET=p_target,
                        PARAGRAPH_NEXT=p_next,
                    )

                    # If it's a redo, append previous critique
                    if attempt > 1 and p_dict.get("critique"):
                        self.logger.debug(
                            f"Redo attempt: Appending previous critique to prompt."
                        )
                        final_edit_prompt = (
                            base_prompt
                            + f"\n\n[CRITIQUE FROM PREVIOUS ATTEMPT - INCORPORATE THESE FIXES]:\n{p_dict['critique']}"
                        )
                    else:
                        final_edit_prompt = base_prompt

                    self.logger.debug(
                        f"Submitting edit prompt to Ollama (Paragraph {i+1}). Prompt length: {len(final_edit_prompt)} chars."
                    )
                    edit_result = self.ollama_client.submit_prompt(final_edit_prompt)

                    if not edit_result.ok or not edit_result.output:
                        self.logger.error(
                            f"Ollama EDITING FAILED at Paragraph {i+1}: {edit_result.error_message}"
                        )
                        return (
                            "failed",
                            f"EDITING FAILED AT P#{i+1}: {edit_result.error_message}",
                        )

                    # PARSER: Extract from markers (<<< >>>)
                    raw_edit = edit_result.output
                    self.logger.debug(
                        f"Received raw output from Ollama (Paragraph {i+1}). Length: {len(raw_edit)} chars."
                    )

                    edit_match = re.search(
                        r"REFINED PARAGRAPH:\s*<<<+(.*?)(?:>>>|\Z)", raw_edit, re.DOTALL
                    )
                    if edit_match:
                        extracted_edit = edit_match.group(1).strip()
                        self.logger.debug(
                            f"Extracted edit from markers for Paragraph {i+1}."
                        )
                    else:
                        # Fallback: if markers aren't there, take the whole thing and let sanitizer clean it
                        extracted_edit = raw_edit.strip()
                        self.logger.warning(
                            f"Markers NOT FOUND in Ollama output for Paragraph {i+1}. Using fallback extraction."
                        )

                    sanitized = self._sanitize_text(extracted_edit)
                    p_dict["edited"] = sanitized
                    self.logger.debug(
                        f"Sanitized edit for Paragraph {i+1}. Length: {len(sanitized)} chars."
                    )

                    # 2. EVALUATION
                    self.logger.debug(
                        f"Submitting evaluation prompt to Ollama (Paragraph {i+1})."
                    )
                    eval_template = eval_prompts[p_type].read_text(encoding="utf-8")
                    eval_prompt = eval_template.format(
                        TONE=speaker_tone,
                        THESIS=thesis,
                        PREV=p_prev,
                        NEXT=p_next,
                        OG=p_target,
                        EP=p_dict["edited"],
                    )

                    eval_result = self.eval_client.submit_prompt(eval_prompt)

                    if not eval_result.ok or not eval_result.output:
                        self.logger.error(
                            f"Ollama EVALUATION FAILED at Paragraph {i+1}: {eval_result.error_message}"
                        )
                        return (
                            "failed",
                            f"EVALUATION FAILED AT P#{i+1}: {eval_result.error_message}",
                        )

                    score, critique = self._parse_evaluation(eval_result.output)
                    self.logger.info(
                        f"Paragraph {i+1}, Attempt {attempt}: Received SCORE: {score}/10"
                    )
                    self.logger.debug(f"Critique for Paragraph {i+1}: {critique}")

                    # Auto-fail Heuristic
                    if "*" in p_dict["edited"] or "#" in p_dict["edited"]:
                        self.logger.warning(
                            f"Paragraph {i+1} AUTO-FAILED: Markdown/Asterisks detected in edit."
                        )
                        score = 1
                        critique = "[AUTO-FAIL: Structural Discipline - Markdown/Asterisks detected.]"

                    p_dict["evaluation_score"] = score
                    p_dict["critique"] = critique
                    self.db.save_job_data(episode_dir, job_data)

                    # Check for Success
                    if score >= 7:
                        self.logger.info(
                            f"Paragraph {i+1} PASSED with score {score} on attempt {attempt}."
                        )
                        passed = True
                        break
                    else:
                        self.logger.info(
                            f"Paragraph {i+1} REJECTED with score {score}. Retrying if attempts remain."
                        )

                # --- MANUAL INTERVENTION (If all 3 attempts failed) ---
                if not passed:
                    self.logger.warning(
                        f"Paragraph {i+1} failed all 3 attempts. Entering manual intervention."
                    )
                    # Pause progress bar to show UI
                    progress.stop()
                    console.clear()
                    console.print(
                        Panel(
                            f"TACTICAL ALERT: REFINEMENT FAILURE FOR PARAGRAPH #{i+1}",
                            style=config.error,
                            border_style=config.panel_border,
                        )
                    )

                    table = Table(title="FAILURE LOG", show_header=True, box=None)
                    table.add_column("METRIC", style=config.primary)
                    table.add_column("VALUE")
                    table.add_row("ATTEMPTS", "3 / 3")
                    table.add_row(
                        "LAST SCORE",
                        f"[{config.warning}]{p_dict['evaluation_score']}/10[/]",
                    )
                    console.print(table)

                    console.print(f"\n[{config.secondary}]ORIGINAL:[/]\n{p_target}")
                    console.print(
                        f"\n[{config.secondary}]LATEST EDIT:[/]\n{p_dict['edited']}"
                    )
                    console.print(
                        f"\n[{config.warning}]LAST CRITIQUE:[/]\n{p_dict['critique']}"
                    )

                    console.print(f"\n[{config.primary}]OPTIONS:[/]")
                    console.print(
                        f"[{config.success}]1.[/] ACCEPT ANYWAY (Set Score to 7)"
                    )
                    console.print(
                        f"[{config.error}]2.[/] LEAVE AS FAILED (Abort Episode)"
                    )

                    choice = ""
                    while choice not in ["1", "2"]:
                        choice = console.input(
                            f"\n[{config.secondary}]SELECT RESPONSE > [/]"
                        ).strip()

                    if choice == "1":
                        p_dict["evaluation_score"] = 7  # Force acceptance
                        self.db.save_job_data(episode_dir, job_data)
                        console.print(
                            f"[{config.success}]ASSET OVERRIDDEN. CONTINUING...[/]"
                        )
                        time.sleep(1)
                        progress.start()
                    else:
                        return (
                            "failed",
                            f"PARAGRAPH #{i+1} REJECTED BY USER AFTER 3 ATTEMPTS",
                        )

                progress.advance(task)

        console.print(
            f"[{config.success}]PARAGRAPH REFINEMENT & EVALUATION COMPLETE![/]"
        )
        return "success", "PARAGRAPH REFINEMENT COMPLETE"

    def _perform_manuscript_assembly(
        self, episode_dir: Path, job_data: JobData, episode
    ) -> tuple[str, str]:
        """Combines all edited paragraphs and performs a final polish pass using Gemini."""
        self.logger.info("Starting manuscript assembly and polishing.")
        if job_data.manuscript:
            self.logger.info("Manuscript already exists. Skipping assembly.")
            console.print(f"[{config.info}]MANUSCRIPT ALREADY ASSEMBLED (SKIPPED)[/]")
            return "success", "MANUSCRIPT ALREADY ASSEMBLED"

        # 1. PRE-FLIGHT CHECK: Ensure all paragraphs have score >= 7
        total_p = len(job_data.paragraphs)
        if total_p == 0:
            self.logger.error("No paragraphs found for assembly.")
            return "failed", "ASSEMBLY FAILED: No paragraphs found."

        failed_p = [
            p
            for p in job_data.paragraphs
            if p.get("evaluation_score") is None or p.get("evaluation_score") < 7
        ]
        if failed_p:
            self.logger.warning(f"{len(failed_p)} paragraphs below quality threshold.")
            indices = [p.get("index", "?") for p in failed_p]
            console.print(
                Panel(
                    f"TACTICAL ALERT: QUALITY THRESHOLD NOT MET FOR {len(failed_p)} PARAGRAPHS",
                    style=config.warning,
                    border_style=config.panel_border,
                )
            )
            console.print(
                f"[{config.warning}]THE FOLLOWING INDICES HAVE SCORES < 7: {indices}[/]"
            )

            console.print(f"\n[{config.primary}]OPTIONS:[/]")
            console.print(
                f"[{config.success}]1.[/] FORCE ASSEMBLY (Use current edits anyway)"
            )
            console.print(
                f"[{config.warning}]2.[/] RE-ATTEMPT REFINEMENT (Return to Editing Stage)"
            )
            console.print(f"[{config.error}]Q.[/] ABORT ASSEMBLY")

            choice = ""
            while choice not in ["1", "2", "q"]:
                choice = (
                    console.input(f"\n[{config.secondary}]SELECT RESPONSE > [/]")
                    .strip()
                    .lower()
                )

            if choice == "1":
                console.print(
                    f"[{config.warning}]PROCEEDING WITH DEGRADED ASSEMBLY...[/]"
                )
                time.sleep(1)
            elif choice == "2":
                return "retry_refinement", "USER REQUESTED RE-ATTEMPT OF REFINEMENT"
            else:
                return "failed", "ASSEMBLY ABORTED BY USER DUE TO QUALITY CONCERNS"

        # 2. COMBINE PARAGRAPHS
        # Sort by index just in case
        self.logger.debug("Combining all edited paragraphs for final polish.")
        sorted_paragraphs = sorted(job_data.paragraphs, key=lambda x: x.get("index", 0))
        combined_text = "\n\n".join([p["edited"] for p in sorted_paragraphs])
        original_word_count = len(combined_text.split())
        self.logger.info(
            f"Combined text length: {len(combined_text)} chars, {original_word_count} words."
        )

        # 3. FINAL POLISH PASS (Gemini) with Word Count Validation
        prompt_path = Path(__file__).parent / "prompts/manuscript/full-pass.txt"
        if not prompt_path.exists():
            self.logger.error(f"Manuscript prompt NOT FOUND: {prompt_path}")
            return "failed", f"MANUSCRIPT PROMPT NOT FOUND: {prompt_path}"

        prompt_template = prompt_path.read_text(encoding="utf-8")

        # Context from Metadata
        tone = job_data.metadata.tone or "Standard"
        thesis = job_data.metadata.thesis or "None provided"
        outline = job_data.metadata.outline or "None provided"

        polished_text = None
        max_polish_attempts = 3
        is_failure = False
        failure_reason = None

        for attempt in range(1, max_polish_attempts + 1):
            self.logger.info(f"Manuscript Polish, Attempt {attempt}/3 starting.")
            with console.status(
                f"[{config.primary}]EXECUTING FINAL INTEGRITY PASS (GEMINI) - Attempt {attempt}...[/]",
                spinner=config.spinner_type,
                spinner_style=config.spinner_color,
            ):
                final_prompt = prompt_template.format(
                    TONE=tone,
                    THESIS=thesis,
                    OUTLINE=outline,
                    TEXT_TO_POLISH=combined_text,
                )

                self.logger.debug(
                    f"Submitting manuscript polish prompt to Gemini. Prompt length: {len(final_prompt)} chars."
                )
                gemini_result = self.gemini_client.submit_prompt(
                    final_prompt, retries=1
                )

                if not gemini_result.ok:
                    self.logger.error(
                        f"Gemini polish FAILED (Attempt {attempt}): {gemini_result.error_message}"
                    )
                    if gemini_result.error_type == "quota":
                        self.logger.critical("GEMINI QUOTA EXCEEDED. Halting assembly.")
                        console.print(
                            f"[{config.error}]GEMINI QUOTA EXCEEDED DURING ASSEMBLY. HALTING ALL OPERATIONS.[/]"
                        )
                        return "failed", "GEMINI QUOTA EXCEEDED"

                    console.print(
                        f"[{config.warning}]POLISH ATTEMPT {attempt} FAILED: {gemini_result.error_message}[/]"
                    )
                    if attempt < max_polish_attempts:
                        continue
                    else:
                        # If we failed all attempts with API errors and have no polished_text
                        if not polished_text:
                            self.logger.critical(
                                f"Manuscript Polish FAILED all {max_polish_attempts} attempts due to API errors."
                            )
                            return (
                                "failed",
                                f"FINAL POLISH FAILED AFTER {max_polish_attempts} ATTEMPTS: {gemini_result.error_message}",
                            )
                        # If we have a polished_text from a previous attempt (with low ratio), we'll fall through and use it.
                        self.logger.warning(
                            "Using degraded polished text from a previous attempt due to final attempt API error."
                        )
                        break

                raw_polished = gemini_result.output.strip()
                self.logger.debug(
                    f"Received raw output from Gemini. Length: {len(raw_polished)} chars."
                )

                # 4. MANUSCRIPT SANITIZATION (Vibe Code)
                # Extract from markers if present
                manuscript_match = re.search(
                    r"<<<+(.*?)(?:>>>|\Z)", raw_polished, re.DOTALL
                )
                current_polish = (
                    manuscript_match.group(1).strip()
                    if manuscript_match
                    else raw_polished
                )
                if manuscript_match:
                    self.logger.debug("Extracted manuscript from markers.")
                else:
                    self.logger.warning(
                        "Manuscript markers NOT FOUND in Gemini output. Using raw output."
                    )

                # Remove LLM Gristle
                current_polish = re.sub(
                    r"^(?:Sure!\s*)?Here is.*?\n+",
                    "",
                    current_polish,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                current_polish = self._sanitize_text(current_polish)
                current_polish = re.sub(r"\n{3,}", "\n\n", current_polish)

                # Validate Word Count
                polished_word_count = len(current_polish.split())
                ratio = polished_word_count / original_word_count
                self.logger.info(
                    f"Attempt {attempt}: Polished word count: {polished_word_count}, Ratio: {ratio:.2f}"
                )

                # Update polished_text with the latest result
                polished_text = current_polish

                if ratio >= 0.95:
                    self.logger.info(
                        f"Manuscript polish SUCCESSFUL on attempt {attempt} (Ratio: {ratio:.2f})."
                    )
                    is_failure = False
                    failure_reason = None
                    console.print(
                        f"[{config.success}]POLISH SUCCESSFUL: {polished_word_count} words (Ratio: {ratio:.2f})[/]"
                    )
                    break
                else:
                    is_failure = True
                    failure_reason = f"Low word count ratio: {ratio:.2f} ({polished_word_count} vs {original_word_count})"
                    self.logger.warning(
                        f"Manuscript polish REJECTED (Attempt {attempt}): {failure_reason}"
                    )
                    console.print(
                        f"[{config.warning}]POLISH FAILED (Attempt {attempt}): {failure_reason}[/]"
                    )
                    if attempt == max_polish_attempts:
                        self.logger.warning(
                            f"Final attempt failed word count validation. Storing with is_failure=True."
                        )
                        console.print(
                            f"\n[{config.warning}]FINAL MANUSCRIPT COMPLETED WITH LOW WORD COUNT AFTER {max_polish_attempts} ATTEMPTS. PROCEEDING AS REQUESTED.[/]"
                        )
                        break

        # 5. SAVE MANUSCRIPT
        if not polished_text:
            self.logger.critical("Final Polish failed to generate any text.")
            return "failed", "FINAL POLISH FAILED: No text generated."

        self.logger.debug("Applying final formatting (indents) to manuscript.")
        # Apply paragraph indents (tabs) for Google Docs compatibility
        # We split by any existing paragraph markers (double or triple newlines)
        # Then we ensure each resulting paragraph is stripped and indented.
        # Finally, we join them with a SINGLE newline.
        raw_paragraphs = [
            p.strip() for p in re.split(r"\n\n+", polished_text) if p.strip()
        ]
        final_manuscript_text = "\n".join(["\t" + p for p in raw_paragraphs])

        self.logger.info("Saving manuscript to job_data and manuscript.txt.")
        job_data.manuscript = final_manuscript_text
        job_data.manuscript_is_failure = is_failure
        job_data.manuscript_failure_reason = failure_reason
        self.db.save_job_data(episode_dir, job_data)

        # Build the final text file content with Title and Date header
        # Clean up date to remove time (Mon, 14 Oct 2019 00:38:36 -0600 -> Mon, 14 Oct 2019)
        raw_date = episode.published or "Date Unknown"
        clean_date = re.sub(r"\s\d{2}:\d{2}:\d{2}.*$", "", raw_date).strip()

        final_file_content = f"{episode.title or 'Untitled Asset'}\n"
        final_file_content += f"{clean_date}\n"
        final_file_content += "-" * 20 + "\n\n"
        final_file_content += final_manuscript_text

        # Also save as a standalone text file for convenience
        output_path = episode_dir / "manuscript.txt"
        output_path.write_text(final_file_content, encoding="utf-8")

        console.print(
            f"[{config.success}]MANUSCRIPT ASSEMBLED AND POLISHED: {output_path.name}[/]"
        )
        return "success", "MANUSCRIPT ASSEMBLY COMPLETE"

    def _perform_manuscript_evaluation(
        self, episode_dir: Path, job_data: JobData, episode
    ) -> tuple[str, str]:
        """Performs a final quality audit of the manuscript using Ollama."""
        self.logger.info("Starting final manuscript quality audit.")
        if job_data.manuscript_score is not None:
            self.logger.info("Manuscript evaluation already exists. Skipping.")
            console.print(
                f"[{config.info}]MANUSCRIPT EVALUATION ALREADY PERFORMED (SKIPPED)[/]"
            )
            return "success", "MANUSCRIPT EVALUATION ALREADY PERFORMED"

        if not job_data.manuscript or not job_data.transcript_txt:
            self.logger.error(
                "Manuscript or original transcript missing for evaluation."
            )
            return (
                "failed",
                "EVALUATION FAILED: Manuscript or original transcript missing.",
            )

        # Load prompt
        prompt_path = (
            Path(__file__).parent / "prompts/manuscript/manuscript-evaluation.txt"
        )
        if not prompt_path.exists():
            return "failed", f"EVALUATION PROMPT NOT FOUND: {prompt_path}"

        prompt_template = prompt_path.read_text(encoding="utf-8")

        # Initialize specialized client for evaluation (llama3.2:3b with high context)
        eval_client = OllamaClient(model="llama3.2:3b", num_ctx=32768)

        with console.status(
            f"[{config.primary}]AUDITING PIPELINE QUALITY (OLLAMA - LLAMA 3.2:3B)...[/]",
            spinner=config.spinner_type,
            spinner_style=config.spinner_color,
        ):
            final_prompt = prompt_template.format(
                ORIGINAL_TRANSCRIPT=job_data.transcript_txt,
                FINAL_MANUSCRIPT=job_data.manuscript,
            )

            result = eval_client.submit_prompt(final_prompt)

            if not result.ok or not result.output:
                return "failed", f"MANUSCRIPT EVALUATION FAILED: {result.error_message}"

            evaluation_report = result.output.strip()

        # Extract Score
        # Flexible match for "Total Score" or "Process Quality Score", handling bolding/markdown
        score_match = re.search(
            r"(?:Total|Process Quality)\s*Score[:\*]*\s*(\d+)",
            evaluation_report,
            re.IGNORECASE,
        )
        score = int(score_match.group(1)) if score_match else None

        # Save to JobData
        job_data.manuscript_eval = evaluation_report
        job_data.manuscript_score = score
        self.db.save_job_data(episode_dir, job_data)

        if score is not None:
            color = config.success if score >= 75 else config.warning
            console.print(
                f"[{config.success}]PIPELINE AUDIT COMPLETE. QUALITY SCORE: [{color}]{score}/100[/][/]"
            )
        else:
            console.print(
                f"[{config.warning}]PIPELINE AUDIT COMPLETE (SCORE EXTRACTION FAILED)[/]"
            )

        return "success", "MANUSCRIPT EVALUATION COMPLETE"

    def _sanitize_text(self, text: str) -> str:
        """Sanitizes text based on Vibe Code Report guidelines and strips Markdown."""
        # 1. Remove Markdown/Structural Gristle
        text = re.sub(r"\*\*|__", "", text)
        text = re.sub(r"[*_]", "", text)
        text = re.sub(r"#+\s*", "", text)
        text = re.sub(r"`", "", text)

        # 2. Join broken lines (single newline -> space, double newline -> preserved)
        text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

        # 3. Collapse only HORIZONTAL whitespace (preserve newlines)
        text = re.sub(r"[ \t]+", " ", text).strip()

        # 4. Remove placeholders like [...]
        text = re.sub(r"\[\.\.\.\]", "", text)

        return text

    def _parse_evaluation(self, response_text: str) -> tuple[int, str]:
        """Extracts Rating and Critique from LLM response using regex."""
        # Extract Rating
        rating_match = re.search(r"Rating:\s*(\d+)", response_text)
        score = int(rating_match.group(1)) if rating_match else 1

        # Extract Critique
        critique_match = re.search(
            r"CRITIQUE FOR REDO:\s*(?:<<<)?(.*?)(?:>>>|\n\n|\Z)",
            response_text,
            re.DOTALL,
        )
        critique = (
            critique_match.group(1).strip()
            if critique_match
            else "No critique provided."
        )

        return score, critique

    def _process_metadata_field(
        self,
        episode_dir: Path,
        job_data: JobData,
        episode,
        field_name: str,
        prompt_path: Path,
        source_text_field: str,
    ) -> tuple[str, str]:
        # Check if field is already populated
        current_value = getattr(job_data.metadata, field_name)
        if current_value:
            return (
                "skipped",
                f"METADATA - {field_name.upper()} ALREADY EXTRACTED: {current_value}",
            )

        # Load prompt
        if not prompt_path.exists():
            return (
                "failed",
                f"METADATA - {field_name.upper()} FAILED: Prompt file not found: {prompt_path}",
            )

        prompt_template = prompt_path.read_text(encoding="utf-8")

        # Get source text for LLM
        source_text = getattr(job_data, source_text_field)
        if not source_text:
            # Fallback to transcript_txt if formatted_txt is not available
            if source_text_field == "formatted_txt" and job_data.transcript_txt:
                source_text = job_data.transcript_txt
            else:
                return (
                    "failed",
                    f"METADATA - {field_name.upper()} FAILED: No source text available from {source_text_field}",
                )

        # LLM Selection
        if field_name == "primary_text":
            client = self.gemini_client
            llm_name = "GEMINI"
        else:
            client = self.metadata_llm_client
            llm_name = self.metadata_llm_type.upper()

        # LLM Call
        with console.status(
            f"[{config.primary}]EXTRACTING {field_name.upper()} for {episode.title} using {llm_name}...[/]",
            spinner=config.spinner_type,
            spinner_style=config.spinner_color,
        ):
            final_prompt = prompt_template.format(TRANSCRIPT_TEXT=source_text)

            # Use Gemini-specific call if needed (with retries)
            if llm_name == "GEMINI":
                llm_result = client.submit_prompt(final_prompt, retries=1)
            else:
                llm_result = client.submit_prompt(final_prompt)

            if not llm_result.ok:
                if llm_name == "GEMINI" and llm_result.error_type == "quota":
                    console.print(
                        f"[{config.error}]GEMINI QUOTA EXCEEDED DURING METADATA. HALTING ALL OPERATIONS.[/]"
                    )
                    return "failed", "GEMINI QUOTA EXCEEDED"

                return (
                    "failed",
                    f"METADATA - {field_name.upper()} FAILED: {llm_result.error_message}",
                )

            extracted_value = llm_result.output.strip()
            if not extracted_value:
                return (
                    "failed",
                    f"METADATA - {field_name.upper()} FAILED: {llm_name} returned no content.",
                )

            # Handle list-based fields
            if field_name == "keywords":
                processed_value = [
                    k.strip() for k in extracted_value.split(",") if k.strip()
                ]
            elif field_name in ["quotes", "takeaways"]:
                processed_value = [
                    line.strip() for line in extracted_value.split("\n") if line.strip()
                ]
            else:
                processed_value = extracted_value

            # Set the extracted value
            setattr(job_data.metadata, field_name, processed_value)
            self.db.save_job_data(episode_dir, job_data)
            return (
                "success",
                f"METADATA - {field_name.upper()} EXTRACTED: {processed_value}",
            )

    def _batch_run_pipeline(self, episodes: list):
        """Runs the full pipeline for a batch of episodes with progress tracking."""
        total_episodes = len(episodes)
        results = {"success": 0, "skipped": 0, "failed": 0, "failed_details": []}

        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"[{config.primary}]INITIATING BATCH PIPELINE[/]", total=total_episodes
            )

            for episode in episodes:
                progress.update(
                    task,
                    description=f"[{config.primary}]Processing {episode.title}...[/]",
                )
                status, message = self._run_pipeline_for_episode(episode)

                if status == "success":
                    results["success"] += 1
                elif status == "skipped":
                    results["skipped"] += 1
                elif status == "failed":
                    results["failed"] += 1
                    results["failed_details"].append(f"UID {episode.id}: {message}")

                progress.advance(task)

        console.print(f"\n[{config.primary}]BATCH PIPELINE COMPLETE[/]")
        console.print(
            f"[{config.success}]Successfully processed: {results['success']}[/]"
        )
        console.print(f"[{config.info}]Skipped (already done): {results['skipped']}[/]")
        if results["failed"] > 0:
            console.print(f"[{config.error}]Failed: {results['failed']}[/]")
            for fail_msg in results["failed_details"]:
                console.print(f"  [{config.error}]- {fail_msg}[/]")
        console.input("\nCONTINUE...")
