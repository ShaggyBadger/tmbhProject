import sys
import os

# Add the project root to sys.path
root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
sys.path.append(root_dir)

# Add the 'main' directory to sys.path so 'import db' works
main_dir = os.path.join(root_dir, "main")
sys.path.append(main_dir)

from db import SessionLocal
from models import PodcastEpisode, PodcastInfo, PodcastPath


def test_db_connection():
    # Create a new session
    db = SessionLocal()
    try:
        # Example Query: Get the first 5 episodes
        episodes = db.query(PodcastEpisode).limit(5).all()

        print(f"Found {len(episodes)} episodes:")
        for ep in episodes:
            print(f"- {ep.title} (Status: {ep.download_status})")

        # Example Query: Count total episodes
        count = db.query(PodcastEpisode).count()
        print(f"\nTotal episodes in database: {count}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Always close the session
        db.close()


def clear_json():
    db = SessionLocal()
    try:
        episodes = db.query(PodcastEpisode.id).all()
        episodes = [e[0] for e in episodes]

        test_episode = episodes[34]

        paths = (
            db.query(PodcastPath).filter(PodcastPath.episode_id == test_episode).all()
        )
        for i in paths:
            print(i.file_path)

    except Exception as e:
        print(f"Error: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    # test_db_connection()
    clear_json()
