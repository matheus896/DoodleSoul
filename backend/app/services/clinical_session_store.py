"""In-memory clinical session store — singleton, following session_grounding_store.py pattern.

Stores clinical alerts, structured payloads, and therapist-facing summaries
per session. Designed for retrieval via the therapist endpoint
GET /api/dashboard/insights/{session_id}.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class ClinicalSessionState:
    alerts: list[dict] = field(default_factory=list)
    payloads: list[dict] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)
    transcript_snapshots: list[dict] = field(default_factory=list)
    emotional_state_current: str = "calm"


class ClinicalSessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ClinicalSessionState] = {}

    def register_session(self, session_id: str) -> None:
        self._sessions.setdefault(session_id, ClinicalSessionState())

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def add_alert(self, session_id: str, alert: dict) -> None:
        self.register_session(session_id)
        self._sessions[session_id].alerts.append(dict(alert))

    def add_payload(self, session_id: str, payload: dict) -> None:
        self.register_session(session_id)
        self._sessions[session_id].payloads.append(dict(payload))

    def add_summary(self, session_id: str, summary: str) -> None:
        self.register_session(session_id)
        self._sessions[session_id].summaries.append(str(summary))

    def set_emotional_state(self, session_id: str, state: str) -> None:
        self.register_session(session_id)
        self._sessions[session_id].emotional_state_current = str(state)

    def get_alerts(self, session_id: str) -> list[dict]:
        state = self._sessions.get(session_id)
        if state is None:
            return []
        return list(state.alerts)

    def get_insights(self, session_id: str) -> dict:
        state = self._sessions.get(session_id)
        if state is None:
            return {"session_id": session_id, "alerts": [], "payloads": [], "summaries": [], "emotional_state_current": "calm"}
        return {
            "session_id": session_id,
            "alerts": list(state.alerts),
            "payloads": list(state.payloads),
            "summaries": list(state.summaries),
            "emotional_state_current": state.emotional_state_current,
        }


_CLINICAL_SESSION_STORE = ClinicalSessionStore()


def get_clinical_session_store() -> ClinicalSessionStore:
    return _CLINICAL_SESSION_STORE
