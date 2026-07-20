from discord import app_commands

from config.constants import CURRENT_SEASON, SEASON_PREFIX

# Shared /<season> command group (e.g. "/q2 setchannel", "/q2 points").
# cogs/admin.py and cogs/members.py both attach their subcommands to this same
# Group object via @season_group.command(...), so everything appears under one
# grouped command in Discord instead of a flat /q2addpoints, /q2points, etc.
# Renaming CURRENT_SEASON in config/constants.py renames this whole group (and
# every subcommand under it) automatically on next bot restart.
season_group = app_commands.Group(
    name=SEASON_PREFIX,
    description=f"{CURRENT_SEASON} challenge commands",
)

# Nested subgroup for the 4 Golden Ticket admin commands (/<season>
# goldenticket day|next25|streak|allhabits). A subgroup's children don't
# count against the parent group's 25-direct-child limit - the group
# itself is one child of season_group, so this is also what keeps
# season_group under that limit as more commands get added over time.
golden_ticket_group = app_commands.Group(
    name="goldenticket",
    description="Moderator-triggered Golden Ticket surprise bonus events",
    parent=season_group,
)
