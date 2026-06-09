from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class LLMClient(Protocol):
    """The one interface every agent depends on. Implementations: MockLLMClient
    (offline) and VLLMClient (OpenAI-compatible -> MI300X). Agents never import
    a concrete client; they receive one. This is what lets the whole pipeline
    run with no GPU."""

    def generate(self, *, system: str, user: str, output_model: type[T]) -> T:
        ...
