from __future__ import annotations

import json
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
        return bool(self.settings.openai_api_key) and not self.settings.synthetic_mode

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        if not self.available:
            raise RuntimeError("LLM unavailable: set OPENAI_API_KEY or disable SYNTHETIC_MODE")

        response = self.client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_max_tokens,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"{system}\n\n"
                        "Respond with a single JSON object that matches this schema:\n"
                        f"{json.dumps(schema.model_json_schema(), indent=2)}"
                    ),
                },
                {"role": "user", "content": user},
            ],
        )
        content = response.choices[0].message.content or "{}"
        try:
            return schema.model_validate_json(content)
        except ValidationError:
            # Retry once by wrapping parse
            data = json.loads(content)
            return schema.model_validate(data)

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