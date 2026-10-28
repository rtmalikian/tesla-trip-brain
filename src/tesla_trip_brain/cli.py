"""CLI: ttrip setup | auth | serve | ask | plan | preview | simulate

Safety posture: planning only reads your calendar file and a battery
% you supply — no car is woken or commanded. `preview` shows the
plan before anything real happens, and the first real action asks
for confirmation (there is no automatic charging command here).
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

from .config import ConfigError, load_settings

__version__ = "0.1.0"


def _setup_logging(verbose: bool) -> None:
    import logging
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")


def _client(settings):
    from .tesla_client import TeslaClient
    return TeslaClient(settings.client_id, settings.client_secret,
                       region=settings.region, redirect_uri=settings.redirect_uri,
                       token_file=settings.token_file)


def cmd_auth(args, settings) -> int:
    client = _client(settings)
    print("Open this URL in your browser and authorize:")
    print(client.authorize_url())
    print("Virtual-key pairing: https://developer.tesla.com/docs/fleet-api#pairing")
    return 0


def cmd_setup(args, settings) -> int:
    from .setup import run_setup
    run_setup()
    return 0


def _trips_for_api(settings):
    """Real calendar trips if the file exists, else demo trips (labelled)."""
    from .simulator import demo_trips
    from .trip import load_trips
    real = load_trips(settings.calendar_file)
    if real:
        return real, False
    return demo_trips(), True


def cmd_serve(args, settings) -> int:
    from .server import serve
    from .service import TripBrainService
    trips, is_demo = _trips_for_api(settings)
    service = TripBrainService(settings, trips_provider=lambda: trips,
                               soc_provider=lambda: 70.0)
    print("Trip data goes ONLY to your configured LLM backend "
          f"(TTB_AI_BASE_URL={settings.ai_base_url or 'none'}); "
          "the rules engine answers readiness questions with no backend at all.")
    if is_demo:
        print("(Serving the demo trips — point TTB_CALENDAR_FILE at your .ics")
        print(" export and the API will answer from your calendar instead.)")
    print("This app only plans trips — it never wakes or commands a car.")
    serve(service)
    return 0


def cmd_ask(args, settings) -> int:
    from .service import TripBrainService
    trips, is_demo = _trips_for_api(settings)
    soc = args.soc if args.soc is not None else 70.0
    service = TripBrainService(settings, trips_provider=lambda: trips,
                               soc_provider=lambda: soc)
    if is_demo:
        print("(Demo trips — point TTB_CALENDAR_FILE at your .ics export to ask about your own trips.)")
    body = {"model": settings.model_id,
            "messages": [{"role": "user", "content": args.question}]}
    resp = service.chat_completions(body)
    print(resp["choices"][0]["message"]["content"])
    return 0


def _pick_trip(args, trips, settings):
    from .trip import Trip
    if args.destination:
        for t in trips:
            if args.destination.lower() in f"{t.destination} {t.title}".lower():
                return t
        print(f"No trip to {args.destination!r} found. Upcoming trips:")
        for t in trips:
            print(f"  - {t.destination} ({t.title})")
        return None
    upcoming = sorted((t for t in trips if t.departure > datetime.now(timezone.utc)),
                      key=lambda t: t.departure)
    if not upcoming:
        print("No upcoming trips. Add one to your calendar export, or run `ttrip simulate`.")
        return None
    if len(upcoming) == 1:
        return upcoming[0]
    print("Which trip?")
    for i, t in enumerate(upcoming, 1):
        print(f"  {i}) {t.destination} — {t.title}, {t.departure.strftime('%a %b %d, %I:%M %p')}")
    pick = input("> ").strip()
    try:
        return upcoming[int(pick) - 1]
    except (ValueError, IndexError):
        print("That wasn't one of the numbered trips — try again.")
        return None


def _plan_for(args, settings, dry_run: bool) -> int:
    from .trip import plan_trip
    trips, is_demo = _trips_for_api(settings)
    trip = _pick_trip(args, trips, settings)
    if trip is None:
        return 2
    if args.soc is None:
        raw = input("Current battery % (like 62):\n> ").strip()
        try:
            soc = float(raw)
        except ValueError:
            print("That needs to be a number — battery % like 62.")
            return 2
    else:
        soc = args.soc
    plan = plan_trip(trip, soc, datetime.now(timezone.utc),
                     pack_kwh=settings.pack_kwh, reserve_pct=settings.reserve_pct,
                     charger_kw=settings.charger_kw)
    if is_demo:
        print("(Demo trip — point TTB_CALENDAR_FILE at your .ics export for your own trips.)")
    print("")
    print("Here's what I would do:" if dry_run else "Trip plan:")
    print(f"  Trip: {trip.title} -> {trip.destination}, {trip.distance_miles:.0f} miles,")
    print(f"        departs {trip.departure.strftime('%a %b %d, %I:%M %p')}")
    if trip.destination_temp_f is not None:
        print(f"        {trip.destination_temp_f:.0f}F at destination")
    print(f"  Drive energy: {plan.drive_kwh:.1f} kWh at {plan.wh_per_mile:.0f} Wh/mile")
    print(f"  Preconditioning: {plan.precondition_kwh:.1f} kWh ({plan.precondition_minutes} min)")
    print(f"  Reserve: {plan.reserve_kwh:.1f} kWh ({settings.reserve_pct:.0f}%)")
    print(f"  You need {plan.required_soc:.0f}% to leave; you have {soc:.0f}%.")
    print(f"  {plan.summary_line()}")
    if dry_run:
        print("Preview only — nothing was changed and no car was contacted.")
    return 0


def cmd_plan(args, settings) -> int:
    return _plan_for(args, settings, dry_run=False)


def cmd_preview(args, settings) -> int:
    return _plan_for(args, settings, dry_run=True)


def cmd_simulate(_args, settings) -> int:
    from .simulator import timeline_lines
    for line in timeline_lines(settings):
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ttrip",
        description="A free trip-readiness planner for your Teslas: "
                    "calendar trips + battery % + destination weather = "
                    "the charge and precondition plan before you leave.")
    p.add_argument("--version", action="version", version=f"ttrip {__version__}")
    p.add_argument("--env-file", default=None)
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("setup", help="Guided first-run setup (plain-language questions)")
    sub.add_parser("auth", help="Authorize with your Tesla account (one-time)")
    sub.add_parser("serve", help="Run the OpenAI-compatible trip-planning API server")
    ask_p = sub.add_parser("ask", help="One-shot trip question (your calendar, or demo trips)")
    ask_p.add_argument("question", help="e.g. 'am I ready for tomorrow's drive to Big Bear?'")
    ask_p.add_argument("--soc", type=float, default=None, help="Current battery %")
    plan_p = sub.add_parser("plan", help="Check readiness for a trip")
    plan_p.add_argument("--destination", default=None, help="e.g. Big Bear")
    plan_p.add_argument("--soc", type=float, default=None, help="Current battery %")
    prv_p = sub.add_parser("preview", help="What a trip plan would say (changes nothing)")
    prv_p.add_argument("--destination", default=None)
    prv_p.add_argument("--soc", type=float, default=None)
    sub.add_parser("simulate", help="Demo trips timeline (no API calls)")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    env = dict(os.environ)
    if args.env_file:
        from dotenv import load_dotenv
        load_dotenv(args.env_file, override=True)
        env = dict(os.environ)
    else:
        from dotenv import load_dotenv
        load_dotenv(override=False)
        env = dict(os.environ)
    try:
        settings = load_settings(env)
    except ConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    handlers = {"setup": cmd_setup, "auth": cmd_auth, "serve": cmd_serve,
                "ask": cmd_ask, "plan": cmd_plan, "preview": cmd_preview,
                "simulate": cmd_simulate}
    return handlers[args.command](args, settings)


if __name__ == "__main__":
    raise SystemExit(main())
