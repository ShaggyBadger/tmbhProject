import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import (
    Progress,
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
from processor.config import config
from processor.models import JobData
from joshlib.gemini import GeminiClient  # Import GeminiClient and GeminiResult

console = Console()


class PipelineController:
    """Manages the TUI for the editing pipeline with a Tactical Terminal aesthetic."""

    def __init__(self):
        self.db = PipelineDatabase()
        self.initializer = PipelineInitializer(self.db)
        self.gemini_client = GeminiClient()
        self._metadata_fields_to_process = {
            "thesis": Path(__file__).parent / "prompts/metadata/extract-thesis.txt",
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
            table.add_row(f"[{config.warning}]Q.[/] ABORT TO BASE")

            console.print(table)

            choice = (
                console.input(f"\n[{config.secondary}]EXECUTE COMMAND > [/]")
                .strip()
                .lower()
            )

            if choice == "1":
                self.select_episode()
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

            console.clear()
            header_text = f"ASSET UNDER REVIEW: {episode.title}"
            console.print(
                Panel(
                    header_text, style=config.header, border_style=config.panel_border
                )
            )

            # Show a brief summary of the current state
            status_table = Table(show_header=False, box=None)
            status_table.add_row(
                f"[{config.info}]TRANSCRIPT_STREAM:[/] {'[green]ACTIVE[/]' if job_data.transcript_txt else '[red]OFFLINE[/]'}"
            )

            # Formatted Sync Logic
            if job_data.formatted_txt:
                fmt_status = "[green]COMPILED[/]"
            elif job_data.paragraphs:
                fmt_status = f"[{config.status_in_progress}]IN PROGRESS[/]"
            else:
                fmt_status = "[dim]PENDING[/]"

            status_table.add_row(f"[{config.info}]FORMATTED_SYNC:   [/] {fmt_status}")
            status_table.add_row(
                f"[{config.info}]MANUSCRIPT_GEN:  [/] {'[green]DEPLOYED[/]' if job_data.manuscript else '[dim]PENDING[/]'}"
            )
            console.print(status_table)
            console.print(f"[{config.primary}]" + "-" * 40 + "[/]")

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
        episode_dir = self.db.get_episode_directory(episode.id)
        if not episode_dir:
            return "failed", f"ERROR: Directory not found for episode UID {episode.id}"

        job_data = self.db.load_job_data(episode_dir)

        # Stage 1: Raw Transcript Extraction
        if not job_data.transcript_txt:
            # Only perform if raw transcript is not already present
            success, message = self._perform_transcript_extraction(episode)
            if not success:
                return "failed", f"RAW TRANSCRIPT EXTRACTION FAILED: {message}"
            # Reload job_data as _perform_transcript_extraction modifies it
            job_data = self.db.load_job_data(episode_dir)
        else:
            # If transcript_txt exists, skip this stage
            pass  # Continue to next stage logic

        # Stage 2: Formatting Protocol
        if not job_data.formatted_txt and job_data.transcript_txt:
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
                with console.status(
                    f"[{config.primary}]FORMATTING (Attempt {attempt}) for {episode.title}...[/]",
                    spinner=config.spinner_type,
                    spinner_style=config.spinner_color,
                ):
                    final_prompt = prompt_template.format(
                        TRANSCRIPT_TEXT=clean_transcript
                    )
                    gemini_result = self.gemini_client.submit_prompt(
                        final_prompt, retries=1
                    )  # GeminiClient has its own retry

                    if not gemini_result.ok:
                        if gemini_result.error_type == "quota":
                            console.print(
                                f"[{config.error}]GEMINI QUOTA EXCEEDED. HALTING ALL OPERATIONS.[/]"
                            )
                            return "failed", "GEMINI QUOTA EXCEEDED"
                        else:
                            console.print(
                                f"[{config.warning}]Gemini formatting failed (Attempt {attempt}): {gemini_result.error_message}[/]"
                            )
                            # Store failed attempt
                            job_data.failed_formatting_attempts.append(
                                {
                                    "attempt_number": attempt,
                                    "error_message": gemini_result.error_message,
                                    "word_count_ratio": "N/A",  # Not applicable for API failure
                                    "formatted_text_preview": (
                                        formatted_text[:500]
                                        if formatted_text
                                        else "No content returned"
                                    ),
                                }
                            )
                            self.db.save_job_data(episode_dir, job_data)
                            continue  # Try again if not quota error

                    formatted_text = gemini_result.output
                    if not formatted_text:
                        console.print(
                            f"[{config.warning}]Gemini returned no formatted content (Attempt {attempt}).[/]"
                        )
                        continue

                    # Validate word count
                    formatted_word_count = len(formatted_text.split())
                    word_count_ratio = formatted_word_count / original_word_count

                    if 0.98 <= word_count_ratio <= 1.02:  # Within 2%
                        job_data.formatted_txt = formatted_text
                        job_data.paragraphs = [
                            {"original": p.strip(), "edited": None}
                            for p in formatted_text.split("\n\n")
                            if p.strip()
                        ]
                        self.db.save_job_data(episode_dir, job_data)
                        # Instead of returning, set a status message and continue
                        console.print(
                            f"[{config.success}]TRANSCRIPT FORMATTED (Original: {original_word_count} words, Formatted: {formatted_word_count} words, Ratio: {word_count_ratio:.2f}, Paragraphs: {len(job_data.paragraphs)})![/]"
                        )
                        break  # Exit the retry loop on success
                    else:
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

        return (
            "completed",
            "PIPELINE COMPLETED FOR EPISODE (OR SKIPPED ALL STEPS)",
        )  # Changed from "RAW TRANSCRIPT ALREADY PRESENT"

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

        # LLM Call
        with console.status(
            f"[{config.primary}]EXTRACTING {field_name.upper()} for {episode.title}...[/]",
            spinner=config.spinner_type,
            spinner_style=config.spinner_color,
        ):
            final_prompt = prompt_template.format(TRANSCRIPT_TEXT=source_text)
            gemini_result = self.gemini_client.submit_prompt(final_prompt, retries=1)

            if not gemini_result.ok:
                return (
                    "failed",
                    f"METADATA - {field_name.upper()} FAILED: {gemini_result.error_message}",
                )

            extracted_value = gemini_result.output.strip()
            if not extracted_value:
                return (
                    "failed",
                    f"METADATA - {field_name.upper()} FAILED: Gemini returned no content.",
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
