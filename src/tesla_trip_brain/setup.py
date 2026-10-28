"""Guided first-run setup: plain-language questions, writes .env itself.

Built for Tesla owners, not developers — defaults everywhere, numbered
choices, charger and battery questions in plain words. Testable: input
and output are injectable.
"""
from __future__ import annotations

import os
from pathlib import Path


def _ask(input_fn, out, prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    out(f"{prompt}{suffix}")
    answer = input_fn("> ").strip()
    return answer or default


def _ask_required(input_fn, out, prompt: str, help_text: str) -> str:
    while True:
        out(help_text)
        answer = input_fn(f"{prompt} ").strip()
        if answer:
            return answer
        out("That one's required — without it the app can't do its job.")


def _ask_yes_no(input_fn, out, prompt: str, default: str = "n") -> bool:
    answer = _ask(input_fn, out, prompt + " (y/n)", default)
    return answer.lower() in ("y", "yes")


def run_setup(input_fn=input, out=print, env_path: str = ".env") -> Path:
    out("")
    out("Welcome to Tesla Trip Brain setup — I'll ask a few questions and")
    out("write the settings file for you. Press Enter to accept a [default].")
    out("")

    path = Path(env_path)
    if path.exists():
        again = _ask(input_fn, out,
                     "A settings file (.env) already exists. Replace it? (y/n)", "n")
        if again.lower() not in ("y", "yes"):
            out("Keeping your existing settings. Nothing changed.")
            return path

    out("STEP 1 of 5 — Connect to Tesla")
    out("Create a free developer app at developer.tesla.com (sign in, then")
    out("'Create App'). Tesla will show you a Client ID and Client Secret.")
    client_id = _ask_required(input_fn, out, "Paste your Client ID:",
                              "First, the Client ID:")
    client_secret = _ask_required(
        input_fn, out, "Paste your Client Secret:",
        "Now the Client Secret (it stays on this computer):")

    out("")
    out("STEP 2 of 5 — Your cars")
    out("For each car: a nickname and its VIN. Find the VIN in your Tesla")
    out("app under Controls → Software (or on the car's touchscreen).")
    vehicles: list[tuple[str, str]] = []
    while True:
        n = len(vehicles) + 1
        name = _ask(input_fn, out,
                    f"Car {n} nickname (e.g. Model Y) — or press Enter if done:",
                    "")
        if not name:
            if vehicles:
                break
            out("Add at least one car to continue.")
            continue
        vin = _ask_required(input_fn, out, f"VIN for {name}:",
                            f"Now the VIN for {name}:")
        vehicles.append((name, vin))

    out("")
    out("STEP 3 of 5 - Your home charger and battery")
    out("Most home wall chargers deliver 11.5 kW; a regular wall outlet")
    out("is about 1.4 kW. Your pack size is on your car's touchscreen")
    out("under Controls > Software, or just take the default (75 kWh")
    out("covers most Model 3/Y cars).")
    charger = _ask(input_fn, out, "Home charger power in kW:", "11.5")
    pack = _ask(input_fn, out, "Usable battery size in kWh:", "75")
    reserve = _ask(input_fn, out,
                   "Reserve to keep on arrival, as a % of battery:", "10")

    out("")
    out("STEP 4 of 5 - Your calendar")
    out("Export your calendar as an .ics file (Google Calendar: Settings")
    out("> Import & export > Export) and tell me where it is. Events")
    out("need a distance in the description, like 'distance: 120 mi'.")
    out("If you skip this, the app plans against its demo trips.")
    cal = _ask(input_fn, out, "Calendar (.ics) file location:", "~/.ttb/trips.ics")

    out("")
    out("STEP 5 of 5 - The AI explainer (optional) and the trip server")
    out("  1) Built-in answers only - no AI, nothing leaves this computer")
    out("  2) Ollama on this computer - free local AI (default)")
    out("  3) Another AI service (OpenAI, Groq, LM Studio...) - you'll paste its details")
    choice = _ask(input_fn, out, "Pick 1, 2 or 3:", "2")
    ai_mode, ai_url, ai_key, ai_model = "auto", "http://localhost:11434/v1", "", "llama3.1"
    if choice == "1":
        ai_mode = "never"
    elif choice == "3":
        ai_url = _ask_required(input_fn, out, "Service address (base URL):",
                               "Paste the service's API address:")
        ai_key = _ask(input_fn, out, "API key for that service (stored only here):")
        ai_model = _ask(input_fn, out, "Model name:", "gpt-4o-mini")
    port = _ask(input_fn, out, "Port for the trip-planning address:", "8651")
    server_key = _ask(input_fn, out,
                      "Optional password for the trip-planning address (blank = none):")

    lines = [
        "# Written by `ttrip setup` - edit by re-running setup any time.",
        f"TESLA_CLIENT_ID={client_id}",
        f"TESLA_CLIENT_SECRET={client_secret}",
        "TESLA_REGION=na",
        "TESLA_REDIRECT_URI=http://localhost:8080/callback",
        "TTB_VEHICLES=" + ",".join(f"{name}={vin}" for name, vin in vehicles),
        "TTB_SERVER_HOST=127.0.0.1",
        f"TTB_SERVER_PORT={port}",
        f"TTB_SERVER_API_KEY={server_key}",
        "TTB_MODEL_ID=tesla-trip-brain",
        f"TTB_AI_BASE_URL={ai_url}",
        f"TTB_AI_API_KEY={ai_key}",
        f"TTB_AI_MODEL={ai_model}",
        f"TTB_AI_MODE={ai_mode}",
        "TTB_AI_TIMEOUT_SECONDS=20",
        "TTB_EMBEDDING_DIM=384",
        "TTB_TOKEN_FILE=~/.ttb/tokens.json",
        f"TTB_CHARGER_KW={charger}",
        f"TTB_PACK_KWH={pack}",
        f"TTB_RESERVE_PCT={reserve}",
        "TTB_COLD_THRESHOLD_F=40",
        f"TTB_CALENDAR_FILE={cal}",
        f"TTB_DATA_FILE={cal}",
        "TTB_DRY_RUN=0",
    ]
    path.write_text("\n".join(lines) + "\n")
    os.chmod(path, 0o600)

    out("")
    out("All set — settings saved to .env (only readable by you).")
    out("Next steps:")
    out("  1) ttrip auth       — sign in to Tesla once (opens a link)")
    out("  2) ttrip simulate   - see demo trips with a pretend car")
    out("  3) ttrip plan       - check readiness for your next trip")
    out("  4) ttrip preview    - what a trip plan would say (saves nothing)")
    out("  5) ttrip serve      - start the trip-planning Q&A API")
    return path
