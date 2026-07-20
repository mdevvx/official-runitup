# RunItUp Challenge Bot

A Discord bot that runs the RunItUp points challenge: tracks daily activity, value posts, wins, and referrals; ranks members on season/weekly/monthly leaderboards; and automates the full Q2 Championship system — Weekly Victory, Monthly Victory, Official Finisher, the Championship Raffle, Golden Ticket surprise events, and the end-of-challenge Grand Championship.

Everything *trackable* (points, thresholds, badges, roles, tickets, rankings, announcements) is automated. Actual reward *fulfillment* (handing out coaching calls, software licenses, AI tool access) stays a moderator job — the doc itself assigns that to moderators, and it's not something a bot can do.

---

## Setup

**Requirements:** Python 3.10+, a Supabase project, a Discord bot application.

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in the values below
python bot.py
```

**Required env vars** (`.env`):

| Var | What it's for |
|---|---|
| `DISCORD_TOKEN`, `GUILD_ID` | Bot login + which server to sync commands to |
| `ADMIN_ROLE_ID`, `MOD_ROLE_ID` | Who can run `[ADMIN]` commands |
| `SUPABASE_URL`, `SUPABASE_KEY` | Database |
| `DIALED_GUILD_ID`, `DIALED_WINS_CHANNEL_ID`, `RUNITUP_WINS_CHANNEL_ID` | Cross-server wins relay (`cogs/wins_relay.py`) — mirrors #wins posts from the Dialed server into RunItUp |

Everything else in `.env.example` is optional and has a sane default or a slash-command equivalent (see `/q2 setchannel`, `/q2 setchallengedates` below) — the DB-backed config always takes priority over env vars once set.

**Run the migrations, in order**, in the Supabase SQL editor:

| File | Adds |
|---|---|
| `migrations/schema.sql` | Base schema |
| `002_q2_relaunch.sql` | Q1→Q2 season archive, `bot_config` table, Masters flag |
| `003_weekly_victory.sql` | `points_history.category`, `weekly_victories`, Official Finisher flag |
| `004_monthly_victory.sql` | `monthly_victories` |
| `005_raffle_tickets.sql` | `users.raffle_tickets`, `raffle_ticket_history` |
| `006_golden_tickets_and_finale.sql` | Streak tracking, `is_founder`/`is_grand_champion` flags |
| `007_winners_and_raffle_draw.sql` | `raffle_draw_winners` |

**Then, in Discord**, create these roles (exact names, exact em dash `—`, all positioned *below* the bot's own role — Discord only lets a bot grant roles beneath itself):

- Tier roles: `Q2 — Challenger`, `Q2 — Builder`, `Q2 — Operator`, `Q2 — Elite`
- `Q2 — Scaler`, `Masters 🥋` (or bind your own via `/q2 setrole`)
- `Q2 — Week 1 Victor` through `Q2 — Week 10 Victor`
- `Q2 — Month 1 Champion`, `Q2 — Month 2 Champion`
- `Q2 — Official Finisher`
- `Q2 — Founder`, `Q2 — Grand Champion`

The bot never creates roles itself — it looks them up by exact name and grants/revokes. A missing role just logs a warning and skips; nothing crashes.

Finally, set your channels (`/q2 setchannel`) and challenge dates (`/q2 setchallengedates`) — **nothing awards points or runs any of the systems below until dates are set.** `challenge_status()` gates everything.

---

## How it works — the full flow

Points come from daily activity, value-drop posts, wins, referrals, and reviews (see `config/constants.py POINTS` for exact values). Every point award is tagged `category`: `"consistency"` (auto-tracked daily habits) or `"performance"` (admin-awarded wins/referrals/bonuses). That single tag is what keeps the systems below honest — Weekly/Monthly Victory only look at consistency points; the leaderboards look at everything.

An hourly background task (`cogs/tasks.py: finalize_weekly_victory_task`) drives almost everything below. It's fully idempotent — re-running it for something already finalized is always a safe no-op, so a missed run or a bot restart just catches up on the next tick.

### Weekly Victory
10 full 7-day weeks (Weeks 1–10). Cross that week's points threshold (auto-computed at 51% of the max realistically-earnable consistency points, `/q2 setweeklyvictorythreshold` to override) and you're that week's winner — full stop, missed days don't disqualify you. Grants `Q2 — Week N Victor` and 25 raffle tickets (+100 more if it's a flagged Golden Ticket Day).

### Monthly Victory
Two months this season — **Month 1 = Weeks 1–4, Month 2 = Weeks 5–8** (the reward table only ever names these two; Weeks 9–10 belong to no month). Win 3 of that month's 4 weeks to win the month. Grants `Q2 — Month N Champion` and 100 raffle tickets.

### Official Finisher
Two independent paths, either one qualifies you:
1. **Win 9 of 10 weeks** — fully automatic, no setup.
2. **Reach ~82.5% of the current season leader's total points** — recomputed live every check (there's no fixed "max points" once open-ended wins/referrals are in play). `/q2 setfinisherpoints` can pin a fixed number instead.

Grants `Q2 — Official Finisher` and 500 raffle tickets, the moment you qualify — not held until the end of the challenge.

### Weekly / Monthly Leaderboards
Separate from Victory — this is pure points ranking (all categories), reset each week/month. You can top the weekly leaderboard without crossing that week's Victory threshold, or vice versa; both can happen to the same person and both pay out. Weekly Top 10 (+25 tickets) / Weekly Champion (+100) and Monthly Top 10 (+100) / Monthly Champion (+250) all stack with Victory rewards.

### Championship Raffle
Every member's ticket total (`/q2 rafflepool` to check standings) grows automatically from every system above. `/q2 raffledraw confirm:True` (admin, one-time per season) runs the actual weighted draw across all 21 prize slots (Grand Prize → Two → Three → Five → Ten Winners), without replacement so nobody double-wins. Results are permanent once drawn — `/q2 rafflewinners` shows them anytime after.

### Golden Ticket Events
Moderator-triggered surprise bonuses — "no warning, no schedule" is the point, nothing here fires automatically:

| Command | Effect |
|---|---|
| `/q2 goldenticket day` | Flags *this* week — its eventual Weekly Victory winners get +100 bonus tickets |
| `/q2 goldenticket next25` | Arms a live counter — the next N people (default 25) to complete today's habit get +25 each, in real time |
| `/q2 goldenticket streak` | Immediate — everyone on a 14+ day streak gets +50 |
| `/q2 goldenticket allhabits` | Immediate — everyone who's hit all 4 trackable habits today gets +100 |

### Grand Championship (end of challenge)
The moment `challenge_status()` flips to `"ended"`, the final season leaderboard locks and pays out: **Top 25** → `Q2 — Founder` + 250 tickets, **Top 10** → +500 tickets (stacks), **Rank 1** → `Q2 — Grand Champion` + 1,000 tickets (stacks with both). `/q2 finalstandings` shows it live or locked depending on challenge status.

### Announcements
The moment a week finalizes, a month finalizes, someone becomes an Official Finisher, or the Championship locks — an embed posts automatically to your `announcements` channel (falls back to `leaderboard`). Each fires exactly once, even though the underlying task re-runs hourly.

---

## Commands

### Member — `/q2 …`

| Command | Shows |
|---|---|
| `points` | Your points, tier, Scaler/Masters badges, Official Finisher badge, weeks/months won, raffle tickets, season rank |
| `leaderboard [limit] [scope: season\|week\|month]` | Ranked list for the chosen scope |
| `mytier` | Current tier and progress to the next one |
| `weeklywinners [week_number]` | Who won a given week (defaults to the most recently closed) |
| `monthlywinners [month_number]` | Who won a given month (defaults to the most recently closed) |
| `finishers` | Everyone with Official Finisher status |
| `finalstandings` | Top 25 — labeled live or locked depending on challenge status |
| `rafflepool [limit]` | Current raffle ticket standings |
| `rafflewinners` | Raffle draw results, once drawn |

### Admin — Points & users

| Command | Params | Does |
|---|---|---|
| `addpoints` | user, points, reason, is_win | Manual award (tagged performance — never counts toward Victory) |
| `removepoints` | user, points, reason | Manual deduction |
| `addreferral` | user, referral_type, count | Whop (+10 ea.) or Discord (+5 ea.) referrals, capped at the season max |
| `viewuser` | user | Full stat card + last 5 points-history entries for any member |
| `setmaster` | user, enabled | Grants/revokes the +15% Masters win bonus |

### Admin — Configuration

| Command | Params | Does |
|---|---|---|
| `setchannel` | channel_type, channel | Registers a channel (leaderboard, wins, announcements, etc.) |
| `listchannels` | — | Shows all registered channels |
| `setrole` | role_type: masters\|scalers, role | Binds a Discord role to Masters/Scalers status |
| `setchallengedates` | start_date, end_date, timezone | The single source of truth for every week/month boundary and the finale trigger |
| `settierpoints` | tier, min_points | Overrides a tier's point floor |
| `config` | — | Full config dump: channels, dates, tiers, thresholds, special roles |

### Admin — Weekly Victory & Finisher tuning

| Command | Params | Does |
|---|---|---|
| `setweeklyvictorythreshold` | points | Overrides the auto-computed weekly bar |
| `setfinisherpoints` | points | Pins Official Finisher's points path to a fixed number instead of the auto ~82.5%-of-leader calculation |

### Admin — Golden Ticket events (`/q2 goldenticket …`)

| Command | Params | Does |
|---|---|---|
| `day` | — | Flags the current week |
| `next25` | count (optional) | Arms the live "next N" bonus |
| `streak` | — | Immediate 14-day-streak bonus |
| `allhabits` | — | Immediate all-habits-today bonus |

### Admin — Championship Raffle

| Command | Params | Does |
|---|---|---|
| `raffledraw` | confirm (required bool) | Runs the one-time weighted prize draw. Refuses to re-run once a season's been drawn. |

---

## Architecture

```
bot.py                  Entry point - loads cogs, syncs the /q2 command tree
cogs/
  members.py            Member-facing /q2 commands
  admin.py               [ADMIN] /q2 commands, incl. the goldenticket subgroup
  leaderboard.py          Passive listener: daily todo / calls / value-post reactions
  tasks.py                Background loops: leaderboard auto-post, hourly finalize task
  wins_relay.py            Cross-server #wins mirror (Dialed -> RunItUp)
  season_group.py          The shared /<season> command group + golden_ticket_group subgroup
database/
  models.py              All game logic: UserModel, WeeklyVictoryModel, MonthlyVictoryModel,
                          RaffleTicketModel, GoldenTicketModel, RaffleDrawModel, ChampionshipModel
  bot_config.py           DB-backed key/value config (channels, thresholds, golden ticket state)
  supabase_client.py      Supabase connection
utils/
  embeds.py               All Discord embed builders
  helpers.py               Challenge-window/week/month date math, misc formatting
config/
  constants.py            Point values, thresholds, tier ranges, ticket values - the tunable knobs
  settings.py              Env var loading
migrations/               Numbered SQL migrations, run in order
```

**Renaming the season**: bump `CURRENT_SEASON` in `config/constants.py` (e.g. `"Q2"` → `"Q3"`) and restart — every `/<season>`-prefixed command and Discord role name regenerates automatically. Previous seasons' roles are left untouched.
