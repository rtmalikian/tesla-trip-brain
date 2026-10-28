# Tesla Trip Brain — Free Trip-Readiness Planner for Tesla Model 3, Model Y, Model S, Model X & Cybertruck

> **▶ Try the live demo: https://rtmalikian.github.io/tesla-trip-brain/** (interactive, runs on pretend data)

**Free & open source trip-readiness planning via the Tesla Fleet API: calendar trips + your battery % + destination weather = the battery % you need to leave with, when to start charging, and how long to precondition — so you never discover at departure time that you're not ready. No paid app, no subscription, no waking your car.**

## Why?

Tesla owners ask the same question the night before a trip, with no free answer:

- "Am I ready for tomorrow's drive to Big Bear?" — Tesla's navigation reacts en route; nothing pre-computes readiness the night before.
- "When do I need to start charging?" — the app shows your current %, never the % you need, the charging time, or the start-by time.
- "Will the cold eat my range?" — a 120-mile drive in 32°F weather needs noticeably more than the same drive at 70°F, and nobody does that math for you.

Trip Brain does it: it reads your calendar trips (an .ics export — Google Calendar, Apple Calendar, Outlook), adds destination weather, and computes the departure plan with the math printed next to the answer. Tesla nav reacts en route; Trip Brain answers *before* you leave.

## How it works

```
Tomorrow 8:00 AM — Ski weekend → Big Bear, 120 miles, 32°F at destination
  Drive energy:     38.6 kWh at 322 Wh/mile (cold uplift +15%)
  Preconditioning:   2.0 kWh (30 min, cold morning)
  Reserve:           7.5 kWh (10% — never plan to arrive at 0%)
  You need 64% to leave; you have 62%.
  → Not ready yet: start charging by about 7:21 AM, then precondition 30 min before leaving.

Saturday 10:00 AM — Desert visit → Palm Springs, 90 miles, 78°F
  You need 44%; you have 62%. → Ready. Precondition 15 min before leaving.

Sunday 9:00 AM — Vegas trip → Las Vegas, 270 miles, 70°F
  You need 111% — beyond a full battery. → Charge now, or plan a Supercharger stop en route.
```

**The math, stated plainly.** Required departure SoC = (drive energy + preconditioning + reserve) ÷ pack size. Drive energy uses 280 Wh/mile, adjusted for destination weather: below 40°F adds 15% (below 20°F, 25%), above 95°F adds 10%. Preconditioning is 2.0 kWh on cold/hot days (30 min), 0.5 kWh otherwise (15 min). Reserve defaults to 10% and is yours to change in setup. Every plan prints its breakdown — the number is never a black box.

**Calendar trips.** Export your calendar as .ics and point `TTB_CALENDAR_FILE` at it. Events need a distance in the description, like `distance: 120 mi` (and optionally `temperature: 32F`). Events without a distance are skipped and the app says so — a title alone cannot size a charge plan. Date-only events are treated as 9:00 AM departures.

**Expected API cost:** this app reads the car's battery % once per plan (a no-wake read) and issues no commands unless you ask it to start charging, so the real bill stays near zero — roughly $0.10/month at the default schedule. Wakes are the priciest Fleet API call, so a sleeping car is simply read later, never woken to measure something.

## Quickstart (for owners, not developers)

No AI needed: everything below works with no LLM backend at all. The AI explainer is an optional extra.

```bash
git clone https://github.com/rtmalikian/tesla-trip-brain.git
cd tesla-trip-brain
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ttrip setup        # plain-language questions — writes .env for you
ttrip simulate     # see demo trips with a pretend car (no car needed)
ttrip plan         # check readiness for your next trip (asks battery % if needed)
ttrip preview      # what a trip plan would say (changes nothing)
ttrip serve        # start the trip-planning API on http://127.0.0.1:8651
```

What you'll see when it works: `ttrip simulate` prints three demo trips — Big Bear (not ready, start charging tonight), Palm Springs (ready), Las Vegas (beyond one charge) — with the full energy breakdown for each. `ttrip setup` asks for your Tesla developer credentials, your cars (numbered list, VIN found in the Tesla app under Controls → Software), your home charger power (11.5 kW prefilled), pack size (75 kWh prefilled), reserve (10% prefilled), and your calendar file — then writes `.env` for you. Nobody hand-edits config syntax.

### Commands

| Command | What it does |
|---|---|
| `ttrip setup` | Guided first-run setup — writes `.env` for you |
| `ttrip auth` | One-time Tesla authorization (prints the link) |
| `ttrip plan [--destination Big Bear] [--soc 62]` | Readiness plan for a trip |
| `ttrip preview` | Same plan, labelled preview — changes nothing |
| `ttrip ask "am I ready for tomorrow's drive to Big Bear?"` | One-shot question via the same engine as the API |
| `ttrip serve` | OpenAI-compatible API server on port 8651 |
| `ttrip simulate` | Demo trips timeline (no API calls, no car needed) |

## AI endpoints

Trip Brain embeds an OpenAI-compatible API, so any OpenAI client can ask it readiness questions. The rules engine answers from the computed plans with no backend at all; a pluggable LLM backend (local Ollama by default, or any OpenAI-compatible service) only explains the plans in free-form words — it never invents a battery %, a trip, or a distance. Vehicle and trip data go only to the backend you configure, nowhere else. LLM-emitted text is never executed as a car command.

```bash
# What models are available?
curl http://127.0.0.1:8651/v1/models

# Am I ready for tomorrow's trip?
curl http://127.0.0.1:8651/v1/chat/completions -H 'Content-Type: application/json' -d '{
  "model": "tesla-trip-brain",
  "messages": [{"role": "user", "content": "am I ready for tomorrow'"'"'s drive to Big Bear?"}]
}'

# Embeddings over trip text (local deterministic hashing, dim 384 by default)
curl http://127.0.0.1:8651/v1/embeddings -H 'Content-Type: application/json' -d '{
  "model": "tesla-trip-brain", "input": "Big Bear ski trip 120 miles"
}'
```

Streaming is not supported (`stream=true` is ignored); responses follow the standard OpenAI chat-completion shape. Optional bearer auth: set `TTB_SERVER_API_KEY` and send `Authorization: Bearer <key>`.

## Tesla developer setup

1. Create a free app at [developer.tesla.com](https://developer.tesla.com) and note the Client ID and Secret.
2. Run `ttrip setup` and paste them when asked (they stay in `.env` on your computer).
3. Run `ttrip auth`, open the printed link, and authorize. Pair a virtual key per the [Fleet API pairing docs](https://developer.tesla.com/docs/fleet-api#pairing).

## `.env` reference

| Variable | Meaning | Default |
|---|---|---|
| `TESLA_CLIENT_ID` / `TESLA_CLIENT_SECRET` | Your Tesla developer app credentials | — |
| `TESLA_REGION` | `na`, `eu`, or `cn` | `na` |
| `TTB_VEHICLES` | `name=VIN` pairs, comma-separated | — |
| `TTB_SERVER_HOST` / `TTB_SERVER_PORT` | The planning API address | `127.0.0.1` / `8651` |
| `TTB_SERVER_API_KEY` | Optional bearer token for `/v1/*` | (none) |
| `TTB_AI_BASE_URL` / `TTB_AI_API_KEY` / `TTB_AI_MODEL` / `TTB_AI_MODE` | Pluggable LLM backend (`auto`/`always`/`never`) | Ollama `http://localhost:11434/v1`, `llama3.1`, `auto` |
| `TTB_PACK_KWH` | Usable pack size | `75` |
| `TTB_RESERVE_PCT` | Reserve to keep on arrival (%) | `10` |
| `TTB_CHARGER_KW` | Home charger power | `11.5` |
| `TTB_CALENDAR_FILE` | Your calendar `.ics` export | `~/.ttb/trips.ics` |
| `TTB_DRY_RUN` | `1` = preview instead of acting | `0` |

## FAQ

**Do I need an AI backend?**
No. The rules engine computes every plan itself; the LLM only rephrases the answer. Run with `TTB_AI_MODE=never` and nothing leaves your computer.

**Where does my calendar come from?**
Any .ics export: Google Calendar (Settings → Import & export → Export), Apple Calendar (File → Export), or Outlook. Add `distance: 120 mi` to a trip event's description so the app can size the plan.

**Why is the Big Bear trip 322 Wh/mile instead of 280?**
Cold weather: below 40°F adds 15% to consumption (heating the cabin and battery). The demo's 32°F destination is why 120 miles needs 38.6 kWh instead of 33.6.

**What if my trip is longer than one charge?**
The plan says so plainly ("you need 111% — beyond a full battery") and suggests charging now or planning a Supercharger stop en route, rather than pretending you'll make it.

**Does it wake my car?**
No. It reads the battery % you supply (or a no-wake last-known state) and issues no commands unless you explicitly ask. A sleeping car is never woken just to measure something.

**Does it work for Model S, X, and Cybertruck?**
Yes — change `TTB_PACK_KWH` to your car's usable pack size in setup (Cybertruck ~123 kWh, Model S ~100 kWh) and the same math applies.

## License

MIT — Raphael Malikian. Free & open source, no subscription, no account, no data leaving your computer except to the LLM backend you choose.
