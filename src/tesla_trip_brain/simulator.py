"""Demo trips for tests, demos, and the GitHub Pages POC.
No API calls, no real cars. One pretend Model Y at 62%.

- Tomorrow 8:00 AM: Big Bear, 120 miles, 32F at destination.
  Cold uplift makes the required SoC about 64% — just above the
  car's 62%, so it is NOT ready and must top up before leaving.
- Saturday 10:00 AM: Palm Springs, 90 miles, 78F, mild — ready
  at 62% with reserve to spare.
- Sunday 9:00 AM: Las Vegas, 270 miles, 70F — beyond one charge
  with reserve, so the plan says to Supercharge en route.

Core invariant the e2e test asserts: the Big Bear plan is
CHARGE_NEEDED with a start-by time before departure, and the
Palm Springs plan is READY.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .trip import Trip, plan_trip

DEMO_SOC = 62.0


def demo_trips(now: datetime | None = None) -> list[Trip]:
    la = ZoneInfo('America/Los_Angeles')
    now = (now or datetime.now(timezone.utc)).astimezone(la)
    tomorrow = (now + timedelta(days=1)).replace(hour=8, minute=0, second=0, microsecond=0)
    saturday = (now + timedelta(days=3)).replace(hour=10, minute=0, second=0, microsecond=0)
    sunday = (now + timedelta(days=4)).replace(hour=9, minute=0, second=0, microsecond=0)
    return [
        Trip("Ski weekend", "Big Bear", tomorrow, 120.0,
             destination_temp_f=32.0),
        Trip("Desert visit", "Palm Springs", saturday, 90.0,
             destination_temp_f=78.0),
        Trip("Vegas trip", "Las Vegas", sunday, 270.0,
             destination_temp_f=70.0),
    ]


def timeline_lines(settings, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(timezone.utc)
    trips = demo_trips(now)
    lines = ["Tesla Trip Brain — demo trips (pretend car, pretend calendar)"]
    lines.append(f"Current battery: {DEMO_SOC:.0f}% (pretend Model Y, 75 kWh pack)")
    lines.append("")
    for trip in trips:
        plan = plan_trip(trip, DEMO_SOC, now, pack_kwh=settings.pack_kwh,
                         reserve_pct=settings.reserve_pct,
                         charger_kw=settings.charger_kw)
        lines.append(f"{trip.title} -> {trip.destination}: "
                     f"{trip.distance_miles:.0f} miles, departs "
                     f"{trip.departure.strftime('%a %b %d, %I:%M %p')}, "
                     f"{trip.destination_temp_f:.0f}F at destination.")
        lines.append(f"  Drive energy {plan.drive_kwh:.1f} kWh at "
                     f"{plan.wh_per_mile:.0f} Wh/mile + precondition "
                     f"{plan.precondition_kwh:.1f} kWh + reserve "
                     f"{plan.reserve_kwh:.1f} kWh = needs {plan.required_soc:.0f}%.")
        lines.append(f"  {plan.summary_line()}")
        lines.append("")
    lines.append("Expected Fleet API cost: this app reads the car's battery %")
    lines.append("once per plan (a no-wake read) and issues no commands at all")
    lines.append("unless you ask it to start charging — so the real bill stays")
    lines.append("near zero, roughly $0.10/month at the default schedule.")
    return lines
