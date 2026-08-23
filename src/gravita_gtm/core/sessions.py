"""Hermes-patterned session layer — conversational, session-based, channel-aware.

The platform is conversational like Hermes: you talk to it in turns, it keeps a
session, it can open channels (workspaces) per workflow, it remembers context
across turns, and it exposes actions as things you can say. Phase 1: a session
manager + a turn buffer that the REPL uses. Later phases: a richer
conversational surface (AG-UI / generative UI) without changing the backend.

Inspire: Hermes sessions, channels, skills, sub-agents — but demand-generation-
specialized. A session is a turn-based conversation with a workspace + channel
+ context that persists across turns.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gravita_gtm.config import STATE_DIR


@dataclass
class Session:
    """One conversational session. A session has an id, a name, a workspace, a
    channel (which workflow it is focused on), and a turn buffer.

    Sessions are the Hermes-patterned piece: conversational, session-based,
    channel-aware. A session is how you talk to the platform: "run signal
    outbound for this week, top 20" is one turn in one session.
    """
    id: str
    name: str
    workspace: str
    channel: str
    created_at: str
    turns: list[dict[str, Any]] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    def add_turn(self, role: str, text: str, result: Any = None) -> None:
        self.turns.append({
            "role": role,
            "text": text,
            "result": result,
            "at": datetime.now(timezone.utc).isoformat(),
        })

    def last_turn(self) -> dict[str, Any] | None:
        return self.turns[-1] if self.turns else None


class SessionManager:
    """Manages sessions. Phase 1: an in-memory store with a JSON dump. Later
    phases: a real store, plus a richer conversational surface."""

    def __init__(self, state_dir: Path = STATE_DIR) -> None:
        self._sessions: dict[str, Session] = {}
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._load()

    def list(self) -> list[Session]:
        return list(self._sessions.values())

    def create(self, name: str, workspace: str = "default",
               channel: str = "outbound") -> Session:
        session = Session(
            id=f"session-{uuid.uuid4().hex[:10]}",
            name=name,
            workspace=workspace,
            channel=channel,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._sessions[session.id] = session
        self._dump()
        return session

    def get(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def switch(self, session_id: str, channel: str | None = None,
               workspace: str | None = None) -> Session | None:
        s = self._sessions.get(session_id)
        if s is None:
            return None
        if channel is not None:
            s.channel = channel
        if workspace is not None:
            s.workspace = workspace
        self._dump()
        return s

    def delete(self, session_id: str) -> bool:
        if session_id not in self._sessions:
            return False
        del self._sessions[session_id]
        self._dump()
        return True

    def _load(self) -> None:
        p = self._state_dir / "sessions.json"
        if not p.exists():
            return
        data = json.loads(p.read_text(encoding="utf-8"))
        for d in data:
            s = Session(**d)
            self._sessions[s.id] = s

    def _dump(self) -> None:
        data = [s.__dict__ for s in self._sessions.values()]
        p = self._state_dir / "sessions.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
