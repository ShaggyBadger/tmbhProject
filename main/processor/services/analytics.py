import logging
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from processor.services.database import PipelineDatabase
from processor.config import config

console = Console()
logger = logging.getLogger(__name__)


class MissionDebrief:
    """Provides high-level analytics for the entire podcast project."""

    def __init__(self, db: PipelineDatabase):
        self.db = db

    def show(self):
        """Displays the tactical analytics debrief."""
        console.clear()
        console.print(
            Panel(
                "MISSION DEBRIEF - GLOBAL OPERATIONS STATUS",
                style=config.header,
                border_style=config.panel_border,
            )
        )

        with Progress(
            SpinnerColumn(spinner_name=config.spinner_type, style=config.spinner_color),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(
                "[primary]GATHERING GLOBAL INTELLIGENCE...[/]", total=None
            )
            all_data = self.db.get_all_job_data()

        if not all_data:
            console.print(
                f"[{config.warning}]NO MISSION DATA AVAILABLE FOR ANALYSIS.[/]"
            )
            console.input("\nPRESS ENTER TO RETURN...")
            return

        # 1. Operational Metrics
        total_episodes = len(all_data)
        completed_episodes = [d for _, d in all_data if d.manuscript_score is not None]
        pending_episodes = total_episodes - len(completed_episodes)

        # 2. Quality Metrics (Avg Process Quality Score)
        scores = [
            d.manuscript_score for _, d in all_data if d.manuscript_score is not None
        ]
        avg_score = sum(scores) / len(scores) if scores else 0

        # 3. Word Count Metrics (Compression/Expansion)
        total_orig_words = 0
        total_refined_words = 0
        for ep, job_data in all_data:
            if job_data.paragraphs:
                orig = " ".join([p["original"] for p in job_data.paragraphs])
                total_orig_words += len(orig.split())
            if job_data.manuscript:
                total_refined_words += len(job_data.manuscript.split())

        compression_ratio = (
            total_refined_words / total_orig_words if total_orig_words > 0 else 0
        )

        # 4. Storage Metrics
        archived_count = sum(1 for _, d in all_data if d.audio_archived)
        archive_pct = (
            (archived_count / total_episodes * 100) if total_episodes > 0 else 0
        )

        # Build Stats Table
        stats_table = Table(header_style=config.primary, box=None)
        stats_table.add_column("METRIC CATEGORY", style=config.secondary)
        stats_table.add_column("DATA POINT")

        # Operational Status
        stats_table.add_row("TOTAL ASSETS TRACKED", str(total_episodes))
        stats_table.add_row(
            "MISSION COMPLETION",
            f"{len(completed_episodes)} / {total_episodes} ({(len(completed_episodes)/total_episodes*100):.1f}%)",
        )

        # Quality Summary
        score_color = (
            config.success
            if avg_score >= 80
            else config.warning if avg_score >= 60 else config.error
        )
        stats_table.add_row(
            "GLOBAL QUALITY SCORE", f"[{score_color}]{avg_score:.2f} / 100.00[/]"
        )

        # Content Volume
        stats_table.add_row(
            "TOTAL REFINED WORD COUNT", f"{total_refined_words:,} words"
        )
        stats_table.add_row(
            "CONTENT DENSITY RATIO", f"{compression_ratio:.2f} (Refined vs Original)"
        )

        # Storage Efficiency
        stats_table.add_row(
            "STORAGE ARCHIVE STATUS",
            f"{archived_count} / {total_episodes} ({(archive_pct):.1f}% Compressed)",
        )

        console.print(stats_table)

        # Failure Log Summary (If any)
        failures = [ep.title for ep, d in all_data if d.manuscript_is_failure]
        if failures:
            fail_table = Table(
                title="ASSETS REQUIRING MANUAL REVIEW",
                title_style=config.warning,
                box=None,
            )
            fail_table.add_column("ASSET TITLE", style=config.error)
            for f in failures[:10]:
                fail_table.add_row(f)
            if len(failures) > 10:
                fail_table.add_row(f"... AND {len(failures)-10} OTHERS")
            console.print(fail_table)

        console.print(f"\n[{config.primary}]MISSION DEBRIEF COMPLETE.[/]")
        console.input("\nPRESS ENTER TO RETURN TO BASE...")
