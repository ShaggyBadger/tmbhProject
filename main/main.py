from curses.ascii import RS
import json
from encodings.punycode import T
import feedparser
import re
import requests
from tqdm import tqdm
from db import SessionLocal
from models import PodcastInfo, PodcastSeason, PodcastEpisode, RssUrls, JobDeployment
from models import PodcastPath, JobDeployment
from sqlalchemy.orm import selectinload
from sqlalchemy import or_
from pathlib import Path
from rich.traceback import install
import logging
from logging_config import setup_logging

install(show_locals=True)
logger = logging.getLogger(__name__)

class PodcastCollection:
    '''
    Docstring for PodcastCollection
    
    This class handles the collection and storage of podcast data from an RSS feed.
    It uses the feedparser library to parse the RSS feed and SQLAlchemy to interact
    with the database.
    '''
    def __init__(self, url="https://feeds.buzzsprout.com/2544823.rss"):
        logger.info(f"Initializing PodcastCollection with URL: {url}")
        self.url = url
        self.parsed = feedparser.parse(url) # Parsed feed
        self.feed = self.parsed.feed # FeedParserDict with general podcast info
        self.podcast_info = self.extract_podcast_metadata() # Dict with podcast metadata
        self.podcast_entries = self.parsed.entries # List of podcast episodes (FeedParserDicts)
        self.podcast_entries.reverse() # Reverse to process from oldest to newest
        logger.info(f"Found {len(self.podcast_entries)} episodes in the feed.")
    
    def standard_flow(self):
        # run this method to extract and store podcast info from the feed
        logger.info("Starting standard podcast collection flow...")
        session = SessionLocal()
        try:
            logger.info("Saving podcast metadata...")
            podcast_metadata = self.save_podcast_metadata(session)
            logger.info("Podcast metadata saved.")

            logger.info("Beginning method to save RSS URL...")
            self.save_rss_url(session, podcast_metadata)
            logger.info("RSS URL saving complete.")

            # save episode info in database
            logger.info("Saving episodes...")
            for entry in self.podcast_entries:
                # get intel for this episode
                episode_info = self.extract_episode_info(entry)

                # save episode info in the database
                episode_id = self.save_episodes(session, episode_info)

                # build path structure for episode
                if episode_id:
                    self.build_episode_paths(session, episode_info, episode_id)
            logger.info("Episodes saved in the database.")
        finally:
            session.close()
            logger.info("Database session closed.")

    def extract_podcast_metadata(self):
        feed = self.feed
        podcast_info = {
            "title": feed.get("title", ""),
            "subtitle": feed.get("subtitle", ""),
            "subtitle_detail": feed.get("subtitle_detail", ""),
            "authors": feed.get("authors", ""),
            "author": feed.get("author", ""),
            "author_detail": feed.get("author_detail", ""),
            "link": feed.get("link", ""),
            "language": feed.get("language", ""),
            "itunes_type": feed.get("itunes_type", ""),
            "itunes_explicit": feed.get("itunes_explicit", ""),
            "image": feed.get("image", ""),
        }
        logger.debug(f"Extracted podcast metadata for '{podcast_info['title']}'")
        return podcast_info

    def save_podcast_metadata(self, session):
        '''
        Extract general podcast info from the feed and save to the database.
        This is not for individual episiodes, but the overall podcast metadata.
        '''
        
        logger.info("Checking for existing podcast info in the database...")
        query = session.query(PodcastInfo)
        query = query.filter_by(title=self.podcast_info.get("title"))
        existing_podcast = query.first()

        if existing_podcast:
                logger.info("Podcast info already exists in the database.")
                return existing_podcast

        try:
            logger.info("Adding new podcast info to the database...")
            new_podcast = PodcastInfo(**self.podcast_info)
            session.add(new_podcast)
            session.commit()
            logger.info(f"Podcast info for '{new_podcast.title}' added to the database with ID {new_podcast.id}.")
            return new_podcast
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error occurred while adding podcast info: {e}", exc_info=True)
            return None
                
    def save_rss_url(self, session, podcast_metadata):
        # ensure the RSS feed URL is saved to the database
        url = self.url
        
        try:
            if not podcast_metadata:
                logger.error("Podcast metadata not provided. Cannot save RSS URL.")
                return

            podcast_id = podcast_metadata.id

            query = session.query(RssUrls)
            query = query.filter_by(rss_url=url, podcast_id=podcast_id)
            existing_rss = query.first()

            if existing_rss:
                logger.info(f"RSS URL '{url}' already exists in the database.")
                return
            
            logger.info(f"Entering RSS URL '{url}' into the database...")
            new_rss = RssUrls(rss_url=url, podcast_id=podcast_id)
            session.add(new_rss)
            session.commit()
            logger.info("RSS URL saved to the database.")

        except Exception as e:
            session.rollback()
            logger.error(f"Error occurred while saving RSS URL: {e}", exc_info=True)

    def save_season_names(self):
        '''
        So this is a weird one. I don't want to run it every time because it will
        keep asking about the oddball episodes. This will have to be run manually
        when needed.
        '''
        logger.info("Starting process to save season names.")
        season_names = []
        oddballs = []
        
        for entry in self.podcast_entries:
            title = entry.title
            match = re.match(r"([A-Z]+)\d+", title)
            if match:
                season_name = match.group(1)
                if season_name not in season_names:
                    season_names.append(season_name)
                    logger.debug(f"Found season name '{season_name}' from title: {title}")
            else:
                oddballs.append(title)
                logger.debug(f"Found oddball title (no season match): {title}")
        
        if oddballs:
            logger.info(f"Found {len(oddballs)} oddball episodes to categorize.")
            for oddball in oddballs:
                print('\n*********************\n')
                for i, season in enumerate(season_names, start=1):
                    print(f"{i}: {season}")
                print(f"\nOddball episode title: {oddball}\n")

                while True:
                    user_input = input("Enter number or new season name: ").strip()
                    
                    if user_input.isdigit():
                        idx = int(user_input) - 1
                        if 0 <= idx < len(season_names):
                            chosen_season = season_names[idx]
                            logger.info(f"User assigned '{oddball}' to existing season '{chosen_season}'.")
                            break
                        else:
                            print("Invalid number. Try again.")
                    elif user_input:
                        chosen_season = user_input
                        if chosen_season not in season_names:
                            season_names.append(chosen_season)
                            logger.info(f"User created new season '{chosen_season}' for '{oddball}'.")
                        else:
                            logger.info(f"User assigned '{oddball}' to existing season '{chosen_season}'.")
                        break
                    else:
                        print("Input cannot be empty. Try again.")

                print(f"Episode '{oddball}' assigned to season '{chosen_season}'")
        
        logger.info(f"Identified seasons for saving: {season_names}")
        input('Press Enter to confirm and save these seasons to the database...')
        session = SessionLocal()
        try:
            for season_name in season_names:
                existing_season = session.query(PodcastSeason).filter_by(code=season_name).first()

                if existing_season:
                    logger.info(f"Season '{season_name}' already exists in the database.")
                    continue
                
                podcast_info = session.query(PodcastInfo).filter_by(title=self.feed.title).first()

                if not podcast_info:
                    logger.error("Podcast info not found in the database. Cannot save season.")
                    continue

                logger.info(f"Saving season '{season_name}' to the database...")
                new_season = PodcastSeason(code=season_name, podcast_id=podcast_info.id)
                session.add(new_season)
                session.commit()
                logger.info(f"Season '{season_name}' saved to the database.")
        except Exception as e:
            session.rollback()
            logger.error(f"Error occurred while saving season '{season_name}': {e}", exc_info=True)
        finally:
            session.close()

    def extract_episode_info(self, entry):
        episode_info = {
            "itunes_title": entry.get("itunes_title", ""),
            "title": entry.get("title", ""),
            "title_detail": entry.get("title_detail", ""),
            "summary": entry.get("summary", ""),
            "summary_detail": entry.get("summary_detail", ""),
            "content": entry.get("content", ""),
            "image": entry.get("image", ""),
            "authors": entry.get("authors", ""),
            "author": entry.get("author", ""),
            "author_detail": entry.get("author_detail", ""),
            "links": entry.get("links", ""),
            "guid": entry.get("id", ""),
            "guidislink": entry.get("guidislink", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "published_parsed": entry.get("published_parsed", ""),
            "itunes_duration": entry.get("itunes_duration", ""),
            "itunes_episodetype": entry.get("itunes_episodetype", ""),
            "itunes_explicit": entry.get("itunes_explicit", ""),
        }
        return episode_info

    def select_episode_season(self, session, episode_info, podcast_id):
        seasons = session.query(PodcastSeason).filter_by(podcast_id=podcast_id).all()
        
        title = episode_info.get("title")
        match = re.match(r"([A-Z]+)\d+", title)

        if match:
            season_name = match.group(1)
            season_entry = session.query(PodcastSeason).filter_by(code=season_name, podcast_id=podcast_id).first()

            if season_entry:
                episode_info['season_id'] = season_entry.id
                logger.debug(f"Automatically matched episode '{title}' to season '{season_name}'.")
                return season_entry.id
            else:
                logger.critical(f"Season '{season_name}' extracted from episode '{title}' but not found in database. Exiting.")
                exit(1)

        logger.warning(f"Could not determine season for episode '{title}'. Manual selection required.")
        print('\n*********************\n')
        print(f"Episode title: {title}\n")
        links = episode_info.get("links", [])[0]
        print(f"Episode link: {links.get('href', 'N/A')}\n")
        print("Available seasons:")

        for i, season in enumerate(seasons, start=1):
            print(f"{i}: {season.code}")
        print("\n")

        while True:
            user_input = input("Enter number for this episode: ").strip()
            
            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(seasons):
                    chosen_season = seasons[idx]
                    break
                else:
                    print("Invalid number. Try again.")
            else:
                print("Invalid entry. Please try again...")

        logger.info(f"User assigned episode '{title}' to season '{chosen_season.code}'.")
        return chosen_season.id

    def save_episodes(self, session, episode_info):
        guid = episode_info.get("guid")
        existing_episode = session.query(PodcastEpisode).filter_by(guid=guid).first()
        title = episode_info.get('title')

        if existing_episode:
            logger.debug(f"Episode '{title}' (GUID: {guid}) already exists. Skipping.")
            return existing_episode.id

        try:
            logger.info(f"Saving episode '{title}' to the database...")
            new_episode = PodcastEpisode(**episode_info)

            rss_entry = session.query(RssUrls).filter_by(rss_url=self.url).first()
            podcast_id = rss_entry.podcast_id

            if podcast_id:
                new_episode.podcast_id = podcast_id
            
            season_id = self.select_episode_season(session, episode_info, podcast_id)
            new_episode.season_id = season_id

            url_link = episode_info.get("links", [])[0].get("href", "")
            new_episode.link = url_link

            session.add(new_episode)
            session.commit()
            logger.info(f"Episode '{title}' saved with ID {new_episode.id}.")
            return new_episode.id

        except Exception as e:
            session.rollback()
            logger.error(f"Error saving episode '{title}': {e}", exc_info=True)
            return None

    def build_episode_paths(self, session, episode_info, episode_id):
        existing_path = session.query(PodcastPath).filter_by(episode_id=episode_id).first()
        if existing_path:
            logger.debug(f"Path for episode ID {episode_id} already exists. Skipping path generation.")
            return existing_path.file_path

        script_dir = Path(__file__).parent.resolve()
        PODCAST_FILES_DIR = script_dir / "podcast_files"
        PODCAST_FILES_DIR.mkdir(parents=True, exist_ok=True)

        rss_entry = session.query(RssUrls).filter_by(rss_url=self.url).first()
        podcast_id = rss_entry.podcast_id

        if not podcast_id:
            logger.error(f"Podcast ID not found for RSS URL {self.url}. Cannot build episode paths.")
            return

        cleaned_name = re.sub(r'\W+', '_', self.podcast_info.get('title').lower())
        PODCAST_DIR = PODCAST_FILES_DIR / f"{podcast_id}_{cleaned_name}"
        PODCAST_DIR.mkdir(parents=True, exist_ok=True)

        season_id = episode_info.get("season_id")
        season_entry = session.query(PodcastSeason).filter_by(id=season_id).first()
        season_name = season_entry.code if season_entry else "unknown_season"
        cleaned_season_name = re.sub(r'\W+', '_', season_name.lower())
        SEASON_DIR = PODCAST_DIR / f"{cleaned_season_name}"
        SEASON_DIR.mkdir(parents=True, exist_ok=True)

        episode_title = episode_info.get("title", "untitled_episode")
        cleaned_episode_title = re.sub(r'\W+', '_', episode_title.lower())
        EPISODE_DIR = SEASON_DIR / f"{episode_id}_{cleaned_episode_title}"
        EPISODE_DIR.mkdir(parents=True, exist_ok=True)

        audio_file_name = f"{episode_id}_{cleaned_episode_title}.mp3"
        audio_file_path = EPISODE_DIR / audio_file_name

        try:
            logger.debug(f"Saving episode path for episode '{episode_title}'...")
            new_path = PodcastPath(
                episode_id=episode_id,
                file_path=str(audio_file_path),
                file_name=str(audio_file_name),
                file_type="audio"
            )
            session.add(new_path)
            session.commit()
            logger.debug(f"Episode path for '{episode_title}' saved.")
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving episode path for '{episode_title}': {e}", exc_info=True)

        return audio_file_path
        
class PodcastDownloader:
    '''
    This class handles downloading podcast episodes given their metadata
    and file paths.
    '''
    def get_pending_downloads(self):
        """
        Query the database for all episodes with a 'pending' or 'failed' download status.
        """
        session = SessionLocal()
        try:
            target_statuses = ['pending', 'failed']
            logger.info(f"Querying for episodes with download status in {target_statuses}")
            query = session.query(PodcastEpisode)
            query = query.options(selectinload(PodcastEpisode.paths))
            query = query.filter(PodcastEpisode.download_status.in_(target_statuses))
            pending_episodes = query.all()
            logger.info(f"Found {len(pending_episodes)} episodes to download.")
            return pending_episodes
        finally:
            session.close()

    def download_episode(self, episode):
        """
        Download a single podcast episode.
        """
        session = SessionLocal()
        try:
            episode = session.merge(episode)
            
            download_url = episode.link
            file_path = Path(episode.paths[0].file_path)

            if not download_url:
                logger.warning(f"Skipping {episode.title} - No download URL found.")
                episode.download_status = 'failed'
                session.commit()
                return

            logger.info(f"Starting download: {episode.title}")
            file_path.parent.mkdir(parents=True, exist_ok=True)

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
            }

            with requests.get(download_url, stream=True, headers=headers) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                
                with open(file_path, 'wb') as f, tqdm(
                    total=total_size,
                    unit='iB',
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=episode.title[:40]
                ) as progress_bar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            size = f.write(chunk)
                            progress_bar.update(size)

            downloaded_size = file_path.stat().st_size
            if total_size != 0 and downloaded_size < total_size:
                logger.warning(f"Incomplete download: {episode.title}. Expected {total_size}, got {downloaded_size}")
                episode.download_status = 'failed'
            else:
                episode.download_status = 'downloaded'
                logger.info(f"Finished download: {episode.title}")

            session.commit()

        except Exception as e:
            logger.error(f"Error downloading {episode.title}: {e}", exc_info=True)
            episode.download_status = 'failed'
            session.commit()
        finally:
            session.close()

    def start_downloads(self):
        """
        Orchestrates the downloading of pending podcast episodes sequentially.
        """
        pending_episodes = self.get_pending_downloads()
        
        if not pending_episodes:
            logger.info("No episodes are pending download.")
        else:
            for episode in pending_episodes:
                self.download_episode(episode)

class DeployPodcastProcessing:
    '''
    This class handles deploying podcast processing jobs.
    '''
    def __init__(self,
                 priority_level='low',
                 fastapi_url="http://192.168.68.66:5000/new-job"
                 ):
        self.priority_level = priority_level
        self.fastapi_url = fastapi_url
        self.mp3s_to_deploy = self.find_mp3s()

        if not self.mp3s_to_deploy:
            logger.info("No MP3 files found for deployment.")
        else:
            for episode in self.mp3s_to_deploy:
                self.deploy_mp3(episode)
        
        logger.info('Deployment process complete.')
    
    def find_mp3s(self):
        logger.info("Finding MP3 files to deploy...")
        session = SessionLocal()
        try:
            query = session.query(PodcastEpisode)
            query = query.options(selectinload(PodcastEpisode.paths))
            query = query.filter(
                PodcastEpisode.download_status == 'downloaded',
                or_(
                    PodcastEpisode.transcription_status == 'pending',
                    PodcastEpisode.transcription_status == 'failed_deployment'
                    )
                )
            query = query.order_by(PodcastEpisode.id.asc())

            mp3_list = query.all()
            if mp3_list:
                logger.info(f"Found {len(mp3_list)} MP3 files to deploy.")
                input('Press Enter to continue...')
            return mp3_list
        finally:
            session.close()
    
    def deploy_mp3(self, episode):
        logger.info(f'Deploying processing job for episode: {episode.title}...')

        if not episode.paths:
            logger.warning(f"No file path found for episode: {episode.title}. Skipping deployment.")
            return

        file_path = Path(episode.paths[0].file_path)
        file_name = episode.paths[0].file_name

        if not file_path.exists():
            logger.error(f"File not found at {file_path} for episode: {episode.title}. Skipping deployment.")
            # TODO : update episode status to indicate missing file
            return

        try:
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f, 'audio/mpeg')}
                data = {'priority_level': self.priority_level, 'filename': file_name}

                response = requests.post(self.fastapi_url, files=files, data=data)
                response.raise_for_status()
                
                logger.info(f"Successfully deployed {file_name}.")
                
                response_data = response.json()
                job_ulid = response_data.get("job_ulid")
                job_status_from_server = response_data.get("status")

                session = SessionLocal()
                try:
                    episode = session.merge(episode)
                    episode.transcription_status = 'deployed'

                    new_job_deployment = JobDeployment(
                        epidode_id=episode.id,
                        ulid=job_ulid,
                        job_status=job_status_from_server
                    )
                    session.add(new_job_deployment)
                    session.commit()
                    logger.info(f"JobDeployment for episode {episode.title} (ULID: {job_ulid}) created with status '{job_status_from_server}'.")
                except Exception as e:
                    session.rollback()
                    logger.error(f"DB Error for {episode.title} post-deployment: {e}", exc_info=True)
                finally:
                    session.close()

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error deploying {file_name}: {e}", exc_info=True)
            self.update_episode_status_on_failure(episode, 'failed_deployment')
        except IOError as e:
            logger.error(f"File error for {file_name}: {e}", exc_info=True)
            self.update_episode_status_on_failure(episode, 'failed_deployment')
        except Exception as e:
            logger.critical(f"Unexpected error deploying {file_name}: {e}", exc_info=True)
            self.update_episode_status_on_failure(episode, 'failed_deployment')

    def update_episode_status_on_failure(self, episode, status):
        session = SessionLocal()
        try:
            episode = session.merge(episode)
            episode.transcription_status = status
            session.commit()
            logger.info(f"Updated episode {episode.title} status to '{status}'.")
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to update episode status for {episode.title} after error: {e}", exc_info=True)
        finally:
            session.close()

class RecoverPodcastTranscripts:
    def __init__(self):
        self.fastapi_url="http://192.168.68.66:5000"
        self.ulids_completed = self.query_server_for_completed_jobs()
        logger.info(f"Found {len(self.ulids_completed)} completed jobs to download.")
        
        if self.ulids_completed:
            for ulid in self.ulids_completed:
                self.download_completed_job(ulid)
    
    def check_job_status(self, ulid):
        '''just a method to do get requests. Gonna combine with threading probably'''
        url = f"{self.fastapi_url}/report-job-status/{ulid}"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get('status')
        except requests.exceptions.RequestException as e:
            logger.error(f"Error checking status for ULID {ulid}: {e}")
            return None

    def query_server_for_completed_jobs(self):
        '''Return a list of ULID's ready to be downloaded from server'''
        session = SessionLocal()
        logger.info("Querying for completed jobs...")

        try:
            query = session.query(JobDeployment)
            query = query.filter(JobDeployment.job_status.in_(["pending", "deployed"]))
            job_list = query.all()

            ulids = [job.ulid for job in job_list] # make list of ulids
            logger.info(f"Found {len(ulids)} pending jobs to check.")

            completed_ulids = []

            for ulid in ulids:
                status = self.check_job_status(ulid)

                if status == 'completed':
                    # also update the job status in the database
                    job = session.query(JobDeployment).filter(JobDeployment.ulid == ulid).first()
                    if job:
                        job.job_status = 'completed'
                        session.commit()

                    completed_ulids.append(ulid)
            
            return completed_ulids
    
        except Exception as e:
            logger.error(f'Exception occurred while querying for jobs: {e}', exc_info=True)
            return []
        finally:
            session.close()
    
    def download_completed_job(self, ulid):
        '''Downloads a transcript, saves it, and updates the database.'''
        logger.info(f"Downloading transcript for job ULID: {ulid}")
        session = SessionLocal()
        try:
            # 1. Find the Job and related Episode/Paths
            # start the query
            query = session.query(JobDeployment)

            # add eager-loading options
            query = query.options(
                selectinload(JobDeployment.episode)
                    .selectinload(PodcastEpisode.paths)
            )

            # apply filters
            query = query.filter(JobDeployment.ulid == ulid)

            # execute
            job = query.first()


            if not job:
                logger.error(f"Job with ULID {ulid} not found in the database.")
                return

            if not job.episode or not job.episode.paths:
                logger.error(f"Episode or path info missing for job ULID {ulid}.")
                return

            # 2. Determine the transcript path
            audio_path = Path(job.episode.paths[0].file_path)
            transcript_path = audio_path.parent / f"{audio_path.stem}.txt"
            logger.debug(f"Determined transcript path: {transcript_path}")

            # 3. Download the transcript
            download_url = f"{self.fastapi_url}/retrieve-job/{ulid}"
            try:
                response = requests.get(download_url)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to download transcript for ULID {ulid}: {e}")
                job.job_status = 'download_failed'
                session.commit()
                return

            # 4. Save the file
            try:
                transcript_path.parent.mkdir(parents=True, exist_ok=True)
                transcript_path.write_text(response.text, encoding='utf-8')
                logger.info(f"Transcript for {ulid} saved to {transcript_path}")
            except IOError as e:
                logger.error(f"Failed to write transcript to disk for ULID {ulid}: {e}")
                job.job_status = 'download_failed'
                session.commit()
                return

            # 5. Update the database
            # Create a new PodcastPath for the transcript
            new_path = PodcastPath(
                episode_id=job.episode.id,
                file_path=str(transcript_path),
                file_name=transcript_path.name,
                file_type='transcript'
            )
            session.add(new_path)
            logger.debug(f"Created new PodcastPath entry for transcript: {transcript_path.name}")

            # Update JobDeployment status
            job.job_status = 'retrieved'
            logger.debug(f"Updated JobDeployment status to 'retrieved' for ULID {ulid}")
            
            # Update PodcastEpisode status
            episode = job.episode
            episode.transcription_status = 'completed'
            logger.debug(f"Updated PodcastEpisode '{episode.title}' transcription_status to 'completed'.")

            session.commit()
            logger.info(f"Successfully processed and updated database for job {ulid}.")

        except Exception as e:
            logger.error(f'An unexpected error occurred during download process for {ulid}: {e}', exc_info=True)
            session.rollback()
        finally:
            session.close()

if __name__ == "__main__":
    setup_logging()
    url = "https://feeds.buzzsprout.com/2544823.rss"

    options = {
        '1': 'Start podcast collection flow',
        '2': 'Download Podcast episodes',
        '3': 'Deploy podcast processing jobs',
        '4': 'Recover completed transcripts from server',
        'q': 'Quit'
    }

    while True:
        logger.info('\n*****Program initiated*****')
        print("\nSelect an option:")
        for option in options:
            print(f"{option}: {options[option]}")
        
        choice = input("Enter option number: ").strip()

        if choice == '1':
            collector = PodcastCollection(url)
            collector.standard_flow()
        
        elif choice == '2':
            downloader = PodcastDownloader()
            downloader.start_downloads()

        elif choice == '3':
            deployer = DeployPodcastProcessing()
        
        elif choice == '4':
            recovery_agent = RecoverPodcastTranscripts()
        
        elif choice.lower() == 'q':
            logger.info("User chose to quit. Exiting program.")
            exit(0)