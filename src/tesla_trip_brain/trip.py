"""Trip-readiness logic: pure functions, no network, `now` injected.

A trip needs energy for the drive plus a reserve buffer plus cabin
preconditioning. The rules engine computes; the LLM only explains.

Consumption model (stated plainly, changeable in setup):
- base 280 Wh/mile (typical Model 3/Y mixed driving)
- destination colder than 40F: +15% (below 20F: +25%)
- destination hotter than 95F: +10% (A/C + battery cooling)
- preconditioning: 2.0 kWh when cold/hot, else 0.5 kWh
- reserve: 10% of pack by default (never plan to arrive at 0%)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

BASE_WH_PER_MILE = 280.0
DEFAULT_PACK_KWH = 75.0


@dataclass
class Trip:
    title: str
    destination: str
    departure: datetime
    distance_miles: float
    destination_temp_f: float | None = None
    vehicle: str = "Model Y"

    def __post_init__(self):
        if self.departure.tzinfo is None:
            self.departure = self.departure.replace(tzinfo=timezone.utc)


@dataclass
class TripPlan:
    trip: Trip
    current_soc: float
    pack_kwh: float
    wh_per_mile: float
    drive_kwh: float
    precondition_kwh: float
    reserve_kwh: float
    required_soc: float
    shortfall_kwh: float
    charge_hours: float
    precondition_minutes: int
    start_charging_by: datetime | None
    status: str  # READY | CHARGE_NEEDED | NOT_ENOUGH_TIME | DEPARTED

    def summary_line(self) -> str:
        t = self.trip
        dep = t.departure.strftime("%a %b %d, %I:%M %p")
        if self.required_soc > 100:
            return (f"Beyond one charge for {t.destination} ({dep}): you need "
                    f"{self.required_soc:.0f}% with reserve, more than a full "
                    f"battery holds. Charge to 100% and plan a Supercharger "
                    f"stop en route.")

        if self.status == "READY":
            return (f"Ready for {t.destination} ({dep}): you need "
                    f"{self.required_soc:.0f}% to leave with reserve, "
                    f"you have {self.current_soc:.0f}%. "
                    f"Precondition {self.precondition_minutes} min before leaving.")
        if self.status == "CHARGE_NEEDED":
            by = self.start_charging_by.strftime("%I:%M %p") if self.start_charging_by else "now"
            return (f"Not ready yet for {t.destination} ({dep}): you need "
                    f"{self.required_soc:.0f}%, you have {self.current_soc:.0f}% "
                    f"(short {self.shortfall_kwh:.1f} kWh, about "
                    f"{self.charge_hours:.1f} h on your home charger). "
                    f"Start charging by {by}, then precondition "
                    f"{self.precondition_minutes} min before leaving.")
        if self.status == "NOT_ENOUGH_TIME":
            return (f"Not enough time for {t.destination} ({dep}): you need "
                    f"{self.required_soc:.0f}%, you have {self.current_soc:.0f}%, "
                    f"but about {self.charge_hours:.1f} h of charging is needed "
                    f"and departure is sooner than that. Charge now, or "
                    f"leave later / stop at a Supercharger en route.")
        return f"That trip to {t.destination} already departed ({dep})."


def weather_factor(temp_f: float | None) -> float:
    if temp_f is None:
        return 1.0
    if temp_f < 20:
        return 1.25
    if temp_f < 40:
        return 1.15
    if temp_f > 95:
        return 1.10
    return 1.0


def precondition_kwh(temp_f: float | None) -> float:
    if temp_f is None:
        return 0.5
    if temp_f < 40 or temp_f > 95:
        return 2.0
    return 0.5


def precondition_minutes(temp_f: float | None) -> int:
    if temp_f is None:
        return 15
    if temp_f < 40 or temp_f > 95:
        return 30
    return 15


def plan_trip(trip: Trip, current_soc: float, now: datetime,
              pack_kwh: float = DEFAULT_PACK_KWH,
              reserve_pct: float = 10.0,
              charger_kw: float = 11.5) -> TripPlan:
    if not (0 <= current_soc <= 100):
        raise ValueError(f"Battery % must be 0-100, got {current_soc}")
    if trip.distance_miles < 0:
        raise ValueError("Distance cannot be negative")
    if pack_kwh <= 0 or charger_kw <= 0:
        raise ValueError("Pack size and charger power must be positive")
    factor = weather_factor(trip.destination_temp_f)
    wh = BASE_WH_PER_MILE * factor
    drive = trip.distance_miles * wh / 1000.0
    pre = precondition_kwh(trip.destination_temp_f)
    reserve = pack_kwh * reserve_pct / 100.0
    required = (drive + pre + reserve) / pack_kwh * 100.0
    shortfall = max(0.0, (required - current_soc) / 100.0 * pack_kwh)
    charge_hours = shortfall / charger_kw if shortfall > 0 else 0.0
    mins = precondition_minutes(trip.destination_temp_f)
    if trip.departure <= now:
        status, start_by = "DEPARTED", None
    elif required > 100:
        status, start_by = "NOT_ENOUGH_TIME", None
    elif shortfall <= 0:
        status, start_by = "READY", None
    else:
        start_by = trip.departure - timedelta(hours=charge_hours, minutes=mins)
        status = "CHARGE_NEEDED" if start_by >= now else "NOT_ENOUGH_TIME"
    return TripPlan(trip, current_soc, pack_kwh, wh, drive, pre, reserve,
                    required, shortfall, charge_hours, mins, start_by, status)


def trip_brief(trips: list[Trip], now: datetime) -> str:
    upcoming = sorted((t for t in trips if t.departure > now),
                      key=lambda t: t.departure)
    if not upcoming:
        return "No upcoming trips on the calendar."
    lines = ["Upcoming trips:"]
    for t in upcoming[:10]:
        temp = f", {t.destination_temp_f:.0f}F at destination" if t.destination_temp_f is not None else ""
        lines.append(f"  - {t.title} -> {t.destination}, "
                     f"departs {t.departure.strftime('%a %b %d, %I:%M %p')}, "
                     f"{t.distance_miles:.0f} miles{temp}.")
    return "\n".join(lines)


def _unfold(text: str) -> list[str]:
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


_DT_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z)?$")


def _parse_dt(value: str, params: str) -> datetime | None:
    value = value.strip()
    m = _DT_RE.match(value)
    if not m:
        dm = re.match(r"^(\d{4})(\d{2})(\d{2})$", value)
        if not dm:
            return None
        return datetime(int(dm.group(1)), int(dm.group(2)), int(dm.group(3)),
                        9, 0, tzinfo=timezone.utc)
    y, mo, d, h, mi, s = (int(m.group(i)) for i in range(1, 7))
    if m.group(7):
        return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)
    tzid = None
    for part in params.split(";"):
        if part.startswith("TZID="):
            tzid = part[5:].strip('"')
    if tzid:
        try:
            return datetime(y, mo, d, h, mi, s, tzinfo=ZoneInfo(tzid))
        except Exception:
            pass
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc)


def parse_ics(text: str) -> list[Trip]:
    """Parse VEVENTs: SUMMARY, LOCATION, DTSTART, DESCRIPTION distance.

    Distance is read from DESCRIPTION like 'distance: 120 mi' or from
    X-TRIP-DISTANCE-MILES; events without a distance are skipped (a
    calendar title alone cannot size a charge plan).
    """
    trips: list[Trip] = []
    event: dict = {}
    in_event = False
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            in_event, event = True, {}
            continue
        if line == "END:VEVENT":
            in_event = False
            summary = event.get("SUMMARY", "Trip")
            location = event.get("LOCATION", "")
            dep = event.get("_departure")
            dist = event.get("_distance")
            if dep is not None and dist is not None:
                trips.append(Trip(title=summary, destination=location or summary,
                                  departure=dep, distance_miles=dist,
                                  destination_temp_f=event.get("_temp")))
            event = {}
            continue
        if not in_event or ":" not in line:
            continue
        key_params, value = line.split(":", 1)
        parts = key_params.split(";")
        key, params = parts[0], ";".join(parts[1:])
        if key == "DTSTART":
            event["_departure"] = _parse_dt(value, params)
        elif key == "SUMMARY":
            event["SUMMARY"] = value.strip()
        elif key == "LOCATION":
            event["LOCATION"] = value.strip()
        elif key == "X-TRIP-DISTANCE-MILES":
            try:
                event["_distance"] = float(value.strip())
            except ValueError:
                pass
        elif key == "DESCRIPTION":
            m = re.search(r"distance:\s*([\d.]+)\s*mi", value, re.I)
            if m:
                event["_distance"] = float(m.group(1))
            m2 = re.search(r"temp(?:erature)?:\s*(-?[\d.]+)\s*F", value, re.I)
            if m2:
                event["_temp"] = float(m2.group(1))
    return trips


def load_trips(calendar_file: str) -> list[Trip]:
    from pathlib import Path
    p = Path(calendar_file).expanduser()
    if not p.exists():
        return []
    try:
        return parse_ics(p.read_text())
    except OSError:
        return []
