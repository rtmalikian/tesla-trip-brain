"""End-to-end: the demo Big Bear plan needs charging with a start-by
before departure, the Palm Springs plan is READY, and the HTTP server
answers a readiness question live."""
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer

import requests

from tesla_trip_brain.config import load_settings
from tesla_trip_brain.server import make_handler
from tesla_trip_brain.service import TripBrainService
from tesla_trip_brain.simulator import DEMO_SOC, demo_trips
from tesla_trip_brain.trip import plan_trip

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_demo_invariant():
    settings = load_settings({"TTB_AI_MODE": "never"})
    trips = demo_trips(NOW)
    big_bear, palm, vegas = trips
    bb = plan_trip(big_bear, DEMO_SOC, NOW, pack_kwh=settings.pack_kwh,
                   reserve_pct=settings.reserve_pct,
                   charger_kw=settings.charger_kw)
    assert bb.status == "CHARGE_NEEDED"
    assert bb.start_charging_by < big_bear.departure
    ps = plan_trip(palm, DEMO_SOC, NOW, pack_kwh=settings.pack_kwh,
                   reserve_pct=settings.reserve_pct,
                   charger_kw=settings.charger_kw)
    assert ps.status == "READY"
    vg = plan_trip(vegas, DEMO_SOC, NOW, pack_kwh=settings.pack_kwh,
                   reserve_pct=settings.reserve_pct,
                   charger_kw=settings.charger_kw)
    assert vg.status == "NOT_ENOUGH_TIME"


def test_http_server_answers_live():
    settings = load_settings({"TTB_AI_MODE": "never"})
    settings.server_port = 0
    trips = demo_trips(NOW)
    service = TripBrainService(settings, trips_provider=lambda: trips,
                               soc_provider=lambda: DEMO_SOC, now=NOW)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        r = requests.get(f"http://127.0.0.1:{port}/v1/models", timeout=5)
        assert r.status_code == 200
        assert r.json()["data"][0]["id"] == "tesla-trip-brain"
        r = requests.post(f"http://127.0.0.1:{port}/v1/chat/completions",
                          json={"messages": [{"role": "user", "content":
                                              "am I ready for tomorrow's drive to Big Bear?"}]},
                          timeout=5)
        assert r.status_code == 200
        assert "Big Bear" in r.json()["choices"][0]["message"]["content"]
    finally:
        httpd.shutdown()
        httpd.server_close()
