"""The setup wizard must produce a config the app can load — no developer
knowledge required from the (scripted) user."""
import os

from tesla_trip_brain.config import load_settings
from tesla_trip_brain.setup import run_setup


def _scripted(answers):
    it = iter(answers)

    def input_fn(prompt=""):
        return next(it)
    return input_fn


def test_wizard_defaults_write_loadable_config(tmp_path):
    env_path = tmp_path / ".env"
    # CID, secret, car, VIN, done, charger, pack, reserve, calendar,
    # AI choice (Ollama), port, server key blank
    answers = ["CID123", "SECRET456", "Model Y", "VINY", "",
               "", "", "", "", "2", "", ""]
    run_setup(input_fn=_scripted(answers), out=lambda *_: None,
              env_path=str(env_path))
    text = env_path.read_text()
    assert "TTB_VEHICLES=Model Y=VINY" in text
    assert "TTB_CHARGER_KW=11.5" in text
    assert "TTB_PACK_KWH=75" in text
    assert "TTB_RESERVE_PCT=10" in text
    assert "TTB_AI_MODE=auto" in text
    env = {}
    for line in text.splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v
    settings = load_settings(env)
    assert settings.charger_kw == 11.5
    assert settings.pack_kwh == 75.0
    assert settings.reserve_pct == 10.0
    assert settings.vehicles[0].name == "Model Y"
    assert oct(os.stat(env_path).st_mode & 0o777) == "0o600"


def test_wizard_custom_values_and_no_ai(tmp_path):
    env_path = tmp_path / ".env"
    answers = ["CID123", "SECRET456", "Model 3", "VIN3", "",
               "7.7", "82", "15", "/tmp/cal.ics", "1", "", ""]
    run_setup(input_fn=_scripted(answers), out=lambda *_: None,
              env_path=str(env_path))
    text = env_path.read_text()
    assert "TTB_CHARGER_KW=7.7" in text
    assert "TTB_PACK_KWH=82" in text
    assert "TTB_RESERVE_PCT=15" in text
    assert "TTB_AI_MODE=never" in text
    assert "TTB_CALENDAR_FILE=/tmp/cal.ics" in text


def test_wizard_keeps_existing_config_when_declined(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("TTB_VEHICLES=Keep=VINKEEP\n")
    run_setup(input_fn=_scripted(["n"]), out=lambda *_: None,
              env_path=str(env_path))
    assert env_path.read_text() == "TTB_VEHICLES=Keep=VINKEEP\n"
