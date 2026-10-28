"""Trip-readiness math: required SoC, cold uplift, edge cases, ICS."""
from datetime import datetime, timedelta, timezone

import pytest

from tesla_trip_brain.trip import (Trip, parse_ics, plan_trip,
                                   weather_factor)

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def _trip(miles=100.0, temp=None, hours=24):
    return Trip("Test", "Somewhere", NOW + timedelta(hours=hours),
                miles, destination_temp_f=temp)


def test_mild_trip_ready_and_math():
    plan = plan_trip(_trip(100.0), 80.0, NOW)
    # 100 mi * 280 Wh/mi = 28 kWh + 0.5 precondition + 7.5 reserve = 36 kWh = 48%
    assert plan.drive_kwh == pytest.approx(28.0)
    assert plan.required_soc == pytest.approx(48.0)
    assert plan.status == "READY"


def test_cold_uplift_raises_requirement():
    mild = plan_trip(_trip(120.0, temp=70.0), 62.0, NOW)
    cold = plan_trip(_trip(120.0, temp=32.0), 62.0, NOW)
    assert cold.wh_per_mile == pytest.approx(280 * 1.15)
    assert cold.required_soc > mild.required_soc
    assert cold.precondition_minutes == 30
    assert cold.required_soc == pytest.approx((120 * 0.322 + 2.0 + 7.5) / 75 * 100, abs=0.5)


def test_charge_needed_start_by_before_departure():
    plan = plan_trip(_trip(120.0, temp=32.0), 62.0, NOW)
    assert plan.status == "CHARGE_NEEDED"
    assert plan.start_charging_by is not None
    assert plan.start_charging_by < plan.trip.departure
    assert plan.start_charging_by >= NOW


def test_not_enough_time_when_departure_too_soon():
    plan = plan_trip(_trip(120.0, temp=32.0, hours=0.5), 62.0, NOW)
    assert plan.status == "NOT_ENOUGH_TIME"


def test_impossible_trip_beyond_full_battery():
    plan = plan_trip(_trip(400.0), 100.0, NOW)
    assert plan.status == "NOT_ENOUGH_TIME"
    assert plan.required_soc > 100


def test_zero_mile_trip_only_needs_reserve_and_precondition():
    plan = plan_trip(_trip(0.0), 20.0, NOW)
    assert plan.status == "READY"
    assert plan.drive_kwh == 0.0


def test_departed_and_bad_inputs():
    plan = plan_trip(_trip(100.0, hours=-1), 80.0, NOW)
    assert plan.status == "DEPARTED"
    with pytest.raises(ValueError):
        plan_trip(_trip(100.0), 120.0, NOW)
    with pytest.raises(ValueError):
        plan_trip(_trip(-5.0), 80.0, NOW)


def test_weather_factor_boundaries():
    assert weather_factor(None) == 1.0
    assert weather_factor(19.9) == 1.25
    assert weather_factor(39.9) == 1.15
    assert weather_factor(40.0) == 1.0
    assert weather_factor(96.0) == 1.10


def test_parse_ics_reads_distance_and_temp():
    ics = """BEGIN:VCALENDAR
BEGIN:VEVENT
SUMMARY:Ski weekend
LOCATION:Big Bear
DTSTART:20261029T160000Z
DESCRIPTION:distance: 120 mi, temperature: 32F
END:VEVENT
BEGIN:VEVENT
SUMMARY:No distance lunch
LOCATION:Downtown
DTSTART:20261030T170000Z
END:VEVENT
END:VCALENDAR
"""
    trips = parse_ics(ics)
    assert len(trips) == 1  # the distance-less event is skipped, by design
    assert trips[0].destination == "Big Bear"
    assert trips[0].distance_miles == 120.0
    assert trips[0].destination_temp_f == 32.0
