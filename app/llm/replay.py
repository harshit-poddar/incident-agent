from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from app.llm.base import LLMClient

T = TypeVar("T", bound=BaseModel)


def fixture_key(system: str, user: str) -> str:
    """Stable short hash of a prompt pair -- identifies one specific call."""
    digest = hashlib.sha256(f"{system}\x00{user}".encode("utf-8")).hexdigest()
    return digest[:12]


def fixture_path(out_dir: Path, model_name: str, key: str) -> Path:
    return out_dir / f"{model_name}.{key}.json"


class RecordingLLMClient:
    """Wraps a real LLMClient and writes every (prompt -> structured response)
    pair into `out_dir` as a JSON fixture. Run this against the live MI300X once
    (one person, one GPU session); the captured fixtures then drive
    MODEL_MODE=replay for everyone else with no GPU."""

    def __init__(self, inner: LLMClient, out_dir: Path | str) -> None:
        self._inner = inner
        self._out_dir = Path(out_dir)
        self._out_dir.mkdir(parents=True, exist_ok=True)
        self.captured: list[Path] = []

    def generate(self, *, system: str, user: str, output_model: type[T]) -> T:
        result = self._inner.generate(system=system, user=user, output_model=output_model)
        key = fixture_key(system, user)
        payload = {
            "output_model": output_model.__name__,
            "key": key,
            "system": system,
            "user": user,
            "response": result.model_dump(mode="json"),
        }
        path = fixture_path(self._out_dir, output_model.__name__, key)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.captured.append(path)
        return result


class ReplayLLMClient:
    """Serves recorded fixtures instead of calling a model -- deterministic and
    GPU-free, the dev/demo default once fixtures exist.

    Matching is two-tier: an exact (output_model, prompt-hash) lookup first, then
    a lenient fallback to any fixture for the same output_model. The fallback
    keeps the demo running when a prompt drifts (e.g. a timestamp baked into the
    user message), which would otherwise change the hash on every run."""

    def __init__(self, fixtures_dir: Path | str) -> None:
        self._dir = Path(fixtures_dir)
        self._exact: dict[tuple[str, str], dict] = {}
        self._by_model: dict[str, list[dict]] = {}
        self._load()

    def _load(self) -> None:
        if not self._dir.is_dir():
            raise FileNotFoundError(
                f"No fixtures dir at {self._dir}. Capture some first:\n"
                "  python scripts/capture_fixtures.py --from-mock"
            )
        for path in sorted(self._dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            model = data["output_model"]
            self._exact[(model, data["key"])] = data
            self._by_model.setdefault(model, []).append(data)
        if not self._exact:
            raise FileNotFoundError(
                f"Fixtures dir {self._dir} is empty. Capture some first:\n"
                "  python scripts/capture_fixtures.py --from-mock"
            )

    def generate(self, *, system: str, user: str, output_model: type[T]) -> T:
        model = output_model.__name__
        data = self._exact.get((model, fixture_key(system, user)))
        if data is None:
            candidates = self._by_model.get(model)
            if not candidates:
                raise KeyError(
                    f"No replay fixture for {model!r}. Re-capture with "
                    "scripts/capture_fixtures.py."
                )
            data = candidates[0]  # lenient fallback: prompt drifted from capture
        return output_model.model_validate(data["response"])
