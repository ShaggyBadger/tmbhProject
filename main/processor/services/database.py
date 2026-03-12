import json
import os
import sys
import logging
from pathlib import Path
from typing import Optional, List

# Ensure the 'main' directory is in sys.path
main_dir = Path(__file__).resolve().parents[2]
if str(main_dir) not in sys.path:
    sys.path.insert(0, str(main_dir))

from sqlalchemy.orm import joinedload
from db import SessionLocal
from models import PodcastEpisode, PodcastPath, PodcastSeason
from processor.models import JobData, Metadata

logger = logging.getLogger(__name__)


class PipelineDatabase:
    """Manages access to the main database and job_data.json files."""

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get_completed_episodes(self) -> List[PodcastEpisode]:
        """Returns episodes that have completed transcription."""
        logger.debug("Fetching all completed episodes from database.")
        session = self.session_factory()
        try:
            return (
                session.query(PodcastEpisode)
                .options(joinedload(PodcastEpisode.season))
                .filter(PodcastEpisode.transcription_status == "completed")
                .order_by(PodcastEpisode.id.desc())
                .all()
            )
        finally:
            session.close()

    def get_available_seasons(self) -> List[PodcastSeason]:
        """Fetch all defined seasons."""
        logger.debug("Fetching all defined seasons.")
        session = self.session_factory()
        try:
            return session.query(PodcastSeason).order_by(PodcastSeason.code).all()
        finally:
            session.close()

    def get_episode_by_id(self, episode_id: int) -> Optional[PodcastEpisode]:
        """Fetch a specific completed episode by ID."""
        logger.debug(f"Fetching episode by ID: {episode_id}")
        session = self.session_factory()
        try:
            return (
                session.query(PodcastEpisode)
                .options(joinedload(PodcastEpisode.season))
                .filter(
                    PodcastEpisode.id == episode_id,
                    PodcastEpisode.transcription_status == "completed",
                )
                .first()
            )
        finally:
            session.close()

    def get_episodes_by_range(self, start_id: int, end_id: int) -> List[PodcastEpisode]:
        """Fetch completed episodes within a specific ID range."""
        logger.debug(f"Fetching episodes in range: {start_id} to {end_id}")
        session = self.session_factory()
        try:
            return (
                session.query(PodcastEpisode)
                .options(joinedload(PodcastEpisode.season))
                .filter(
                    PodcastEpisode.id >= start_id,
                    PodcastEpisode.id <= end_id,
                    PodcastEpisode.transcription_status == "completed",
                )
                .order_by(PodcastEpisode.id.asc())
                .all()
            )
        finally:
            session.close()

    def get_episodes_by_season(self, season_code: str) -> List[PodcastEpisode]:
        """Fetch completed episodes for a specific season code."""
        logger.debug(f"Fetching episodes for season: {season_code}")
        session = self.session_factory()
        try:
            return (
                session.query(PodcastEpisode)
                .join(PodcastEpisode.season)
                .options(joinedload(PodcastEpisode.season))
                .filter(
                    PodcastSeason.code == season_code,
                    PodcastEpisode.transcription_status == "completed",
                )
                .order_by(PodcastEpisode.id.asc())
                .all()
            )
        finally:
            session.close()

    def get_unknown_season_episodes(self) -> List[PodcastEpisode]:
        """Returns episodes that are not assigned to a season."""
        logger.debug("Fetching all episodes without a season assignment.")
        session = self.session_factory()
        try:
            return (
                session.query(PodcastEpisode)
                .filter(PodcastEpisode.season_id == None)
                .order_by(PodcastEpisode.id.asc())
                .all()
            )
        finally:
            session.close()

    def update_episode_season(self, episode_id: int, season_id: int):
        """Updates the season_id for a specific episode."""
        logger.info(f"Updating season_id for episode {episode_id} to {season_id}")
        session = self.session_factory()
        try:
            episode = (
                session.query(PodcastEpisode)
                .filter(PodcastEpisode.id == episode_id)
                .first()
            )
            if episode:
                episode.season_id = season_id
                session.commit()
                logger.info("Database update successful.")
            else:
                logger.error(f"Episode {episode_id} not found for update.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update episode season in database: {e}")
        finally:
            session.close()

    def update_episode_paths(self, episode_id: int, new_dir: Path):
        """Updates all path records for an episode to reflect a new directory."""
        logger.info(
            f"Updating all paths for episode {episode_id} to new directory: {new_dir}"
        )
        session = self.session_factory()
        try:
            paths = (
                session.query(PodcastPath)
                .filter(PodcastPath.episode_id == episode_id)
                .all()
            )
            for p in paths:
                old_path = Path(p.file_path)
                new_file_path = new_dir / old_path.name
                logger.debug(f"Updating path ID {p.id}: {old_path} -> {new_file_path}")
                p.file_path = str(new_file_path)
            session.commit()
            logger.info("Path updates successful.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update episode paths in database: {e}")
        finally:
            session.close()

    def get_episode_directory(self, episode_id: int) -> Optional[Path]:
        """Gets the directory path for a given episode ID."""
        logger.debug(f"Getting directory for episode ID: {episode_id}")
        session = self.session_factory()
        try:
            path_record = (
                session.query(PodcastPath)
                .filter(PodcastPath.episode_id == episode_id)
                .first()
            )
            if path_record:
                dir_path = Path(path_record.file_path).parent
                logger.debug(f"Resolved directory: {dir_path}")
                return dir_path
            logger.warning(f"No directory found for episode ID: {episode_id}")
            return None
        finally:
            session.close()

    def load_job_data(self, episode_dir: Path) -> JobData:
        """Loads job_data.json from the episode directory."""
        json_path = episode_dir / "job_data.json"
        logger.debug(f"Loading job data from: {json_path}")

        if not json_path.exists():
            logger.info(f"Job data file does not exist: {json_path}")
            return JobData()

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            job_data = JobData.from_dict(data)
            logger.debug("Successfully loaded job data.")
            return job_data
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Error loading job data from {json_path}: {e}")
            return JobData()

    def save_job_data(self, episode_dir: Path, job_data: JobData):
        """Saves the JobData instance to job_data.json."""
        json_path = episode_dir / "job_data.json"
        logger.debug(f"Saving job data to: {json_path}")
        episode_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(job_data.to_dict(), f, indent=4)
            logger.debug("Save successful.")
        except Exception as e:
            logger.error(f"Failed to save job data to {json_path}: {e}")

    def initialize_job_data(self, episode_id: int) -> Optional[JobData]:
        """Ensures job_data.json is synced with the current schema."""
        logger.info(f"Initializing job data for episode ID: {episode_id}")
        episode_dir = self.get_episode_directory(episode_id)
        if not episode_dir:
            return None

        job_data = self.load_job_data(episode_dir)
        self.save_job_data(episode_dir, job_data)
        return job_data
