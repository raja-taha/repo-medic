from __future__ import annotations

import json
import re
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from repomedic_core.config import get_settings
from repomedic_core.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T", bound=BaseModel)


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                api_key=self.settings.openai_api_key or "sk-placeholder",
                base_url=self.settings.openai_base_url,
            )
        return self._client

    @property
    def available(self) -> bool:
        if self.settings.synthetic_mode:
            return False
        key = (self.settings.openai_api_key or "").strip()
        if not key:
            return False
        if key.startswith("sk-your-") or "change-me" in key.lower() or "placeholder" in key.lower():
            return False
        return True

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[T],
        *,
        max_tokens: int | None = None,
        retries: int = 2,
    ) -> T:
        if not self.available:
            raise RuntimeError("LLM unavailable: set OPENAI_API_KEY or disable SYNTHETIC_MODE")

        token_budget = max_tokens or self.settings.llm_max_tokens
        last_error: Exception | None = None
        messages = [
            {
                "role": "system",
                "content": (
                    f"{system}\n\n"
                    "Respond with a single compact JSON object matching this schema. "
                    "Keep string values short. Prefer search/replace snippets over full files.\n"
                    f"{json.dumps(schema.model_json_schema(), indent=2)}"
                ),
            },
            {"role": "user", "content": user},
        ]

        for attempt in range(retries + 1):
            response = self.client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=self.settings.llm_temperature,
                max_tokens=token_budget,
                response_format={"type": "json_object"},
                messages=messages,
            )
            content = response.choices[0].message.content or "{}"
            finish = response.choices[0].finish_reason
            try:
                return schema.model_validate(_parse_json_object(content))
            except (ValidationError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "llm_json_parse_failed",
                    attempt=attempt,
                    finish_reason=finish,
                    error=str(exc),
                    content_len=len(content),
                )
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous reply was invalid or truncated JSON. "
                            "Return ONLY a complete, valid JSON object. "
                            "Use small old_str/new_str edits — never paste entire large files. "
                            f"Parse error: {exc}"
                        ),
                    }
                )
                # Give a bit more room on retry if we hit length
                if finish == "length":
                    token_budget = min(token_budget * 2, 16_384)

        raise RuntimeError(f"LLM returned invalid JSON after retries: {last_error}")

    def complete_text(self, system: str, user: str) -> str:
        if not self.available:
            raise RuntimeError("LLM unavailable")
        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""


def _parse_json_object(content: str) -> dict:
    text = content.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # Extract outermost object if model wrapped extra text
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if match:
        data = json.loads(match.group(0))
        if isinstance(data, dict):
            return data
    raise json.JSONDecodeError("Could not parse JSON object", text, 0)


def heuristic_checklist(title: str, body: str, language: str = "python") -> dict:
    """Deterministic fallback when LLM keys are missing (synthetic / offline mode)."""
    lines = [ln.strip("-* •\t ") for ln in (body or "").splitlines() if ln.strip()]
    criteria = []
    for idx, line in enumerate(lines[:8], start=1):
        if any(
            key in line.lower()
            for key in ("should", "must", "expect", "fix", "bug", "error", "return", "when")
        ):
            criteria.append({"id": f"AC-{idx}", "text": line, "verified": False})
    if not criteria:
        criteria = [
            {
                "id": "AC-1",
                "text": f"Reproduce and fix the issue described in: {title}",
                "verified": False,
            },
            {
                "id": "AC-2",
                "text": "Add or update tests that fail before the fix and pass after",
                "verified": False,
            },
            {
                "id": "AC-3",
                "text": "Ensure lint/type checks still pass on changed files",
                "verified": False,
            },
        ]
    return {
        "criteria": criteria,
        "reproduction_hint": "Run the project's test suite after applying the fix",
        "language": language,
    }
