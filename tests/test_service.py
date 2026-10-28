"""OpenAI response shapes + trip-readiness Q&A rules. The rules engine
must answer readiness questions with computed plans, never invented numbers."""
from datetime import datetime, timezone

from tesla_trip_brain.config import load_settings
from tesla_trip_brain.service import TripBrainService
from tesla_trip_brain.simulator import DEMO_SOC, demo_trips


def _service():
    settings = load_settings({"TTB_VEHICLES": "Model Y=VINY",
                              "TTB_AI_MODE": "never"})
    now = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)
    trips = demo_trips(now)
    return TripBrainService(settings, trips_provider=lambda: trips,
                            soc_provider=lambda: DEMO_SOC, now=now)


def _ask(service, question):
    resp = service.chat_completions(
        {"model": "tesla-trip-brain",
         "messages": [{"role": "user", "content": question}]})
    assert resp["object"] == "chat.completion"
    assert resp["model"] == "tesla-trip-brain"
    assert resp["choices"][0]["message"]["role"] == "assistant"
    assert resp["choices"][0]["finish_reason"] == "stop"
    return resp["choices"][0]["message"]["content"]


def test_models_shape():
    models = _service().models_list()
    assert models["object"] == "list"
    assert models["data"][0]["id"] == "tesla-trip-brain"


def test_ready_question_for_big_bear():
    answer = _ask(_service(), "am I ready for tomorrow's drive to Big Bear?")
    assert "Big Bear" in answer
    assert "Not ready yet" in answer
    assert "Start charging by" in answer


def test_next_trip_without_destination():
    answer = _ask(_service(), "am I ready for tomorrow's trip?")
    assert "Big Bear" in answer


def test_trip_list_answer():
    answer = _ask(_service(), "what trips are coming up?")
    assert "Big Bear" in answer
    assert "Palm Springs" in answer
    assert "Las Vegas" in answer


def test_embeddings_shape_and_determinism():
    service = _service()
    resp = service.embeddings({"input": "Big Bear ski trip 120 miles"})
    assert resp["object"] == "list"
    assert len(resp["data"][0]["embedding"]) == 384
    again = service.embeddings({"input": "Big Bear ski trip 120 miles"})
    assert again["data"][0]["embedding"] == resp["data"][0]["embedding"]


def test_unknown_question_falls_back_to_capability_blurb():
    answer = _ask(_service(), "tell me a joke about Mars")
    assert "am I ready for tomorrow's drive" in answer
