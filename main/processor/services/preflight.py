import shutil
import logging
import os
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from sqlalchemy import text, func
from dotenv import load_dotenv

from processor.config import config
from db import SessionLocal
from models import PodcastEpisode, PodcastSeason, JobDeployment

# Load environment variables from .env file
load_dotenv()

console = Console()
logger = logging.getLogger(__name__)


class PreflightCheck:
    """Performs tactical diagnostics and generates a system status report."""

    def __init__(self):
        self.script_dir = Path(__file__).resolve().parents[2]
        self.podcast_root = self.script_dir / "podcast_files"

    def run_all(self) -> bool:
        """Executes system status checks and displays a tactical intel report."""
        console.clear()
        console.print(
            Panel(
                "TACTICAL SYSTEM REPORT - INITIALIZING...",
                style=config.header,
                border_style=config.panel_border,
            )
        )

        # 1. Basic Connectivity Checks
        self._display_section_header("CORE SUBSYSTEMS")
        subsystems = [
            ("DATABASE CONNECTIVITY", self._check_database),
            ("STORAGE AVAILABILITY", self._check_disk_space),
        ]

        results_table = Table(show_header=True, header_style=config.primary, box=None)
        results_table.add_column("SUBSYSTEM", width=30)
        results_table.add_column("STATUS", justify="center")
        results_table.add_column("DETAIL")

        for name, func_check in subsystems:
            status, detail = func_check()
            status_display = (
                f"[{config.success}]ONLINE[/]"
                if status
                else f"[{config.error}]DEGRADED[/]"
            )
            results_table.add_row(name, status_display, detail)

        console.print(results_table)

        # 2. Database Intel
        self._display_section_header("DATABASE INTEL")
        db_stats = self._get_db_stats()

        stats_table = Table(show_header=False, box=None, padding=(0, 2))
        stats_table.add_column("LABEL", style=config.secondary)
        stats_table.add_column("VALUE", style=config.primary)

        stats_table.add_row(
            "TOTAL ASSETS (EPISODES)", str(db_stats.get("total_episodes", 0))
        )
        stats_table.add_row(
            "OPERATIONAL SEASONS", str(db_stats.get("total_seasons", 0))
        )
        stats_table.add_row(
            "DEPLOYED JOBS (WAITING)", str(db_stats.get("pending_jobs", 0))
        )
        stats_table.add_row(
            "TRANSCRIPTION COMPLETE", str(db_stats.get("completed_transcripts", 0))
        )

        console.print(stats_table)

        # 3. Storage Intel
        self._display_section_header("STORAGE TELEMETRY")
        storage_stats = self._get_storage_stats()

        store_table = Table(show_header=False, box=None, padding=(0, 2))
        store_table.add_column("LABEL", style=config.secondary)
        store_table.add_column("VALUE", style=config.primary)

        store_table.add_row(
            "DOWNLOADED AUDIO ASSETS", str(storage_stats.get("audio_files", 0))
        )
        store_table.add_row(
            "LOCAL PAYLOAD SIZE", storage_stats.get("total_size", "0 B")
        )
        store_table.add_row(
            "PODCAST ROOT PATH",
            str(self.podcast_root.relative_to(self.script_dir.parent)),
        )

        console.print(store_table)

        console.print(
            f"\n[{config.success}]REPORT COMPLETE. ALL SYSTEMS READY FOR DEPLOYMENT.[/]"
        )
        logger.info("Tactical system report generated.")
        console.input(
            f"\n[{config.secondary}]PRESS ENTER TO PROCEED TO MISSION CONTROL...[/]"
        )
        return True

    def _display_section_header(self, title: str):
        console.print(f"\n[{config.primary}]> {title}[/]")
        console.print(f"[{config.primary}]" + "-" * (len(title) + 2) + "[/]")

    def _check_database(self) -> tuple[bool, str]:
        """Check if we can connect to the SQLite DB."""
        try:
            session = SessionLocal()
            session.execute(text("SELECT 1"))
            session.close()
            return True, "SQLITE-LINK ESTABLISHED"
        except Exception as e:
            return False, f"LINK FAILURE: {str(e)}"

    def _check_disk_space(self) -> tuple[bool, str]:
        """Check if we have at least 1GB of space."""
        try:
            total, used, free = shutil.disk_usage(self.script_dir)
            free_gb = free / (1024**3)
            status = free_gb >= 1.0
            return status, f"{free_gb:.2f} GB REMAINING"
        except Exception as e:
            return False, f"TELEMETRY ERROR: {e}"

    def _get_db_stats(self) -> dict:
        """Fetch statistics from the database."""
        stats = {}
        session = SessionLocal()
        try:
            stats["total_episodes"] = session.query(
                func.count(PodcastEpisode.id)
            ).scalar()
            stats["total_seasons"] = session.query(
                func.count(PodcastSeason.id)
            ).scalar()
            stats["pending_jobs"] = (
                session.query(func.count(JobDeployment.id))
                .filter(JobDeployment.job_status.in_(["pending", "deployed-waiting"]))
                .scalar()
            )
            stats["completed_transcripts"] = (
                session.query(func.count(PodcastEpisode.id))
                .filter(PodcastEpisode.transcription_status == "completed")
                .scalar()
            )
        except Exception as e:
            logger.error(f"Failed to fetch DB stats: {e}")
        finally:
            session.close()
        return stats

    def _get_storage_stats(self) -> dict:
        """Scan the podcast_files directory for intel."""
        stats = {"audio_files": 0, "total_size": 0}
        try:
            if self.podcast_root.exists():
                for root, dirs, files in os.walk(self.podcast_root):
                    for f in files:
                        stats["audio_files"] += 1
                        stats["total_size"] += os.path.getsize(os.path.join(root, f))

            # Format size
            size_bytes = stats["total_size"]
            for unit in ["B", "KB", "MB", "GB", "TB"]:
                if size_bytes < 1024.0:
                    stats["total_size"] = f"{size_bytes:.2f} {unit}"
                    break
                size_bytes /= 1024.0
        except Exception as e:
            logger.error(f"Failed to fetch storage stats: {e}")
            stats["total_size"] = "UNKNOWN"
        return stats
