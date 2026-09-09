"""
bi/data/agent_executor.py
-------------------------
Query executor that fetches data by running ADK agents.

Each agent is invoked via ``run_adk_agent()`` (HTTP POST to the ADK server).
The text response is parsed as JSON rows and concatenated across all requested
agents.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import timedelta
from typing import Any

import aiohttp

from apowerb.bi.charts.core import DataSource
from apowerb.configs.settings import get_settings
from apowerb.core.agent_main import get_agent_by_id, get_agent_folder_name
from apowerb.helpers.security import create_access_token

settings = get_settings()

logger = logging.getLogger(__name__)


class AgentQueryExecutor:
    """Runs one or more ADK agents and collects their output as data rows."""

    def __init__(self, user_id: str, token: str | None = None) -> None:
        self._user_id = user_id
        self._token = token or self._internal_token(user_id)

    @staticmethod
    def _internal_token(user_email: str) -> str:
        return create_access_token(
            data={"sub": user_email, "type": "access"},
            expires_delta=timedelta(minutes=30),
        )

    async def run(self, source: DataSource) -> list[dict[str, Any]]:
        agent_ids: list[int | str] = source.source_options.get("agent_ids", [])
        if not agent_ids:
            logger.warning("[AGENT_EXECUTOR] No agent_ids in source_options — returning empty")
            return []

        all_rows: list[dict[str, Any]] = []

        for aid in agent_ids:
            agent_info = get_agent_by_id(str(aid), self._user_id)
            if not agent_info:
                logger.warning("[AGENT_EXECUTOR] Agent %s not found for user %s — skipping", aid, self._user_id)
                continue

            agent_name = get_agent_folder_name(agent_info["agent_name"])
            session_id = f"bi-agent-{uuid.uuid4().hex[:12]}"
            message_text = self._message_for(source)
            new_message = {"role": "user", "parts": [{"text": message_text}]}

            try:
                url = f"{settings.root_path}/api/adk/run"
                payload = {
                    "agent_name": agent_name,
                    "user_id": self._user_id,
                    "session_id": session_id,
                    "new_message": new_message,
                    "run_mode": "run",
                    "streaming": False,
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._token}",
                }
                # Bounded total timeout: a hung agent must fail fast, not
                # freeze the dashboard for 15 minutes (was total=None).
                _total = int(os.getenv("BI_AGENT_TIMEOUT_S", "120"))
                timeout = aiohttp.ClientTimeout(
                    total=_total, connect=15, sock_read=_total
                )
                async with aiohttp.ClientSession(timeout=timeout) as http:
                    async with http.post(url, json=payload, headers=headers) as resp:
                        resp.raise_for_status()
                        result = await resp.json()
            except Exception:
                logger.exception("[AGENT_EXECUTOR] run_adk_agent failed for agent %s", aid)
                continue

            logger.info("[AGENT_EXECUTOR] Raw result type=%s, preview=%s", type(result).__name__, str(result)[:500])
            rows = self._parse_response(result, agent_name=agent_name)
            all_rows.extend(rows)

        return all_rows

    # An agent chart with no instruction is asked for "the latest data" and
    # nothing else -- a question no agent can answer. Stating the output
    # contract at least makes the failure the user's to fix, not a mystery.
    _FALLBACK_MESSAGE = (
        "Reply with ONLY a JSON array of objects -- no prose, no explanation, "
        "no code fence. Each object is one row of the data this chart shows."
    )

    @classmethod
    def _message_for(cls, source: DataSource) -> str:
        """What to ask the agent: the chart's own instruction, or the contract."""
        message = source.source_options.get("message") or source.query
        return message.strip() if isinstance(message, str) and message.strip() else cls._FALLBACK_MESSAGE

    @staticmethod
    def _answer_texts(result: Any) -> tuple[list[str], list[str]]:
        """Candidate answer texts, most recent first, reasoning excluded.

        ADK returns a list of events; a Gemini 2.5 event holds its reasoning
        summary in parts flagged ``thought`` and the actual answer in a plain
        part. Reading the first part with text hands back the monologue --
        that is the 08/09 bug. ``routers/adk_runner.get_session_history``
        already makes this distinction; this path had not.
        """
        texts: list[str] = []
        thoughts: list[str] = []

        def push(into: list[str], value: Any) -> None:
            if isinstance(value, str) and value.strip():
                into.append(value)

        if isinstance(result, list):
            for event in reversed(result):
                if not isinstance(event, dict):
                    continue
                content = event.get("content")
                parts = content.get("parts", []) if isinstance(content, dict) else []
                answer = ""
                for part in parts:
                    if not isinstance(part, dict) or not isinstance(part.get("text"), str):
                        continue
                    if part.get("thought"):
                        push(thoughts, part["text"])
                    else:
                        answer += part["text"]
                push(texts, answer)
                push(texts, event.get("response"))
                push(texts, event.get("text"))
        elif isinstance(result, dict):
            push(texts, result.get("response"))
            push(texts, result.get("text"))
        elif result:
            push(texts, str(result))

        return texts, thoughts

    @staticmethod
    def _rows_from_text(text: str) -> list[dict[str, Any]] | None:
        """JSON rows carried by one answer, bare or inside a code fence."""

        def coerce(raw: str) -> list[dict[str, Any]] | None:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
            if isinstance(data, list):
                return [r for r in data if isinstance(r, dict)]
            if isinstance(data, dict):
                return [data]
            return None

        rows = coerce(text)
        if rows is not None:
            return rows

        for marker in ("```json", "```"):
            if marker in text:
                start = text.index(marker) + len(marker)
                end = text.find("```", start)
                if end != -1:
                    rows = coerce(text[start:end].strip())
                    if rows is not None:
                        return rows
        return None

    @classmethod
    def _parse_response(cls, result: Any, agent_name: str | None = None) -> list[dict[str, Any]]:
        """Extract JSON rows from the agent response text."""
        texts, thoughts = cls._answer_texts(result)
        if not texts and not thoughts:
            return []

        for text in texts:
            rows = cls._rows_from_text(text)
            if rows is not None:
                return rows

        # Text was present but no JSON rows could be extracted. Returning []
        # here would render an empty chart with no explanation (the prior
        # silent-failure symptom). Surface it so the service maps it to 502 --
        # and say what the reader can actually change. Reasoning alone counts
        # as "the model spoke": it is reported, never swallowed.
        preview = (texts or thoughts)[0][:300]
        who = f"Agent {agent_name!r}" if agent_name else "The agent"
        logger.warning(
            "[AGENT_EXECUTOR] Could not parse agent response as JSON rows (agent=%s); preview=%s",
            agent_name, preview,
        )
        raise ValueError(
            f"{who} answered with text instead of data rows. An agent chart needs an "
            "instruction saying what to return: set it on the chart's data source "
            "(source_options.message). Answer preview: " + repr(preview)
        )
