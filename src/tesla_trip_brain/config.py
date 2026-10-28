"""Configuration for Tesla Trip Brain. All settings come from the
environment (see .env.example). Copy .env.example to .env — .env is
git-ignored so secrets never leave your machine.

Times are written the way owners say them ("4:00 PM"), never as
24-hour numbers. The setup wizard writes this file for you — nobody
hand-edits it.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field


class ConfigError(Exception):
    pass


@dataclass
class VehicleConfig:
    name: str
    vin: str


@dataclass
class Settings:
    client_id: str = ""
    client_secret: str = ""
    region: str = "na"
    redirect_uri: str = "http://localhost:8080/callback"
    token_file: str = "~/.ttb/tokens.json"
    vehicles: list[VehicleConfig] = field(default_factory=list)
    # The OpenAI-compatible server this app exposes.
    server_host: str = "127.0.0.1"
    server_port: int = 8651
    server_api_key: str = ""          # optional bearer token for /v1/*
    model_id: str = "tesla-trip-brain"
    # Pluggable LLM backend (any OpenAI-compatible API; default: local Ollama).
    ai_base_url: str = "http://localhost:11434/v1"
    ai_api_key: str = ""
    ai_model: str = "llama3.1"
    ai_mode: str = "auto"             # auto | always | never
    ai_timeout_seconds: float = 20.0
    embedding_dim: int = 384
    dry_run: bool = False
    # Trip-plan defaults (the common answers; setup writes them).
    pack_kwh: float = 75.0
    reserve_pct: float = 10.0
    charger_kw: float = 11.5
    cold_threshold_f: float = 40.0
    calendar_file: str = "~/.ttb/trips.ics"
    data_file: str = "~/.ttb/trips.ics"


def _parse_vehicles(raw: str) -> list[VehicleConfig]:
    """Format: name=VIN,name2=VIN2 (or bare VINs)."""
    vehicles = []
    for idx, item in enumerate(raw.split(",")):
        item = item.strip()
        if not item:
            continue
        name = None
        if "=" in item:
            name, item = item.split("=", 1)
            name = name.strip()
        vin = item.strip()
        if not vin:
            raise ConfigError("Empty VIN in TTB_VEHICLES")
        vehicles.append(VehicleConfig(name=name or f"car-{idx + 1}", vin=vin))
    if not vehicles:
        raise ConfigError("TTB_VEHICLES is empty — add at least one name=VIN entry")
    return vehicles


def parse_12h_time(raw: str) -> int:
    """'4:00 PM' -> minutes after midnight. Raises ConfigError on bad input."""
    m = re.match(r"^\s*(\d{1,2})\s*:\s*(\d{2})\s*([APap][Mm])\s*$", raw or "")
    if not m:
        raise ConfigError(
            f"Time must look like '4:00 PM', got {raw!r}. "
            "Write the hour, a colon, the minutes, and AM or PM.")
    hour, minute, meridiem = int(m.group(1)), int(m.group(2)), m.group(3).upper()
    if not (1 <= hour <= 12) or not (0 <= minute <= 59):
        raise ConfigError(f"Not a real clock time: {raw!r}")
    if meridiem == "PM" and hour != 12:
        hour += 12
    if meridiem == "AM" and hour == 12:
        hour = 0
    return hour * 60 + minute


def format_12h_time(minutes: int) -> str:
    minutes %= 24 * 60
    hour, minute = divmod(minutes, 60)
    meridiem = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {meridiem}"


def _int(env: dict, key: str, default: int) -> int:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a whole number, got {raw!r}") from exc


def _float(env: dict, key: str, default: float) -> float:
    raw = env.get(key)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(raw)
    except (ValueError, TypeError) as exc:
        raise ConfigError(f"{key} must be a number, got {raw!r}") from exc


def _bool(env: dict, key: str, default: bool = False) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def load_settings(env: dict | None = None) -> Settings:
    env = os.environ if env is None else env
    s = Settings()
    s.client_id = env.get("TESLA_CLIENT_ID", "")
    s.client_secret = env.get("TESLA_CLIENT_SECRET", "")
    s.region = env.get("TESLA_REGION", "na").strip().lower()
    if s.region not in ("na", "eu", "cn"):
        raise ConfigError(f"TESLA_REGION must be na|eu|cn, got {s.region!r}")
    s.redirect_uri = env.get("TESLA_REDIRECT_URI", s.redirect_uri)
    s.token_file = env.get("TTB_TOKEN_FILE", s.token_file)
    raw_vehicles = env.get("TTB_VEHICLES", "")
    if raw_vehicles.strip():
        s.vehicles = _parse_vehicles(raw_vehicles)
    s.server_host = env.get("TTB_SERVER_HOST", s.server_host)
    s.server_port = _int(env, "TTB_SERVER_PORT", s.server_port)
    s.server_api_key = env.get("TTB_SERVER_API_KEY", "")
    s.model_id = env.get("TTB_MODEL_ID", s.model_id)
    s.ai_base_url = env.get("TTB_AI_BASE_URL", s.ai_base_url).rstrip("/")
    s.ai_api_key = env.get("TTB_AI_API_KEY", "")
    s.ai_model = env.get("TTB_AI_MODEL", s.ai_model)
    s.ai_mode = env.get("TTB_AI_MODE", s.ai_mode).strip().lower()
    if s.ai_mode not in ("auto", "always", "never"):
        raise ConfigError(f"TTB_AI_MODE must be auto|always|never, got {s.ai_mode!r}")
    s.ai_timeout_seconds = _float(env, "TTB_AI_TIMEOUT_SECONDS", s.ai_timeout_seconds)
    s.embedding_dim = _int(env, "TTB_EMBEDDING_DIM", s.embedding_dim)
    if not (8 <= s.embedding_dim <= 4096):
        raise ConfigError("TTB_EMBEDDING_DIM must be between 8 and 4096")
    s.dry_run = _bool(env, "TTB_DRY_RUN")
    s.pack_kwh = _float(env, "TTB_PACK_KWH", s.pack_kwh)
    s.reserve_pct = _float(env, "TTB_RESERVE_PCT", s.reserve_pct)
    s.charger_kw = _float(env, "TTB_CHARGER_KW", s.charger_kw)
    if not (0 <= s.reserve_pct <= 30):
        raise ConfigError(f"TTB_RESERVE_PCT must be between 0 and 30, got {s.reserve_pct}")
    s.cold_threshold_f = _float(env, "TTB_COLD_THRESHOLD_F", s.cold_threshold_f)
    if not (-20 <= s.cold_threshold_f <= 70):
        raise ConfigError(f"TTB_COLD_THRESHOLD_F must be between -20 and 70, got {s.cold_threshold_f}")
    s.calendar_file = env.get("TTB_CALENDAR_FILE", s.calendar_file)
    s.data_file = env.get("TTB_DATA_FILE", s.data_file)
    return s
