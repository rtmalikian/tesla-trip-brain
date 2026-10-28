"""Config parsing: vehicles, 12-hour times, trip defaults, AI mode."""
import pytest

from tesla_trip_brain.config import (ConfigError, format_12h_time,
                                     load_settings, parse_12h_time)


def test_defaults_load():
    s = load_settings({})
    assert s.server_port == 8651
    assert s.pack_kwh == 75.0
    assert s.reserve_pct == 10.0
    assert s.charger_kw == 11.5
    assert s.cold_threshold_f == 40.0
    assert s.ai_mode == "auto"
    assert s.model_id == "tesla-trip-brain"


def test_vehicles_parsed():
    s = load_settings({"TTB_VEHICLES": "Model Y=VINY,Model 3=VIN3"})
    assert [(v.name, v.vin) for v in s.vehicles] == [("Model Y", "VINY"),
                                                     ("Model 3", "VIN3")]


def test_bad_values_rejected():
    with pytest.raises(ConfigError):
        load_settings({"TTB_RESERVE_PCT": "40"})
    with pytest.raises(ConfigError):
        load_settings({"TTB_RESERVE_PCT": "abc"})
    with pytest.raises(ConfigError):
        load_settings({"TTB_COLD_THRESHOLD_F": "100"})
    with pytest.raises(ConfigError):
        load_settings({"TESLA_REGION": "xx"})
    with pytest.raises(ConfigError):
        load_settings({"TTB_AI_MODE": "sometimes"})
    with pytest.raises(ConfigError):
        load_settings({"TTB_EMBEDDING_DIM": "2"})


def test_12h_times():
    assert parse_12h_time("4:00 PM") == 16 * 60
    assert parse_12h_time("12:00 AM") == 0
    assert parse_12h_time("12:30 PM") == 12 * 60 + 30
    assert format_12h_time(16 * 60) == "4:00 PM"
    assert format_12h_time(0) == "12:00 AM"
    with pytest.raises(ConfigError):
        parse_12h_time("16:00")
    with pytest.raises(ConfigError):
        parse_12h_time("13:00 PM")
