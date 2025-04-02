import praw
import requests
import schedule
import time
import os
import json
import argparse
import re
from datetime import datetime, timedelta, timezone
import ffmpeg
import xml.etree.ElementTree as ET

# Parse command-line arguments for bot configuration
parser = argparse.ArgumentParser(description="Reddit to Facebook Bot")
parser.add_argument("--no-videos", action="store_true", help="Disable video posting")
parser.add_argument("--no-images", action="store_true", help="Disable image posting (including galleries)")
parser.add_argument("--no-greeting", action="store_true", help="Disable the initial greeting message")
parser.add_argument("--no-debug", action="store_true", help="Disable debug logging")
parser.add_argument("--no-downloading", action="store_true", help="Disable downloading new media; only post existing files from media folder")
parser.add_argument("--no-hashtags", action="store_true", help="Disable adding hashtags to posts")
parser.add_argument("--no-subreddits", action="store_true", help="Disable pulling posts from predefined subreddits list")
parser.add_argument("--no-homepage", action="store_true", help="Disable pulling posts from Reddit homepage")
parser.add_argument("--no-joining", action="store_true", help="Disable auto-joining anime-related subreddits from homepage")
parser.add_argument("--nsfw", action="store_true", help="Enable NSFW posts (off by default)")
args = parser.parse_args()

# Reddit setup with your credentials
reddit = praw.Reddit(
    client_id="83LypQ5gk0QBMW2TC6nDWw",
    client_secret="zWUo7zy_rp79dI3119iCVwxpDksUew",
    user_agent="FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)",
    username="Deablo_Demon_Lord",
    password="rNUELkUnb@EQ.i6"
)

# Test Reddit API connection to ensure credentials are valid
try:
    subreddit = reddit.subreddit("anime")
    for submission in subreddit.hot(limit=1):
        print(f"Successfully fetched post: {submission.title}")
    print("Reddit API connection is working!")
except Exception as e:
    print(f"Reddit API connection failed: {str(e)}")
    exit(1)

# Facebook setup with your Page ID and Access Token
PAGE_ACCESS_TOKEN = "EAANavxtZAHIoBO0NnNOQl8LTiG9gwjPsft1ESHEMmA07flehz7ZAcy8U8BXSQLpyKT9k9psQ34KAS7D7ng62cOL9p31hPEZBoNXZAdmtZA4PepESfkaJOFaKJQqMoc0J1ZC4CzKotvL5C2JFrDaeTc03mZAZAiDezX1AvLliZBg27jh8EQACHE3O9fNUeVT1ZBhICZCbrjC6L7QX85q4TV0"
PAGE_ID = "563175166885757"

# Directory to save downloaded media
MEDIA_DIR = "media"
if not os.path.exists(MEDIA_DIR):
    os.makedirs(MEDIA_DIR)

# File to store posted Reddit post IDs
POSTED_IDS_FILE = "posted_ids.json"

# File to store joined subreddits
JOINED_SUBREDDITS_FILE = "subreddits-joined.txt"

# Maximum file size allowed (100MB in bytes)
MAX_FILE_SIZE = 100 * 1024 * 1024

# Counter and limits for posts in a batch
POSTS_PER_BATCH = 25
COOLDOWN_SECONDS = 900
DELAY_BETWEEN_POSTS = 30
posts_in_batch = 0
download_failures = 0
MAX_FAILURES_BEFORE_NOTIFICATION = 5

# List of subreddits to fetch posts from (if not disabled)
SUBREDDITS = [
    "anime", "anime_irl", "bleach", "haikyuu", "Gintama", "animeskirts", "SSSSGRIDMAN",
    "KaijuNo8", "StardustCrusaders", "NeonGenesisEvangelion", "sololeveling", "yugioh",
    "SaintSeiya", "Komi_san", "Naruto", "Hololive", "manga", "JuJutsuKaisen", "HISHAMtalksANIME",
    "MyAnimeList", "Lumine_Mains", "KimetsuNoYaiba", "evangelion", "LoveLive", "Horikitafanclub",
    "animecuddling", "ShingekiNoKyojin", "vagabondmanga", "Joshi_Kosei", "bokunokokoro",
    "ShikimoriIsntJustCute", "jigokuraku", "winterwaifus", "NilouMains", "Anime_Romance",
    "Genshin_Wallpaper", "Dhaka", "Moescape", "KaMikoto", "SpyXFamily", "AnimeBurgers",
    "DungeonMeshi", "Animesuggest", "Animemes", "overlord", "EightySix", "SoloLevelingMemes",
    "Frieren", "LightNovels", "attackontitan", "CultofYamai", "Re_Zero", "CodeGeass",
    "OtonariNoTenshiSama", "sixfacedworld", "AquaSama", "VinlandSaga", "OshiNoKoMemes",
    "TenseiSlime", "Tomozaki_kun", "toarumajutsunoindex", "Rakudai", "BlueBox", "Berserk"
]

# Hashtags to append to every post (unless --no-hashtags is used)
HASHTAGS = " #anime #animes #animelover #animefan #animeart #animegirls #animeindonesia #animeedits #animelove #animememes #animegirl #animefanart #animeworld #animesbrasil #animescene #animeloversfollowme #animejapan #animeedit #animegirlkawaii #animegirlsdaily #Anime2025 #newanime"

# Keywords to identify anime-related subreddits
ANIME_KEYWORDS = ["anime", "manga", "kawaii", "otaku", "waifu", "senpai", "shonen", "shoujo", "mecha", "isekai"]

# Sanitize filename for local saving
def sanitize_filename(title, max_length=100):
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    sanitized = sanitized.replace(" ", "_")
    return sanitized[:max_length]

# Generate a time-based greeting message
def get_time_based_greeting():
    current_hour = datetime.now(timezone.utc).hour
    if 5 <= current_hour < 12:
        return "Good morning"
    elif 12 <= current_hour < 17:
        return "Good afternoon"
    else:
        return "Good evening"

# Post a text message to Facebook
def post_text_to_facebook(message):
    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/feed"
    payload = {"message": message, "access_token": PAGE_ACCESS_TOKEN}
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("Text message posted successfully!")
    else:
        print(f"Error posting text message: {response.text}")

# Post an image to Facebook
def post_image_to_facebook(caption, image_path):
    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/photos"
    full_path = os.path.join(MEDIA_DIR, image_path)
    files = {"source": open(full_path, "rb")}
    caption_with_hashtags = caption if args.no_hashtags else f"{caption}{HASHTAGS}"
    payload = {"message": caption_with_hashtags, "access_token": PAGE_ACCESS_TOKEN}
    response = requests.post(url, files=files, data=payload)
    files["source"].close()
    if response.status_code == 200:
        print(f"Image posted successfully from {full_path}!")
        return True
    else:
        print(f"Error posting image: {response.text}")
        return False

# Post multiple images to Facebook
def post_multiple_images_to_facebook(caption, image_paths):
    photo_ids = []
    for image_path in image_paths:
        url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/photos"
        full_path = os.path.join(MEDIA_DIR, image_path)
        files = {"source": open(full_path, "rb")}
        payload = {"published": "false", "access_token": PAGE_ACCESS_TOKEN}
        response = requests.post(url, files=files, data=payload)
        files["source"].close()
        if response.status_code == 200:
            photo_id = response.json().get("id")
            photo_ids.append(photo_id)
            print(f"Uploaded image {image_path} with ID {photo_id}")
        else:
            print(f"Error uploading image {image_path}: {response.text}")
            return False

    url = f"https://graph.facebook.com/v22.0/{PAGE_ID}/feed"
    caption_with_hashtags = caption if args.no_hashtags else f"{caption}{HASHTAGS}"
    payload = {"message": caption_with_hashtags, "access_token": PAGE_ACCESS_TOKEN}
    for i, photo_id in enumerate(photo_ids):
        payload[f"attached_media[{i}]"] = f'{{"media_fbid":"{photo_id}"}}'
    response = requests.post(url, data=payload)
    if response.status_code == 200:
        print("Multiple images posted successfully!")
        return True
    else:
        print(f"Error posting multiple images: {response.text}")
        return False

# Post a video to Facebook
def post_video_to_facebook(caption, video_path):
    url = f"https://graph-video.facebook.com/v22.0/{PAGE_ID}/videos"
    full_path = os.path.join(MEDIA_DIR, video_path)
    files = {"source": open(full_path, "rb")}
    caption_with_hashtags = caption if args.no_hashtags else f"{caption}{HASHTAGS}"
    payload = {"description": caption_with_hashtags, "access_token": PAGE_ACCESS_TOKEN}
    response = requests.post(url, files=files, data=payload)
    files["source"].close()
    if response.status_code == 200:
        print(f"Video posted successfully from {full_path}!")
        return True
    else:
        print(f"Error posting video: {response.text}")
        return False

# Load previously posted IDs from file
def load_posted_ids():
    if os.path.exists(POSTED_IDS_FILE):
        with open(POSTED_IDS_FILE, "r") as f:
            return set(json.load(f))
    return set()

# Save a new posted ID to file
def save_posted_id(post_id):
    posted_ids = load_posted_ids()
    posted_ids.add(post_id)
    with open(POSTED_IDS_FILE, "w") as f:
        json.dump(list(posted_ids), f)

# Load previously joined subreddits from file
def load_joined_subreddits():
    if os.path.exists(JOINED_SUBREDDITS_FILE):
        with open(JOINED_SUBREDDITS_FILE, "r") as f:
            return set(f.read().splitlines())
    return set()

# Save a newly joined subreddit to file
def save_joined_subreddit(subreddit_name):
    joined_subreddits = load_joined_subreddits()
    joined_subreddits.add(subreddit_name)
    with open(JOINED_SUBREDDITS_FILE, "w") as f:
        f.write("\n".join(sorted(joined_subreddits)))
    print(f"Joined and logged subreddit: {subreddit_name}")

# Check if a subreddit is anime-related
def is_anime_related(subreddit_name):
    name_lower = subreddit_name.lower()
    return any(keyword in name_lower for keyword in ANIME_KEYWORDS)

# Check file size to ensure it’s within limits
def check_file_size(url):
    try:
        headers = {"User-Agent": "FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)"}
        response = requests.head(url, headers=headers, allow_redirects=True)
        size = int(response.headers.get("content-length", 0))
        print(f"File size for {url}: {size} bytes")
        return size <= MAX_FILE_SIZE
    except Exception as e:
        print(f"Error checking file size for {url}: {str(e)}")
        return False

# Download media with retry logic
def download_media(url, filename, max_retries=3, initial_delay=5):
    full_path = os.path.join(MEDIA_DIR, filename)
    for attempt in range(max_retries):
        try:
            headers = {"User-Agent": "FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)"}
            response = requests.get(url, headers=headers, stream=True)
            response.raise_for_status()
            with open(full_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            print(f"Successfully downloaded {url} to {full_path}")
            return True
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                delay = initial_delay * (2 ** attempt)
                print(f"Rate limit hit for {url}. Retrying in {delay} seconds... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(delay)
            else:
                print(f"Download failed for {url}: {str(e)}")
                return False
        except Exception as e:
            print(f"Download failed for {url}: {str(e)}")
            return False
    print(f"Failed to download {url} after {max_retries} attempts due to rate limiting.")
    return False

# Extract audio URL from DASH manifest for video posts
def get_audio_url_from_dash(dash_url):
    try:
        headers = {"User-Agent": "FBRedditBot/1.0 (by /u/Deablo_Demon_Lord)"}
        response = requests.get(dash_url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch DASH manifest: {dash_url}")
            return None
        root = ET.fromstring(response.content)
        namespaces = {"ns": "urn:mpeg:dash:schema:mpd:2011"}
        for adaptation_set in root.findall(".//ns:AdaptationSet", namespaces):
            if adaptation_set.get("contentType") == "audio":
                base_url = adaptation_set.find(".//ns:BaseURL", namespaces)
                if base_url is not None:
                    audio_url = base_url.text
                    if not audio_url.startswith("http"):
                        base_path = dash_url.rsplit("/", 1)[0]
                        audio_url = f"{base_path}/{audio_url}"
                    return audio_url
        print(f"No audio stream found in DASH manifest: {dash_url}")
        return None
    except Exception as e:
        print(f"Error parsing DASH manifest {dash_url}: {str(e)}")
        return None

# Merge video and audio streams into a single file
def merge_video_audio(video_url, audio_url, output_filename):
    try:
        video_file = os.path.join(MEDIA_DIR, "temp_video.mp4")
        audio_file = os.path.join(MEDIA_DIR, "temp_audio.mp4")
        output_path = os.path.join(MEDIA_DIR, output_filename)
        if not download_media(video_url, "temp_video.mp4"):
            print(f"Failed to download video: {video_url}")
            return None
        if not download_media(audio_url, "temp_audio.mp4"):
            print(f"Failed to download audio: {audio_url}")
            return None
        video_stream = ffmpeg.input(video_file)
        audio_stream = ffmpeg.input(audio_file)
        output = ffmpeg.output(video_stream, audio_stream, output_path, vcodec="copy", acodec="aac", strict="experimental")
        ffmpeg.run(output)
        if os.path.exists(video_file):
            os.remove(video_file)
        if os.path.exists(audio_file):
            os.remove(audio_file)
        return output_filename
    except Exception as e:
        print(f"Error merging video and audio: {str(e)}")
        return None

# Countdown timer for delays between posts
def countdown(seconds):
    for i in range(seconds, 0, -1):
        print(f"Waiting {i} seconds...", end="\r")
        time.sleep(1)
    print(" " * 50, end="\r")

# Main job to fetch and post media from Reddit
def job():
    global posts_in_batch, download_failures
    posted_ids = load_posted_ids()
    joined_subreddits = load_joined_subreddits()
    twelve_hours_ago = datetime.now(timezone.utc) - timedelta(hours=12)
    twelve_hours_ago_timestamp = int(twelve_hours_ago.timestamp())

    # Determine sources based on command-line arguments
    sources = []
    if not args.no_subreddits:
        subreddit_string = "+".join(SUBREDDITS)
        sources.append(("subreddits", reddit.subreddit(subreddit_string)))
    if not args.no_homepage:
        sources.append(("homepage", reddit.front))

    if not sources:
        print("No sources enabled (--no-subreddits and --no-homepage both set). Skipping job.")
        return

    if not args.no_debug:
        print(f"Current UTC time: {datetime.now(timezone.utc)}")
        print(f"12 hours ago (UTC): {twelve_hours_ago}")
        print(f"Fetching posts from: {', '.join(source[0] for source in sources)}...")

    eligible_posts_found = 0
    try:
        for source_name, source in sources:
            if not args.no_debug:
                print(f"Processing {source_name}...")
            submissions = source.new(limit=200) if source_name == "subreddits" else source.new(limit=200)
            for submission in submissions:
                if not args.no_debug:
                    print(f"Checking post {submission.id}: {submission.title}")
                    print(f"Post creation time (UTC): {datetime.fromtimestamp(submission.created_utc, tz=timezone.utc)}")
                if submission.id in posted_ids:
                    if not args.no_debug:
                        print(f"Post {submission.id} already posted, skipping")
                    continue
                if submission.created_utc < twelve_hours_ago_timestamp:
                    if not args.no_debug:
                        print(f"Post {submission.id} is older than 12 hours, skipping")
                    continue
                if submission.over_18 and not args.nsfw:  # Skip NSFW unless --nsfw is set
                    if not args.no_debug:
                        print(f"Post {submission.id} is marked NSFW, skipping")
                    continue

                # Auto-join anime-related subreddits from homepage (unless disabled)
                if source_name == "homepage" and not args.no_homepage and not args.no_joining:
                    subreddit_name = submission.subreddit.display_name
                    if is_anime_related(subreddit_name) and subreddit_name not in joined_subreddits and subreddit_name not in SUBREDDITS:
                        try:
                            reddit.subreddit(subreddit_name).subscribe()
                            save_joined_subreddit(subreddit_name)
                            joined_subreddits.add(subreddit_name)
                        except Exception as e:
                            print(f"Failed to join subreddit {subreddit_name}: {str(e)}")

                media_url = None
                is_video = False
                audio_url = None
                if not args.no_images and submission.url.endswith((".jpg", ".jpeg", ".png", ".gif")):
                    media_url = submission.url
                elif not args.no_videos and hasattr(submission, "media") and submission.media:
                    if "reddit_video" in submission.media:
                        media_url = submission.media["reddit_video"]["fallback_url"]
                        is_video = True
                        if "dash_url" in submission.media["reddit_video"]:
                            audio_url = get_audio_url_from_dash(submission.media["reddit_video"]["dash_url"])

                if not media_url:
                    if not args.no_debug:
                        print(f"Post {submission.id} has no media, skipping")
                    continue
                if not args.no_downloading and not check_file_size(media_url):
                    if not args.no_debug:
                        print(f"Media too large for post {submission.id}: {submission.url}")
                    continue

                eligible_posts_found += 1
                if not args.no_debug:
                    print(f"Eligible post found: {submission.id} (Total eligible: {eligible_posts_found})")

                success = False
                base_filename = sanitize_filename(submission.title)

                if is_video and not args.no_videos:
                    video_filename = f"{base_filename}.mp4"
                    video_path = os.path.join(MEDIA_DIR, video_filename)
                    if args.no_downloading:
                        if os.path.exists(video_path):
                            success = post_video_to_facebook(submission.title, video_filename)
                        else:
                            if not args.no_debug:
                                print(f"Video file {video_filename} not found in media folder, skipping")
                            continue
                    else:
                        if audio_url and check_file_size(audio_url):
                            merged_file = merge_video_audio(media_url, audio_url, video_filename)
                            if merged_file:
                                success = post_video_to_facebook(submission.title, merged_file)
                            else:
                                print(f"Failed to merge audio for video post {submission.id}, posting without audio")
                                if download_media(media_url, video_filename):
                                    success = post_video_to_facebook(submission.title, video_filename)
                                else:
                                    download_failures += 1
                        else:
                            print(f"No audio available for video post {submission.id}, posting without audio")
                            if download_media(media_url, video_filename):
                                success = post_video_to_facebook(submission.title, video_filename)
                            else:
                                download_failures += 1
                elif not args.no_images and hasattr(submission, "is_gallery") and submission.is_gallery:
                    image_paths = []
                    try:
                        for i, item in enumerate(submission.gallery_data["items"][:10]):
                            media_id = item["media_id"]
                            media_url = submission.media_metadata[media_id]["s"]["u"]
                            if args.no_downloading or check_file_size(media_url):
                                image_filename = f"{base_filename}_gallery_{i}.jpg"
                                image_path = os.path.join(MEDIA_DIR, image_filename)
                                if args.no_downloading:
                                    if os.path.exists(image_path):
                                        image_paths.append(image_filename)
                                    else:
                                        if not args.no_debug:
                                            print(f"Gallery image {image_filename} not found in media folder, skipping")
                                else:
                                    if download_media(media_url, image_filename):
                                        image_paths.append(image_filename)
                                    else:
                                        download_failures += 1
                        if image_paths:
                            success = post_multiple_images_to_facebook(submission.title, image_paths)
                    except Exception as e:
                        print(f"Error processing gallery post {submission.id}: {str(e)}")
                elif not args.no_images:
                    image_filename = f"{base_filename}.jpg"
                    image_path = os.path.join(MEDIA_DIR, image_filename)
                    if args.no_downloading:
                        if os.path.exists(image_path):
                            success = post_image_to_facebook(submission.title, image_filename)
                        else:
                            if not args.no_debug:
                                print(f"Image file {image_filename} not found in media folder, skipping")
                            continue
                    else:
                        if download_media(media_url, image_filename):
                            success = post_image_to_facebook(submission.title, image_filename)
                        else:
                            download_failures += 1

                if not args.no_downloading and download_failures >= MAX_FAILURES_BEFORE_NOTIFICATION:
                    post_text_to_facebook("Warning: Bot is encountering repeated download failures due to rate limiting. Please check the logs.")
                    download_failures = 0

                if success:
                    save_posted_id(submission.id)
                    posts_in_batch += 1
                    print(f"Posted {posts_in_batch}/{POSTS_PER_BATCH} posts in this batch")
                    countdown(DELAY_BETWEEN_POSTS)
                    if posts_in_batch >= POSTS_PER_BATCH:
                        print(f"Reached {POSTS_PER_BATCH} posts. Cooling down for {COOLDOWN_SECONDS} seconds...")
                        time.sleep(COOLDOWN_SECONDS)
                        posts_in_batch = 0
                        print("Cooldown finished. Resuming posting...")
                else:
                    print(f"Failed to post {submission.id}, continuing to next post")

        if not args.no_debug:
            print(f"Finished processing posts. Eligible posts found: {eligible_posts_found}")
            if eligible_posts_found == 0:
                print("No eligible posts found in this batch. Waiting for next scheduled run...")
    except Exception as e:
        print(f"Error fetching Reddit posts: {str(e)}")

# Initial setup and startup message
print("The bot has started")
if not args.no_greeting:
    greeting = get_time_based_greeting()
    post_text_to_facebook(f"{greeting}, the bot has started!")

# Run the job immediately and schedule it to run every minute
job()
schedule.every(1).minutes.do(job)

# Keep the bot running indefinitely
while True:
    schedule.run_pending()
    time.sleep(60)