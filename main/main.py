from curses.ascii import RS
import json
from encodings.punycode import T
import feedparser
import re
import requests
from tqdm import tqdm
from db import SessionLocal
from models import PodcastInfo, PodcastSeason, PodcastEpisode, RssUrls
from models import PodcastPath, JobDeployment
from sqlalchemy.orm import selectinload
from sqlalchemy import or_
from pathlib import Path
import time
from rich.traceback import install
install(show_locals=True)

class PodcastCollection:
    '''
    Docstring for PodcastCollection
    
    This class handles the collection and storage of podcast data from an RSS feed.
    It uses the feedparser library to parse the RSS feed and SQLAlchemy to interact
    with the database.
    '''
    def __init__(self, url="https://feeds.buzzsprout.com/2544823.rss"):
        self.url = url
        self.parsed = feedparser.parse(url) # Parsed feed
        self.feed = self.parsed.feed # FeedParserDict with general podcast info
        self.podcast_info = self.extract_podcast_metadata() # Dict with podcast metadata
        self.podcast_entries = self.parsed.entries # List of podcast episodes (FeedParserDicts)
        self.podcast_entries.reverse() # Reverse to process from oldest to newest
    
    def standard_flow(self):
        # run this method to extract and store podcast info from the feed
        print("Starting standard podcast collection flow...")
        session = SessionLocal()
        try:
            time.sleep(1)

            print("Saving podcast metadata...")
            podcast_metadata = self.save_podcast_metadata(session)
            print('Podcast metadata saved.\n\n')
            time.sleep(1)

            print("beginning method to save RSS URL...")
            self.save_rss_url(session, podcast_metadata)
            print('RSS URL saving complete.\n\n')
            time.sleep(1)

            # save episode info in database
            print("Saving episodes...")
            for entry in self.podcast_entries:
                # get intel for this episode
                episode_info = self.extract_episode_info(entry)

                # save episode info in the database
                episode_id = self.save_episodes(session, episode_info)

                # build path structure for episode
                if episode_id:
                    self.build_episode_paths(session, episode_info, episode_id)
            print('Episodes saved in the database.\n\n')
            time.sleep(1)
        finally:
            session.close()
            print("Database session closed.")

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

        return podcast_info

    def save_podcast_metadata(self, session):
        '''
        Extract general podcast info from the feed and save to the database.
        This is not for individual episiodes, but the overall podcast metadata.

        Steps:
        1. Extract relevant fields from the feed.
        2. Check if this podcast info already exists in the database.
        3. If not, create a new PodcastInfo entry and save it.
        4. Handle exceptions and ensure session is closed.
        5. Print status messages throughout the process.
        '''
        
        # check if this podcast info is already in the database
        print('Checking for existing podcast info in the database...')
        query = session.query(PodcastInfo)
        query = query.filter_by(title=self.podcast_info.get("title"))
        existing_podcast = query.first()

        if existing_podcast:
                print('Podcast info already exists in the database.')
                return existing_podcast

        try:
            print('Adding new podcast info to the database...')
            new_podcast = PodcastInfo(**self.podcast_info)
            session.add(new_podcast)
            session.commit()
            print('Podcast info added to the database.')
            return new_podcast
            
        except Exception as e:
            session.rollback()
            print(f"Error occurred while adding podcast info: {e}")
            return None
                
    def save_rss_url(self, session, podcast_metadata):
        # ensure the RSS feed URL is saved to the database
        url = self.url
        
        try:
            # Use the passed podcast_metadata directly
            if not podcast_metadata:
                print("Error: Podcast metadata not provided. Cannot save RSS URL.")
                return

            podcast_id = podcast_metadata.id

            # Now, check if the RSS URL already exists for this podcast
            query = session.query(RssUrls)
            query = query.filter_by(rss_url=url, podcast_id=podcast_id)
            existing_rss = query.first()

            if existing_rss:
                # the RSS URL is already saved
                print("RSS URL already exists in the database.")
                return
            
            # save the RSS URL
            print("Entering RSS URL into the database...")
            new_rss = RssUrls(rss_url=url, podcast_id=podcast_id)
            session.add(new_rss)
            session.commit()
            print("RSS URL saved to the database.")

        except Exception as e:
            # rollback in case of error
            session.rollback()
            print(f"Error occurred while saving RSS URL: {e}")

    def save_season_names(self):
        '''
        So this is a weird one. I don't want to run it every time because it will
        keep asking about the oddball episodes. This will have to be run manually
        when needed.
        1. Extract season names from episode titles using regex.
        2. Identify oddball episodes that don't match the pattern.
        3. Prompt user to assign oddball episodes to existing or new seasons.
        4. Save all season names to the database.
        '''
        # get the unique season names from the podcast entries
        season_names = []

        # list to hold odball episodes that don't match the pattern
        oddballs = []
        
        # regex pattern to match season names (e.g., "S1", "S2", "SPECIAL1", etc.)
        for entry in self.podcast_entries:
            title = entry.title
            match = re.match(r"([A-Z]+)\d+", title)
            if match:
                season_name = match.group(1)
                if season_name not in season_names:
                    season_names.append(season_name)
            else:
                oddballs.append(title)
        
        # now we go through oddball episodes and assign them to a season
        if oddballs:
            for oddball in oddballs:
                print('\n*********************\n')
                # Print numbered list of existing seasons
                for i, season in enumerate(season_names, start=1):
                    print(f"{i}: {season}")
                print(f"\nOddball episode title: {oddball}\n")

                # Prompt user input
                while True:
                    user_input = input("Enter number or new season name: ").strip()
                    
                    if user_input.isdigit():
                        idx = int(user_input) - 1
                        if 0 <= idx < len(season_names):
                            print(f'Valid number selected: {season_names[idx]}')
                            chosen_season = season_names[idx]
                            break
                        else:
                            print("Invalid number. Try again.")
                    elif user_input:
                        chosen_season = user_input
                        # Add to season set if it's a new one
                        if chosen_season not in season_names:
                            season_names.append(chosen_season)
                        break
                    else:
                        print("Input cannot be empty. Try again.")

                print(f"Episode '{oddball}' assigned to season '{chosen_season}'")
        
        # save the season names to the database
        # add quick verification step
        for season in season_names:
            print(f"Identified season: {season}")
        input('Press Enter to confirm and save these seasons to the database...')
        session = SessionLocal()

        for season_name in season_names:
            # check if the season already exists for this podcast
            query = session.query(PodcastSeason)
            query = query.filter_by(code=season_name)
            existing_season = query.first()

            if existing_season:
                print(f"Season '{season_name}' already exists in the database.")
                continue
            
            # find the podcast info entry id
            query = session.query(PodcastInfo)
            query = query.filter_by(title=self.feed.title)
            podcast_info = query.first()

            if not podcast_info:
                print("Podcast info not found in the database. Cannot save season.")
                continue

            try:
                # save the new season
                print(f"Saving season '{season_name}' to the database...")
                new_season = PodcastSeason(code=season_name, podcast_id=podcast_info.id)
                session.add(new_season)
                session.commit()
                print(f"Season '{season_name}' saved to the database.")
            except Exception as e:
                session.rollback()
                print(f"Error occurred while saving season '{season_name}': {e}")

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
        # use this to select the season for an episode based on its title
        # collect available season names. put the whole season objects in a list
        query = session.query(PodcastSeason)
        query = query.filter_by(podcast_id=podcast_id)
        seasons = query.all()
        
        # try to extract season name from episode title
        title = episode_info.get("title")
        match = re.match(r"([A-Z]+)\d+", title)

        if match:
            # this means we found a season name in the title
            season_name = match.group(1)
            query = session.query(PodcastSeason)
            query = query.filter_by(code=season_name, podcast_id=podcast_id)
            season_entry = query.first()

            if season_entry:
                # the sesaon name was found in the database
                episode_info['season_id'] = season_entry.id
                return season_entry.id
            else:
                # season name successfully extracted from title but not found in DB
                # TODO: handle this better. Maybe add way to input the season
                # name into the database on the fly?
                print(f"Season '{season_name}' extracted from episode '{title}' but not found in database.")
                print('please verify season names in the database. Maybe run the',
                      'utiltiy to save season names again?')
                print('Exiting the program for now.')
                exit(1)

        # ok so if there is no season match found in the title, we need to
        # prompt the user to see what season this episode belongs to
        print('\n*********************\n')
        print(f"Episode title: {title}\n")
        links = episode_info.get("links", [])[0]
        print(f"Episode link: {links.get('href', 'N/A')}\n")

        print("Available seasons:")

        # print out the season options
        for i, season in enumerate(seasons, start=1):
            print(f"{i}: {season.code}")
        print("\n")

        # Prompt user input
        while True:
            user_input = input("Enter number for this episode: ").strip()
            
            if user_input.isdigit():
                idx = int(user_input) - 1
                if 0 <= idx < len(seasons):
                    # valid number selected
                    chosen_season = seasons[idx]
                    break
                else:
                    print("Invalid number. Try again.")

            else:
                print("Invalid entry. Please try again...")

        print(f"Episode '{title}' assigned to season '{chosen_season.code}'")
        return chosen_season.id

    def save_episodes(self, session, episode_info):
        # save individual episode info to the database
        # check if this episode already exists in the database
        query = session.query(PodcastEpisode)
        query = query.filter_by(guid=episode_info.get("guid"))
        existing_episode = query.first()

        if existing_episode:
            print(f"Episode '{episode_info.get('title')}' already exists in the database.")
            return existing_episode.id

        try:
            print(f"Saving episode '{episode_info.get('title')}' to the database...")
            new_episode = PodcastEpisode(**episode_info)

            # find the podcast info entry id
            query = session.query(RssUrls)
            query = query.filter_by(rss_url=self.url)
            rss_entry = query.first()
            podcast_id = rss_entry.podcast_id

            if podcast_id:
                new_episode.podcast_id = podcast_id
            
            # find the season id
            season_id = self.select_episode_season(session, episode_info, podcast_id)
            new_episode.season_id = season_id

            # update link in the episode info
            url_link = episode_info.get("links", [])[0].get("href", "")
            new_episode.link = url_link

            # ok, now add the episode to the database
            session.add(new_episode)
            session.commit()
            print(f"Episode '{episode_info.get('title')}' saved to the database.")
            return new_episode.id

        except Exception as e:
            session.rollback()
            print(f"Error occurred while saving episode '{episode_info.get('title')}': {e}")
            return None

    def build_episode_paths(self, session, episode_info, episode_id):
        # First, check if a path for this episode already exists
        existing_path = session.query(PodcastPath).filter_by(episode_id=episode_id).first()
        if existing_path:
            # print(f"Path for episode ID {episode_id} already exists.")
            return existing_path.file_path

        # create directory structure for storing podcast files
         # create base directory for podcast files
        CWD = Path.cwd()
        PODCAST_FILES_DIR = CWD / "podcast_files"
        PODCAST_FILES_DIR.mkdir(parents=True, exist_ok=True)

        # get podcast id from RSS URL
        query = session.query(RssUrls)
        query = query.filter_by(rss_url=self.url)
        rss_entry = query.first()
        podcast_id = rss_entry.podcast_id

        if not podcast_id:
            # idk how we got to this point with no podcast id, but just exit
            print("Podcast ID not found. Cannot build episode paths.")
            return

        # create directory for this specific podcast
        cleaned_name = re.sub(r'\W+', '_', self.podcast_info.get('title').lower())

        PODCAST_DIR = PODCAST_FILES_DIR / f"{podcast_id}_{cleaned_name}"
        PODCAST_DIR.mkdir(parents=True, exist_ok=True)

        # create directory for seasons
        season_id = episode_info.get("season_id")
        query = session.query(PodcastSeason)
        query = query.filter_by(id=season_id)
        season_entry = query.first()

        season_name = season_entry.code if season_entry else "unknown_season"
        cleaned_season_name = re.sub(r'\W+', '_', season_name.lower())
        SEASON_DIR = PODCAST_DIR / f"{cleaned_season_name}"
        SEASON_DIR.mkdir(parents=True, exist_ok=True)

        # create directory for this specific episode
        episode_title = episode_info.get("title", "untitled_episode")
        cleaned_episode_title = re.sub(r'\W+', '_', episode_title.lower())
        EPISODE_DIR = SEASON_DIR / f"{episode_id}_{cleaned_episode_title}"
        EPISODE_DIR.mkdir(parents=True, exist_ok=True)

        # create the actual filename for the audio file
        audio_file_name = f"{episode_id}_{cleaned_episode_title}.mp3"
        audio_file_path = EPISODE_DIR / audio_file_name

        # save the episode path in the database
        try:
            print(f"Saving episode path for episode '{episode_title}'...")
            new_path = PodcastPath(
                episode_id=episode_id,
                file_path=str(audio_file_path),
                file_name=str(audio_file_name),
                file_type="audio"  # assuming audio for now
            )
            session.add(new_path)
            session.commit()
            print(f"Episode path for episode '{episode_title}' saved.")
        except Exception as e:
            session.rollback()
            print(f"Error occurred while saving episode path for episode '{episode_title}': {e}")

        return audio_file_path
        
class PodcastDownloader:
    '''
    Docstring for PodcastDownloader
    
    This class handles downloading podcast episodes given their metadata
    and file paths.
    '''
    def get_pending_downloads(self):
        """
        Query the database for all episodes with a 'pending' download status.
        
        Returns:
            A list of PodcastEpisode objects that need to be downloaded.
        """
        session = SessionLocal()
        try:
            target_statuses = ['pending', 'failed']
            query = session.query(PodcastEpisode)
            query = query.options(selectinload(PodcastEpisode.paths)) # Eager load paths
            query = query.filter(PodcastEpisode.download_status.in_(target_statuses))
            pending_episodes = query.all()
            return pending_episodes
        finally:
            session.close()

    def download_episode(self, episode):
        """
        Download a single podcast episode from its link and save it.
        This method is designed to be called in a separate thread.
        """
        # Each thread creates its own session
        session = SessionLocal()
        try:
            # Re-attach the episode object to the new session
            episode = session.merge(episode)
            
            download_url = episode.link
            file_path = Path(episode.paths[0].file_path) # Assuming one path per episode

            if not download_url:
                print(f"Skipping {episode.title} - No download URL found.")
                episode.download_status = 'failed'
                session.commit()
                return

            print(f"Starting download: {episode.title}")
            
            # Ensure the directory exists
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
                    desc=episode.title[:40] # Truncate title for display
                ) as progress_bar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: # filter out keep-alive new chunks
                            size = f.write(chunk)
                            progress_bar.update(size)

            downloaded_size = file_path.stat().st_size
            if total_size != 0 and downloaded_size < total_size:
                print(f"Incomplete download: {episode.title}. Expected {total_size}, got {downloaded_size}")
                episode.download_status = 'failed'
            else:
                episode.download_status = 'downloaded'

            session.commit()
            if episode.download_status == 'downloaded':
                print(f"Finished download: {episode.title}")

        except Exception as e:
            print(f"Error downloading {episode.title}: {e}")
            episode.download_status = 'failed'
            session.commit()
        finally:
            session.close()

    def start_downloads(self):
        """
        Orchestrates the concurrent downloading of pending podcast episodes.
        """
        pending_episodes = self.get_pending_downloads()
        
        if not pending_episodes:
            print("No episodes are pending download.")
        else:
            print(f"Found {len(pending_episodes)} episodes to download.")
            for episode in pending_episodes:
                self.download_episode(episode)

class DeployPodcastProcessing:
    '''
    Docstring for DeployPodcastProcessing
    
    This class is a placeholder for deploying podcast processing jobs.
    '''
    def __init__(self,
                 priority_level='low',
                 fastapi_url="http://192.168.68.66:5000/new-job"
                 ):
        self.priority_level = priority_level
        self.fastapi_url = fastapi_url
        self.mp3s_to_deploy = self.find_mp3s() # list of mp3 files to deploy

        if len(self.mp3s_to_deploy) == 0:
            print("No MP3 files found for deployment.")

        else:
            for episode in self.mp3s_to_deploy:
                self.deploy_mp3(episode)
        
        print('Deployment process complete....')
    
    def find_mp3s(self):
        print("Finding MP3 files to deploy...")
        session = SessionLocal()
        mp3_list = []

        try:
            query = session.query(PodcastEpisode)
            query = query.options(selectinload(PodcastEpisode.paths)) # Eager load paths
            query = query.filter(
                PodcastEpisode.download_status == 'downloaded',
                or_(
                    PodcastEpisode.transcription_status == 'pending',
                    PodcastEpisode.transcription_status == 'failed_deployment'
                    )
                )
            query = query.order_by(PodcastEpisode.id.asc())

            mp3_list = query.all()
            print(f"Found {len(mp3_list)} MP3 files to deploy.")
            input('Press Enter to continue...')
        
        finally:
            session.close()
        
        return mp3_list

    def deploy_mp3(self, episode):
        print(f'Deploying processing job for episode: {episode.title}...')

        if not episode.paths:
            print(f"No file path found for episode: {episode.title}. Skipping deployment.")
            return

        file_path = Path(episode.paths[0].file_path)
        file_name = episode.paths[0].file_name

        if not file_path.exists():
            print(f"File not found at {file_path} for episode: {episode.title}. Skipping deployment.")
            # TODO : update episode status to indicate missing file
            return

        try:
            with open(file_path, 'rb') as f:
                #  build the multipart form data
                # first the mp3 file
                files = {
                    'file': (file_name, f, 'audio/mpeg')
                }

                # then the json data
                data = {
                    'priority_level': self.priority_level,
                    'filename': file_name
                }

                # send it
                response = requests.post(
                    self.fastapi_url,
                    files=files,
                    data=data
                )
                response.raise_for_status()
                
                print(f"Successfully deployed {file_name}.")
                
                response_data = response.json()
                job_ulid = response_data.get("job_ulid")
                job_status_from_server = response_data.get("status") # This should be 'deployed' or similar

                # update the database
                session = SessionLocal()
                try:
                    episode = session.merge(episode)
                    episode.transcription_status = 'deployed' # Update episode status

                    # Create a new JobDeployment entry
                    new_job_deployment = JobDeployment(
                        epidode_id=episode.id,
                        ulid=job_ulid,
                        job_status=job_status_from_server
                    )
                    session.add(new_job_deployment)
                    session.commit()

                    print(f"JobDeployment for episode {episode.title} (ULID: {job_ulid}) created successfully.")
                except Exception as e:
                    session.rollback()
                    print(f"Error updating transcription status or creating JobDeployment for {episode.title}: {e}")
                finally:
                    session.close()

        except requests.exceptions.RequestException as e:
            print(f"Network or server error while deploying {file_name}: {e}")
            session = SessionLocal()
            try:
                episode = session.merge(episode)
                episode.transcription_status = 'failed_deployment'
                session.commit()
            except Exception as update_e:
                session.rollback()
                print(f"Error updating transcription status after deployment failure for {episode.title}: {update_e}")
            finally:
                session.close()
        except IOError as e:
            print(f"File system error reading {file_name}: {e}")
            session = SessionLocal()
            try:
                episode = session.merge(episode)
                episode.transcription_status = 'failed_deployment'
                session.commit()
            except Exception as update_e:
                session.rollback()
                print(f"Error updating transcription status after file system error for {episode.title}: {update_e}")
            finally:
                session.close()
        except Exception as e:
            print(f"An unexpected error occurred during deployment of {file_name}: {e}")
            session = SessionLocal()
            try:
                episode = session.merge(episode)
                episode.transcription_status = 'failed_deployment'
                session.commit()
            except Exception as update_e:
                session.rollback()
                print(f"Error updating transcription status after unexpected error for {episode.title}: {update_e}")
            finally:
                session.close()

if __name__ == "__main__":
    url = "https://feeds.buzzsprout.com/2544823.rss"

    options = {
        '1': 'Start podcast collection flow',
        '2': 'Download Podcast episodes',
        '3': 'Deploy podcast processing jobs',
        'q': 'Quit'
    }

    while True:
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
            # Instantiate and run the deployment process
            deployer = DeployPodcastProcessing()
        
        elif choice.lower() == 'q':
            print("Exiting the program.")
            exit(0)