import shutil
import logging
import re
import time
from pathlib import Path
from typing import List, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from processor.services.database import PipelineDatabase
from processor.config import config
from models import PodcastEpisode, PodcastSeason

console = Console()
logger = logging.getLogger(__name__)


class PodcastReorganizer:
    """Manages moving episodes from 'unknown_season' to assigned seasons."""

    def __init__(self, db: PipelineDatabase):
        self.db = db

    def start(self):
        """Entry point for the reorganization TUI."""
        while True:
            console.clear()
            console.print(
                Panel(
                    "ASSET REORGANIZATION MODULE - SEASON ASSIGNMENT",
                    style=config.header,
                    border_style=config.panel_border,
                )
            )

            unknown_episodes = self.db.get_unknown_season_episodes()
            if not unknown_episodes:
                console.print(
                    f"[{config.success}]NO UNKNOWN SEASON ASSETS DETECTED. ALL SYSTEMS NOMINAL.[/]"
                )
                console.input("\nPRESS ENTER TO RETURN...")
                return

            table = Table(header_style=config.primary, border_style=config.panel_border)
            table.add_column("IDX", justify="right")
            table.add_column("ID", justify="right")
            table.add_column("TITLE")
            table.add_column("PUBLISHED")

            for i, ep in enumerate(unknown_episodes, start=1):
                table.add_row(str(i), str(ep.id), ep.title, ep.published or "Unknown")

            console.print(table)
            console.print(f"[{config.warning}]B.[/] BACK")

            choice = (
                console.input(
                    f"\n[{config.secondary}]SELECT ASSET IDX TO REORGANIZE > [/]"
                )
                .strip()
                .lower()
            )

            if choice == "b":
                return

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(unknown_episodes):
                    self._reorganize_episode(unknown_episodes[idx])
                else:
                    console.print(f"[{config.error}]INVALID SELECTION.[/]")
                    time.sleep(1)
            else:
                console.print(f"[{config.error}]INVALID INPUT.[/]")
                time.sleep(1)

    def _reorganize_episode(self, episode: PodcastEpisode):
        """Handle the re-assignment of a single episode."""
        # Load extra context from JobData if available
        old_dir = self.db.get_episode_directory(episode.id)
        job_data = self.db.load_job_data(old_dir) if old_dir else None

        while True:
            console.clear()
            console.print(
                Panel(
                    f"REORGANIZING ASSET: {episode.title}",
                    style=config.header,
                    border_style=config.panel_border,
                )
            )

            # Display Episode Info from Database
            info_table = Table(show_header=False, box=None)
            info_table.add_row(f"[{config.primary}]ID:[/]", str(episode.id))
            info_table.add_row(f"[{config.primary}]TITLE:[/]", episode.title)

            # Display Metadata from JobData if it exists
            if job_data and job_data.metadata:
                m = job_data.metadata
                summary = m.summary or episode.summary or "N/A"
                primary_text = m.primary_text or "N/A"

                # Format long text
                def truncate(text, limit=300):
                    if not text:
                        return "N/A"
                    return (text[:limit] + "...") if len(text) > limit else text

                info_table.add_row(
                    f"[{config.primary}]SUMMARY (JSON):[/]", truncate(summary)
                )
                info_table.add_row(
                    f"[{config.primary}]PRIMARY TEXT:[/]", truncate(primary_text)
                )
                info_table.add_row(
                    f"[{config.primary}]THESIS:[/]", truncate(m.thesis, 150)
                )
            else:
                info_table.add_row(
                    f"[{config.primary}]SUMMARY (DB):[/]",
                    (
                        (episode.summary[:200] + "...")
                        if episode.summary and len(episode.summary) > 200
                        else (episode.summary or "N/A")
                    ),
                )

            console.print(info_table)

            # Fetch Available Seasons
            seasons = self.db.get_available_seasons()

            console.print(f"\n[{config.secondary}]SELECT TARGET DIVISION (SEASON):[/]")
            season_table = Table(
                header_style=config.primary, border_style=config.panel_border
            )
            season_table.add_column("IDX", justify="right")
            season_table.add_column("CODE")

            for i, s in enumerate(seasons, start=1):
                season_table.add_row(str(i), s.code)

            console.print(season_table)
            console.print(f"[{config.warning}]B.[/] BACK")

            choice = (
                console.input(f"\n[{config.secondary}]SELECT DIVISION IDX > [/]")
                .strip()
                .lower()
            )

            if choice == "b":
                return

            if choice.isdigit():
                s_idx = int(choice) - 1
                if 0 <= s_idx < len(seasons):
                    self._execute_move(episode, seasons[s_idx])
                    return
                else:
                    console.print(f"[{config.error}]INVALID SELECTION.[/]")
            else:
                console.print(f"[{config.error}]INVALID INPUT.[/]")

            time.sleep(1)

    def _execute_move(self, episode: PodcastEpisode, target_season: PodcastSeason):
        """Execute the physical directory move and database updates."""
        logger.info(
            f"Executing re-org for episode {episode.id} to season {target_season.code}"
        )

        # 1. Get current directory
        old_dir = self.db.get_episode_directory(episode.id)
        if not old_dir or not old_dir.exists():
            logger.error(
                f"Cannot move episode {episode.id}: Current directory not found or does not exist at {old_dir}"
            )
            console.print(f"[{config.error}]ERROR: SOURCE DIRECTORY NOT FOUND.[/]")
            console.input("\nPRESS ENTER...")
            return

        # 2. Determine target directory structure
        # We need to know where the podcast root is.
        # Usually it's old_dir.parent.parent (unknown_season/episode_dir -> podcast_root/unknown_season/episode_dir)
        podcast_root = old_dir.parent.parent

        cleaned_season_name = re.sub(r"\W+", "_", target_season.code.lower())
        new_season_dir = podcast_root / cleaned_season_name
        new_episode_dir = new_season_dir / old_dir.name

        logger.info(f"Moving {old_dir} to {new_episode_dir}")

        try:
            # Create target season directory if it doesn't exist
            new_season_dir.mkdir(parents=True, exist_ok=True)

            if new_episode_dir.exists():
                logger.warning(
                    f"Target directory {new_episode_dir} already exists. Aborting move to prevent data loss."
                )
                console.print(
                    f"[{config.error}]ERROR: TARGET DIRECTORY ALREADY EXISTS.[/]"
                )
                console.input("\nPRESS ENTER...")
                return

            # Physical move
            shutil.move(str(old_dir), str(new_episode_dir))
            logger.info("Physical move complete.")

            # 3. Update Database
            self.db.update_episode_season(episode.id, target_season.id)
            self.db.update_episode_paths(episode.id, new_episode_dir)

            console.print(
                f"[{config.success}]ASSET SUCCESSFULLY REASSIGNED TO {target_season.code}.[/]"
            )
            logger.info(
                f"Episode {episode.id} successfully moved and database updated."
            )
            console.input("\nPRESS ENTER TO CONTINUE...")

        except Exception as e:
            logger.error(f"Failed to reorganize episode {episode.id}: {e}")
            console.print(
                f"[{config.error}]CRITICAL ERROR DURING REORGANIZATION: {e}[/]"
            )
            console.input("\nPRESS ENTER...")
