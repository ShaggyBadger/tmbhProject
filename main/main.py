import feedparser
import re
from db import SessionLocal
from models import PodcastInfo, PodcastSeason, PodcastEpisode, RssUrls, PodcastPath

class PodcastCollection:
    def __init__(self, url="https://feeds.buzzsprout.com/2544823.rss"):
        self.url = url
        self.parsed = feedparser.parse(url) # Parsed feed
        self.feed = self.parsed.feed # FeedParserDict with general podcast info
        self.podcast_entries = self.parsed.entries # List of podcast episodes (FeedParserDicts)
    
    def standard_flow(self):
        # run this method to extract and store podcast info from the feed
        print("Starting standard podcast collection flow...")
        print("Extracting podcast info...")
        self.extract_podcast_info()
        print('Extraction complete.\n\n')
        print("Saving RSS URL...")
        self.save_rss_url()
        print('RSS URL saved.\n\n')
        
    def extract_podcast_info(self):
        feed = self.feed
        podcast_info = {
            "title": feed.get("title", ""),
            "subtitle": feed.get("subtitle", ""),
            "subtitle_detail": str(feed.get("subtitle_detail", "")),
            "authors": str(feed.get("authors", "")),
            "author": feed.get("author", ""),
            "author_detail": str(feed.get("author_detail", "")),
            "link": feed.get("link", ""),
            "language": feed.get("language", ""),
            "itunes_type": feed.get("itunes_type", ""),
            "itunes_explicit": feed.get("itunes_explicit", ""),
            "image": str(feed.get("image", "")),
        }

        # check if this podcast info is already in the database
        session = SessionLocal()

        # Perform a query to check for existing podcast by URL
        print('Checking for existing podcast info in the database...')
        query = session.query(PodcastInfo)
        query = query.filter_by(title=podcast_info.get("title"))
        existing_podcast = query.first()

        try:
            if existing_podcast:
                print('Podcast info already exists in the database.')
                pass
            else:
                print('Adding new podcast info to the database...')
                new_podcast = PodcastInfo(**podcast_info)
                session.add(new_podcast)
                session.commit()
                print('Podcast info added to the database.')
        except Exception as e:
            session.rollback()
            print(f"Error occurred while adding podcast info: {e}")
        finally:
            session.close()
        
    def save_rss_url(self):
        # ensure the RSS feed URL is saved to the database
        session = SessionLocal()
        url = self.url

        # find the podcast info entry id
        query = session.query(PodcastInfo)
        query = query.filter_by(title=self.feed.title)
        podcast_info = query.first()

        if not podcast_info:
            # the parent podcast info must be saved first
            print("Podcast info not found in the database. Cannot save RSS URL.")
            session.close()
            return

        # check if the RSS URL already exists for this podcast
        query = session.query(RssUrls)
        query = query.filter_by(rss_url=url, podcast_id=podcast_info.id)
        existing_rss = query.first()

        if existing_rss:
            # the RSS URL is already saved
            print("RSS URL already exists in the database.")
            session.close()
            return
        
        try:
            # save the RSS URL
            print("Saving RSS URL to the database...")
            new_rss = RssUrls(rss_url=url, podcast_id=podcast_info.id)
            session.add(new_rss)
            session.commit()
            print("RSS URL saved to the database.")
        except Exception as e:
            # rollback in case of error
            session.rollback()
            print(f"Error occurred while saving RSS URL: {e}")
        finally:
            session.close()

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



if __name__ == "__main__":
    url = "https://feeds.buzzsprout.com/2544823.rss"
    collector = PodcastCollection(url)
    collector.standard_flow()