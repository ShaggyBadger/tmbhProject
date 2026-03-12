import sys
import logging
from pathlib import Path

# Ensure the 'main' directory is in sys.path
main_dir = Path(__file__).resolve().parents[2]
if str(main_dir) not in sys.path:
    sys.path.insert(0, str(main_dir))

from processor.services.database import PipelineDatabase

logger = logging.getLogger(__name__)


class PipelineInitializer:
    """Scans all episodes in the database and ensures each has an up-to-date job_data.json file."""

    def __init__(self, db: PipelineDatabase):
        self.db = db

    def sync_all_episodes(self, status=None):
        """Finds all completed episodes and initializes/syncs their job_data.json files."""
        logger.info("Starting global job data synchronization pass.")
        episodes = self.db.get_completed_episodes()
        logger.info(f"Found {len(episodes)} completed episodes to sync.")

        total = len(episodes)
        for i, ep in enumerate(episodes, start=1):
            if status:
                status.update(
                    f"[bold cyan][{i}/{total}][/] Syncing: [italic]{ep.title}[/]"
                )

            logger.debug(f"Syncing episode {ep.id}: {ep.title}")
            self.db.initialize_job_data(ep.id)

        logger.info("Global synchronization pass complete.")
