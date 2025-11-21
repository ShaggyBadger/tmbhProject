import feedparser
import re




url = "https://feeds.buzzsprout.com/2544823.rss"
feed = feedparser.parse(url)

odbballs = []
season_names = []

entries = feed.entries
for entry in entries:
    title = entry.title
    match = re.match(r"([A-Z]+)\d+", title)


    if match:
        code = match.group(1)
        if code not in season_names:
            season_names.append(code)
    else:
        odbballs.append(title)

for i in season_names:
    print(i)

input('press  enter to continue...')
for i in odbballs:
    print(i)