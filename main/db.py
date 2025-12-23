import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Build the path to the database file within the 'main' directory
db_path = Path(__file__).parent / "podcast.db"
logger.info(f"Database path set to: {db_path}")

Base = declarative_base()
engine = sa.create_engine(f"sqlite:///{db_path}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
