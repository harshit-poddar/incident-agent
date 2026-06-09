from __future__ import annotations

import json
from typing import TypeVar

from pydantic import BaseModel

from app.config import settings

T = TypeVar("T", bound=BaseModel)


class VLLMClient:
    """OpenAI-compatible client targeting MODEL_BASE_URL (vLLM on the MI300X).

    NOTE: for production, migrate agents to pydantic_ai's Agent for native
    tool-calling. This plain client is the dev-time structured-output path and
    keeps the dependency surface small."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        from openai import OpenAI  # lazy import: mock runs need no openai dep

        self._model = model or settings.model_name
        self._client = OpenAI(
            base_url=base_url or settings.model_base_url,
            api_key=api_key or settings.model_api_key,
        )

    def generate(self, *, system: str, user: str, output_model: type[T]) -> T:
        schema = output_model.model_json_schema()
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": system
                    + "\n\nRespond ONLY with JSON matching this schema:\n"
                    + json.dumps(schema),
                },
                {"role": "user", "content": user},
            ],
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or "{}"
        return output_model.model_validate_json(content)
