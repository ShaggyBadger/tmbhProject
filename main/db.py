import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker
from pathlib import Path

# Build the path to the database file within the 'main' directory
db_path = Path(__file__).parent / "podcast.db"

Base = declarative_base()
engine = sa.create_engine(f"sqlite:///{db_path}")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
