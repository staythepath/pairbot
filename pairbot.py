import discord
import json
import random
import logging
import os
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Set up logging
logging.basicConfig(level=logging.DEBUG)

# Initialize data structures
pairings_history = {}


# Function to load or initialize data
def load_data():
    global pairings_history
    if os.path.exists("pairings_history.json"):
        with open("pairings_history.json", "r") as file:
            data = json.load(file)
        pairings_history = data.get("pairings", {})
        logging.info("Loaded pairings history from file.")
    else:
        pairings_history = {}
        logging.warning(
            "pairings_history.json not found. Starting with an empty pairings history."
        )


# Load data initially
load_data()

# Setup bot intents
intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
intents.guilds = True

# Initialize the bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Initialize the scheduler
scheduler = AsyncIOScheduler()


# Bot event when ready
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
    load_data()


# Function to find the best partner for a member
def find_best_partner(member_id, current_members, member_history, paired_members):
    potential_partners = [
        m for m in current_members if m != member_id and m not in paired_members
    ]
    least_recently_paired = None
    longest_time = timedelta.min

    for partner_id in potential_partners:
        last_paired_time = datetime.min
        for pairing_time in member_history.get(partner_id, {}):
            if pairing_time != "name":
                pairing_time_obj = datetime.strptime(pairing_time, "%Y-%m-%d %H:%M:%S")
                if (
                    member_history[partner_id][pairing_time] == member_id
                    and pairing_time_obj > last_paired_time
                ):
                    last_paired_time = pairing_time_obj

        time_since_last_paired = datetime.now() - last_paired_time
        if time_since_last_paired > longest_time:
            longest_time = time_since_last_paired
            least_recently_paired = partner_id

    return least_recently_paired


# Function to update member history
def update_member_history(
    member_id, partner_id, current_time, member_history, current_members
):
    member_history_entry = member_history.get(
        member_id, {"name": current_members[member_id]}
    )
    member_history_entry[current_time] = partner_id
    member_history[member_id] = member_history_entry


# Function to pair members
# @tasks.loop(hours=168)
async def pair_members():
    global pairings_history
    load_data()  # Reload data every time we run the pairing

    # Ensure JSON file exists
    if not os.path.exists("pairings_history.json"):
        with open("pairings_history.json", "w") as file:
            json.dump({"pairings": {}, "members": {}}, file, indent=4)

    # Load member history from JSON file
    with open("pairings_history.json", "r") as file:
        data = json.load(file)
    member_history = data.get("members", {})

    guild = discord.utils.get(bot.guilds, name="The Long Journey")
    if not guild:
        logging.error("Guild not found")
        return

    announcement_channel = discord.utils.get(guild.channels, name="pairing-testing")
    if not announcement_channel:
        logging.error("Announcement channel not found")
        return

    current_members = {
        str(member.id): member.display_name
        for member in guild.members
        if not member.bot and discord.utils.get(member.roles, name="member")
    }

    # Shuffle the list of member IDs to randomize pairing order
    member_ids = list(current_members.keys())
    random.shuffle(member_ids)

    new_pairings = []
    paired_members = set()
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Special handling for "StayThePath" if odd number of members
    if len(member_ids) % 2 != 0:
        extra_member_id = "273183253207318530"  # ID for "StayThePath"

        first_partner_id = find_best_partner(
            extra_member_id, current_members, member_history, paired_members
        )
        if first_partner_id:
            new_pairings.append((extra_member_id, first_partner_id))
            update_member_history(
                extra_member_id,
                first_partner_id,
                current_time,
                member_history,
                current_members,
            )
            update_member_history(
                first_partner_id,
                extra_member_id,
                current_time,
                member_history,
                current_members,
            )
            paired_members.update([extra_member_id, first_partner_id])

        # Ensure "StayThePath" is eligible for a second pairing
        second_partner_id = find_best_partner(
            extra_member_id,
            current_members,
            member_history,
            paired_members - {first_partner_id},
        )
        if second_partner_id:
            new_pairings.append((extra_member_id, second_partner_id))
            update_member_history(
                extra_member_id,
                second_partner_id,
                current_time,
                member_history,
                current_members,
            )
            update_member_history(
                second_partner_id,
                extra_member_id,
                current_time,
                member_history,
                current_members,
            )
            paired_members.update([second_partner_id])

    # Pair the remaining members
    for member_id in member_ids:
        if member_id not in paired_members:
            partner_id = find_best_partner(
                member_id, current_members, member_history, paired_members
            )
            if partner_id:
                new_pairings.append((member_id, partner_id))
                update_member_history(
                    member_id, partner_id, current_time, member_history, current_members
                )
                update_member_history(
                    partner_id, member_id, current_time, member_history, current_members
                )
                paired_members.update([member_id, partner_id])

    new_pairings_with_details = []

    for member_id, partner_id in new_pairings:
        print("member_id: ", member_id)
        print("partner_id: ", partner_id)
        try:
            member = await guild.fetch_member(int(member_id))
            partner = await guild.fetch_member(int(partner_id))
            announcement = (
                f"{member.mention} is paired with {partner.mention} this week!"
            )
            await announcement_channel.send(announcement)
            new_pairings_with_details.append(
                {member.display_name: partner.display_name}
            )
        except Exception as e:
            logging.error(f"Error in sending pairing announcement: {e}")

    pairings_history[current_time] = new_pairings_with_details

    # Write the updated member and pairings history back to the file
    with open("pairings_history.json", "r+") as file:
        data["members"] = member_history
        data["pairings"] = pairings_history
        file.seek(0)
        json.dump(data, file, indent=4)
        file.truncate()

    logging.info("Completed pairings.")


# Add job to the scheduler
scheduler.add_job(
    pair_members,
    CronTrigger(day_of_week="fri", hour=12, minute=0, timezone="America/Chicago"),
)


# Bot event when ready
@bot.event
async def on_ready():
    logging.info(f"Logged in as {bot.user}")
    load_data()
    scheduler.start()  # Start the scheduler


# Command to trigger pairing manually
@bot.command(name="pair")
async def pair_command(ctx):
    logging.info(f"Pair command invoked by {ctx.author}")
    await pair_members()


# Run the bot
bot.run("")
