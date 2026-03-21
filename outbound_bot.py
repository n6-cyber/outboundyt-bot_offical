# Imports below
import discord
from discord.ext import commands, tasks
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import json
import logging
import datetime

# Logging protocol below!

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)

# Global Variables

last_vid = None 

# Loading the .env file below!
load_dotenv()
YT_KEY = os.getenv("YT_KEY")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
YT_CHANNEL_ID = os.getenv("YT_CHANNEL_ID")
TOKEN = os.getenv("DISCORD_TOKEN")

# .env validation!

if not YT_KEY or not TOKEN or not YT_CHANNEL_ID:
    logger.error("Missing required .env variables! Check your .env file!")
    exit(1)

# Intent Definitions below!

intent = discord.Intents.default()
intent.message_content = True

# Initializing YT API below!

youtube = build("youtube", "v3", developerKey=YT_KEY)

# Initializing Discord Bot below!

bot = commands.Bot(command_prefix="!", intents=intent)

# Loop checks for latest vid!

def save_last_vid(vid):
    try:
        with open("vid_state.json", "w") as f:
            json.dump(vid, f)
    except Exception as e:
        logger.error(f"Save failed: {e}")

def load_last_vid():
    global last_vid
    try:
        with open("vid_state.json", "r") as f:
            last_vid = json.load(f)
            logger.info(f"Loaded last vid: {last_vid}")
    except Exception as e:
        last_vid = None
        logger.error(f"Load failed: {e}")

# check_once function helper below!

async def check_once():
    global last_vid
    try:
        request = youtube.search().list(
            channelId=YT_CHANNEL_ID,
            part="snippet,id",
            order="date",
            maxResults=1,
            type="video"
        )
        response = request.execute()
        if not response["items"]:
            return 
        latest = response["items"][0]
        video_id = latest["id"]["videoId"]
        title = latest["snippet"]["title"]
        if video_id == last_vid:
            logger.info("No new video found")
            return
        last_vid = video_id
        save_last_vid(last_vid)
        channel = bot.get_channel(CHANNEL_ID)
        if channel is None:
            logger.error(f"Channel {CHANNEL_ID} not found!")
            return
        await channel.send(f"🎬 New video from Outbound Kid!\n**{title}**\nhttps://youtube.com/watch?v={video_id}")
    except Exception as e: 
        logger.error(f"No new video/error has occured: {e}")

@tasks.loop(minutes=30)
async def check_new_vid():
    await check_once()

# Before Loop function

@check_new_vid.before_loop
async def before_check():
    await bot.wait_until_ready()

# Below is the On Ready function!

@bot.event # listen for the event below!
async def on_ready():
    logger.info(f"Logged in as {bot.user.name}")
    try:
        load_last_vid()
        check_new_vid.start()
        logger.info(f"Video check started sucessfully!")
    except Exception as e:
        logger.error(f"Failed to start: {e}")

# Bot Commands below, perms and more

@bot.command()
@commands.has_permissions(administrator=True)
async def stop(ctx):
    await ctx.send("🔴 Bot stopping now...")
    await bot.close()

@bot.command()
@commands.has_permissions(administrator=True)
async def check(ctx):
    await ctx.send("🔍 Checking now...")
    await check_once()

@bot.command()
@commands.has_permissions(administrator=True)
async def status(ctx):
    next_check = check_new_vid.next_iteration
    now = datetime.datetime.now(datetime.timezone.utc)
    diff = next_check - now
    minutes = int(diff.total_seconds() // 60)
    seconds = int(diff.total_seconds() % 60)
    await ctx.send(
        f"✅ **Bot Status**\n"
        f"📺 Last video: `{last_vid}`\n"
        f"⏰ Next check in: `{minutes}m {seconds}s`"
    )

@bot.command()
async def help_bot(ctx):
    await ctx.send("**Commands:**\n`!check` - Check for new videos now\n`!status` - Bot status\n`!stop` - Stop the bot (admin only)")

bot.run(TOKEN)