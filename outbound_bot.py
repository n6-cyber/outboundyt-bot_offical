import discord
from discord.ext import commands, tasks
from googleapiclient.discovery import build
from dotenv import load_dotenv
import os
import json
import logging
import time

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
load_dotenv()
YT_KEY = os.getenv("YT_KEY")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
YT_CHANNEL_ID = os.getenv("YT_CHANNEL_ID")
TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
TRUSTED_ID = int(os.getenv("COOWNER_ID"))
MEMBER_ROLE_ID = int(os.getenv("MEMBER_ROLE_ID"))

if not all([YT_KEY, TOKEN, YT_CHANNEL_ID, CHANNEL_ID, OWNER_ID, TRUSTED_ID, MEMBER_ROLE_ID]):
    logger.error("Missing required .env variables! Check your .env file!")
    exit(1)

# --- Global Variables & State ---
start_time = int(time.time())
DATA_FILE = "bot_data.json"

bot_data = {
    "last_vid": None,
    "sub_goal": None,
    "goal_notified": False,
    "current_subs": None
}

# --- Initialization ---
intent = discord.Intents.default()
intent.message_content = True
bot = commands.Bot(command_prefix="!", intents=intent)
youtube = build("youtube", "v3", developerKey=YT_KEY)

# --- Privilege Check ---
def is_privileged(ctx):
    return ctx.author.id in [OWNER_ID, TRUSTED_ID]

# --- Save/Load Functions ---
def bot_save():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(bot_data, f, indent=4)
        logger.info("Bot data saved.")
    except Exception as e:
        logger.error(f"Save failed: {e}")

def bot_load():
    global bot_data
    if not os.path.exists(DATA_FILE):
        logger.info("No data file found. Creating new one...")
        bot_save()
        return
    try:
        with open(DATA_FILE, "r") as f:
            loaded_data = json.load(f)
            bot_data.update(loaded_data)
            logger.info("Bot data loaded successfully.")
    except Exception as e:
        logger.error(f"Load failed: {e}")

# --- YouTube API Functions ---
def get_sub_count():
    try:
        request = youtube.channels().list(
            part="statistics",
            id=YT_CHANNEL_ID
        )
        response = request.execute()
        return int(response["items"][0]["statistics"]["subscriberCount"])
    except Exception as e:
        logger.error(f"Failed to fetch sub count: {e}")
        return None

async def check_once():
    try:
        # 1. Check for new video
        vid_request = youtube.search().list(
            channelId=YT_CHANNEL_ID,
            part="snippet,id",
            order="date",
            maxResults=1,
            type="video"
        )
        vid_response = vid_request.execute()

        if vid_response.get("items"):
            latest = vid_response["items"][0]
            video_id = latest["id"]["videoId"]
            title = latest["snippet"]["title"]

            if video_id != bot_data["last_vid"]:
                bot_data["last_vid"] = video_id
                try:
                    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
                except Exception as e:
                    logger.error(f"Channel not found: {e}")
                    return
                if channel:
                    await channel.send(
                        f"<@&{MEMBER_ROLE_ID}> 🎬 **New video from Outbound Kid!**\n"
                        f"**{title}**\n"
                        f"https://youtube.com/watch?v={video_id}"
                    )
            else:
                logger.info("No new video found")

        # 2. Fetch and cache sub count
        current_subs = get_sub_count()
        if current_subs:
            bot_data["current_subs"] = current_subs
            logger.info(f"Cached sub count: {current_subs:,}")

        # 3. Check sub goal
        if bot_data["sub_goal"] is not None and not bot_data["goal_notified"]:
            if current_subs and current_subs >= bot_data["sub_goal"]:
                bot_data["goal_notified"] = True
                try:
                    channel = bot.get_channel(CHANNEL_ID) or await bot.fetch_channel(CHANNEL_ID)
                except Exception as e:
                    logger.error(f"Channel not found: {e}")
                    return
                if channel:
                    await channel.send(
                        f"<@&{MEMBER_ROLE_ID}> 🎉 **WE DID IT!** Outbound Kid just hit..."
                    )
         # Save everything at once
        bot_save()

    except Exception as e:
        logger.error(f"Error in check_once: {e}")

@tasks.loop(minutes=30)
async def check_new_vid():
    await check_once()

@check_new_vid.before_loop
async def before_check():
    await bot.wait_until_ready()

# --- Bot Events ---
@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name}")
    bot_load()
    if not check_new_vid.is_running():
        check_new_vid.start()
        logger.info("Background checks started!")

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("❌ You don't have permission! (Owner/Trusted only)")
    else:
        logger.error(f"Command error: {error}")

# --- Bot Commands ---
@bot.command()
@commands.check(is_privileged)
async def stop(ctx):
    await ctx.send("🔴 Bot stopping now...")
    await bot.close()

@bot.command()
@commands.check(is_privileged)
async def check(ctx):
    await ctx.send("🔍 Forcing YouTube check now...")
    await check_once()

@bot.command()
@commands.check(is_privileged)
async def set_sub_goal(ctx, goal: int):
    bot_data["sub_goal"] = goal
    bot_data["goal_notified"] = False
    bot_save()
    await ctx.send(f"✅ Sub goal set to **{goal:,}** subscribers!")

@bot.command()
@commands.check(is_privileged)
async def remove_sub_goal(ctx):
    bot_data["sub_goal"] = None
    bot_data["goal_notified"] = False
    bot_save()
    await ctx.send("🗑️ Sub goal removed.")

@bot.command()
async def sub_info(ctx):
    if bot_data["sub_goal"] is None:
        await ctx.send("ℹ️ No active subscriber goal set right now.")
        return

    current_subs = bot_data.get("current_subs")
    if not current_subs:
        await ctx.send("❌ No sub data yet, wait for the next check in 30 minutes!")
        return

    goal = bot_data["sub_goal"]
    percent = min((current_subs / goal) * 100, 100)
    filled_blocks = int(percent / 10)
    empty_blocks = 10 - filled_blocks
    progress_bar = ("█" * filled_blocks) + ("░" * empty_blocks)

    embed = discord.Embed(title="🎯 Outbound Kid Sub Goal", color=discord.Color.green())
    embed.description = (
        f"**{current_subs:,}** / **{goal:,}** Subscribers\n\n"
        f"`[{progress_bar}] {percent:.1f}%`"
    )
    if current_subs >= goal:
        embed.set_footer(text="🎉 Goal reached!")
    else:
        embed.set_footer(text=f"Just {goal - current_subs:,} more to go!")

    await ctx.send(embed=embed)

@bot.command()
async def bot_info(ctx):
    try:
        next_check = check_new_vid.next_iteration
        countdown = f"<t:{int(next_check.timestamp())}:R>"
    except:
        countdown = "Not scheduled"

    current_uptime = int(time.time() - start_time)
    days, remainder = divmod(current_uptime, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)
    latency = round(bot.latency * 1000)

    embed = discord.Embed(title="🤖 Outbound Bot Info", color=discord.Color.blue())
    embed.add_field(name="📺 Last Video ID", value=f"`{bot_data['last_vid']}`", inline=False)
    embed.add_field(name="⏰ Next YouTube Check", value=countdown, inline=False)
    embed.add_field(name="🟢 Uptime", value=f"`{days}d {hours}h {minutes}m {seconds}s`", inline=True)
    embed.add_field(name="📡 Latency", value=f"`{latency}ms`", inline=True)

    await ctx.send(embed=embed)

@bot.command()
async def help_bot(ctx):
    embed = discord.Embed(title="🛠️ Bot Commands", description="All commands start with `!`", color=discord.Color.gold())
    embed.add_field(name="Public Commands", value=
        "`!bot_info` - Bot status, latency and next check\n"
        "`!sub_info` - Subscriber goal progress", inline=False)

    if is_privileged(ctx):
        embed.add_field(name="Admin Commands (Owner/Trusted Only)", value=
            "`!check` - Force check for new videos\n"
            "`!set_sub_goal <number>` - Set subscriber goal\n"
            "`!remove_sub_goal` - Remove current goal\n"
            "`!stop` - Safely shut down the bot", inline=False)

    await ctx.send(embed=embed)

bot.run(TOKEN)
