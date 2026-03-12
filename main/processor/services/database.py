import json
import os
import sys
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


class PipelineDatabase:
    """Manages access to the main database and job_data.json files."""

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def get_completed_episodes(self) -> List[PodcastEpisode]:
        """Returns episodes that have completed transcription."""
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
        session = self.session_factory()
        try:
            return session.query(PodcastSeason).order_by(PodcastSeason.code).all()
        finally:
            session.close()

    def get_episode_by_id(self, episode_id: int) -> Optional[PodcastEpisode]:
        """Fetch a specific completed episode by ID."""
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

    def get_episode_directory(self, episode_id: int) -> Optional[Path]:
        """Gets the directory path for a given episode ID."""
        session = self.session_factory()
        try:
            path_record = (
                session.query(PodcastPath)
                .filter(PodcastPath.episode_id == episode_id)
                .first()
            )
            if path_record:
                return Path(path_record.file_path).parent
            return None
        finally:
            session.close()

    def load_job_data(self, episode_dir: Path) -> JobData:
        """Loads job_data.json from the episode directory."""
        json_path = episode_dir / "job_data.json"

        if not json_path.exists():
            return JobData()

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return JobData.from_dict(data)
        except (json.JSONDecodeError, Exception) as e:
            return JobData()

    def save_job_data(self, episode_dir: Path, job_data: JobData):
        """Saves the JobData instance to job_data.json."""
        json_path = episode_dir / "job_data.json"
        episode_dir.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(job_data.to_dict(), f, indent=4)

    def initialize_job_data(self, episode_id: int) -> Optional[JobData]:
        """Ensures job_data.json is synced with the current schema."""
        episode_dir = self.get_episode_directory(episode_id)
        if not episode_dir:
            return None

        job_data = self.load_job_data(episode_dir)
        self.save_job_data(episode_dir, job_data)
        return job_data
