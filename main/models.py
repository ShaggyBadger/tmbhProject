import db
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
# Helper function to get current UTC time
def utcnow():
    return datetime.now(timezone.utc)

class PodcastInfo(db.Base):
    """Holds general podcast metadata parsed from RSS feed"""
    __tablename__ = "podcast_info"

    id = Column(Integer, primary_key=True)
    title = Column(String)
    subtitle = Column(String)
    subtitle_detail = Column(JSON)
    authors = Column(JSON)
    author = Column(String)
    author_detail = Column(JSON)
    link = Column(String)
    language = Column(String)
    itunes_type = Column(String)
    itunes_explicit = Column(String)
    image = Column(JSON)

    # Relationships
    seasons = relationship("PodcastSeason", back_populates="podcast")
    episodes = relationship("PodcastEpisode", back_populates="podcast")
    rss_urls = relationship("RssUrls", back_populates="podcast")

class PodcastSeason(db.Base):
    """Holds podcast season information parsed from RSS feed"""
    __tablename__ = "podcast_seasons"

    id = Column(Integer, primary_key=True)
    code = Column(String)
    podcast_id = Column(Integer, ForeignKey("podcast_info.id"))

    # Relationships
    podcast = relationship("PodcastInfo", back_populates="seasons")
    episodes = relationship("PodcastEpisode", back_populates="season")

class PodcastEpisode(db.Base):
    """Holds podcast episode information parsed from RSS feed"""
    __tablename__ = "podcast_episodes"

    id = Column(Integer, primary_key=True)
    itunes_title = Column(String)
    title = Column(String)
    title_detail = Column(JSON)
    summary = Column(String)
    summary_detail = Column(JSON)
    content = Column(JSON)
    image = Column(JSON)
    authors = Column(JSON)
    author = Column(String)
    author_detail = Column(JSON)
    links = Column(JSON)
    guid = Column(String, unique=True, index=True) # stored as 'id' in feedparser
    guidislink = Column(String)
    link = Column(String)
    published = Column(String)
    published_parsed = Column(JSON)
    itunes_duration = Column(String)
    itunes_episodetype = Column(String)
    itunes_explicit = Column(String)
    download_status = Column(String, default='pending')  # e.g. "pending", "downloaded", "failed"

    # Foreign keys
    season_id = Column(Integer, ForeignKey("podcast_seasons.id"))
    podcast_id = Column(Integer, ForeignKey("podcast_info.id"))

    # Relationships
    season = relationship("PodcastSeason", back_populates="episodes")
    podcast = relationship("PodcastInfo", back_populates="episodes")
    paths = relationship("PodcastPath", back_populates="episode")

class PodcastPath(db.Base):
    __tablename__ = "podcast_paths"

    id = Column(Integer, primary_key=True)
    episode_id = Column(Integer, ForeignKey("podcast_episodes.id"), nullable=False)
    file_path = Column(String, nullable=False, unique=True)
    file_type = Column(String, nullable=False, default='audio')   # e.g. "audio", "transcript", "cleaned"
    created_at = Column(DateTime, default=utcnow)

    # relationship
    episode = relationship("PodcastEpisode", back_populates="paths")

class RssUrls(db.Base):
    __tablename__ = "rss_urls"

    id = Column(Integer, primary_key=True)
    podcast_id = Column(Integer, ForeignKey("podcast_info.id"), nullable=False)
    rss_url = Column(String, nullable=False, unique=True)
    added_at = Column(DateTime(timezone=True), default=utcnow)
    last_checked_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    status = Column(String, default="current")
    error_message = Column(String, nullable=True)

    podcast = relationship("PodcastInfo", back_populates="rss_urls")
