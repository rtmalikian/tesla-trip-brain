"""Transport-independent service: OpenAI-shaped requests in,
OpenAI-shaped responses out. The HTTP server is a thin wrapper;
tests drive this class directly.

Flow: rules engine answers readiness questions from the computed
trip plans (no AI needed — "am I ready for tomorrow's drive to
Big Bear?"). If rules don't match and ai_mode is auto|always, the
LLM backend gets the trip brief as context and explains; it never
invents a SoC figure — numbers come from the trip math. Otherwise
the capability blurb. This app never wakes or commands a car and
never executes LLM-emitted text as a command.
"""
from __future__ import annotations

import itertools
import re
import time
from datetime import datetime, timezone

from .embeddings import embed_text
from .llm import LlmBackend
from .trip import Trip, plan_trip, trip_brief

CAPABILITY_BLURB = (
    "I check whether your Tesla is ready for tomorrow's trip: I read "
    "your calendar trips, work out the battery % you need to leave "
    "with (drive energy + reserve + preconditioning), and tell you "
    "when to start charging. Try: \"am I ready for tomorrow's drive "
    "to Big Bear?\", \"what trips are coming up?\" or \"plan my trip "
    "to Palm Springs\". Connect an LLM backend (TTB_AI_BASE_URL) and "
    "I can explain in free-form words too. I never wake or control "
    "a car — I only plan from your calendar and your battery %."
)


class TripBrainService:
    def __init__(self, settings, trips_provider=None, soc_provider=None,
                 llm_factory=None, now=None):
        self.settings = settings
        self.trips_provider = trips_provider or (lambda: [])
        self.soc_provider = soc_provider or (lambda: 70.0)
        self.llm_factory = llm_factory
        self._now = now
        self._ids = itertools.count(1)

    def _now_dt(self):
        return self._now or datetime.now(timezone.utc)

    def _llm(self):
        if self.llm_factory is not None:
            return self.llm_factory()
        if self.settings.ai_mode == "never" or not self.settings.ai_base_url:
            return None
        return LlmBackend(self.settings.ai_base_url, self.settings.ai_api_key,
                          self.settings.ai_model, self.settings.ai_timeout_seconds)

    def _next_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time())}-{next(self._ids)}"

    def models_list(self) -> dict:
        return {"object": "list", "data": [{
            "id": self.settings.model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "tesla-trip-brain",
        }]}

    def chat_completions(self, body: dict) -> dict:
        messages = body.get("messages") or []
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = str(m.get("content") or "")
                break
        trips = self.trips_provider()
        text = self._rules_answer(user_text, trips)
        if text is None:
            text = self._llm_answer(user_text, trips)
        return {
            "id": self._next_id("chatcmpl"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": self.settings.model_id,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }

    def embeddings(self, body: dict) -> dict:
        raw = body.get("input", "")
        texts = raw if isinstance(raw, list) else [raw]
        data = []
        for i, t in enumerate(texts):
            data.append({
                "object": "embedding",
                "index": i,
                "embedding": embed_text(str(t), self.settings.embedding_dim),
            })
        return {"object": "list", "data": data, "model": self.settings.model_id,
                "usage": {"prompt_tokens": 0, "total_tokens": 0}}

    def _plan(self, trip: Trip) -> str:
        plan = plan_trip(trip, self.soc_provider(), self._now_dt(),
                         pack_kwh=self.settings.pack_kwh,
                         reserve_pct=self.settings.reserve_pct,
                         charger_kw=self.settings.charger_kw)
        return plan.summary_line()

    def _rules_answer(self, user_text: str, trips: list) -> str | None:
        q = user_text.lower()
        upcoming = sorted((t for t in trips if t.departure > self._now_dt()),
                          key=lambda t: t.departure)
        if "trip" in q and ("list" in q or "coming" in q or "upcoming" in q
                            or "what" in q):
            return trip_brief(trips, self._now_dt())
        if not upcoming:
            return None
        # Match a named destination/title, else the next trip.
        target = None
        for t in upcoming:
            hay = f"{t.destination} {t.title}".lower()
            words = [w for w in re.split(r"[^a-z]+", q) if len(w) >= 3]
            if any(w in hay for w in words if w not in ("ready", "tomorrow", "drive", "trip", "plan", "leave", "going")):
                target = t
                break
        if target is None and ("ready" in q or "plan" in q or "tomorrow" in q):
            target = upcoming[0]
        if target is not None:
            return self._plan(target)
        return None

    def _llm_answer(self, user_text: str, trips: list) -> str:
        llm = self._llm()
        if llm is None:
            return CAPABILITY_BLURB
        try:
            return llm.chat(trip_brief(trips, self._now_dt()), user_text)
        except Exception:
            return CAPABILITY_BLURB + " (The AI backend didn't respond just now.)"
