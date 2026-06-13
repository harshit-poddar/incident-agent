"""Pre-flight health check -- run this BEFORE the live demo.

Reads the active settings (.env) and probes every backend they enable: the
model endpoint, Postgres, qdrant, redis, the MI300X GPU monitor, the
OpenTelemetry collector, and the GitHub API. Prints a green/red board and exits
non-zero if anything that the demo depends on is down -- so you find out at your
desk, not on stage.

    python scripts/preflight.py            # fast checks (no GPU tokens burned)
    python scripts/preflight.py --deep     # also runs one real LLM generate()

Each check is isolated: a failure in one never aborts the others, so you get the
full picture in a single run."""
from __future__ import annotations

import pathlib
import socket
import sys
import time
import traceback

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Windows consoles default to cp1252, which can't encode the ✓/✗ glyphs below.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app.config import settings

# ANSI colours (Windows Terminal / PowerShell 7 support these).
G, R, Y, B, DIM, X = "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"
PASS, FAIL, SKIP, WARN = f"{G}PASS{X}", f"{R}FAIL{X}", f"{DIM}SKIP{X}", f"{Y}WARN{X}"

_results: list[tuple[str, str]] = []  # (status, name) for the final tally


def check(name: str, enabled: bool, fn) -> None:
    """Run one probe. `fn` returns a detail string on success or raises."""
    if not enabled:
        print(f"  {SKIP}  {name:26} {DIM}(disabled in settings){X}")
        _results.append(("skip", name))
        return
    t0 = time.perf_counter()
    try:
        detail = fn() or ""
        ms = (time.perf_counter() - t0) * 1000
        print(f"  {PASS}  {name:26} {DIM}{ms:6.0f}ms{X}  {detail}")
        _results.append(("pass", name))
    except Exception as e:  # noqa: BLE001 -- we want every failure surfaced
        ms = (time.perf_counter() - t0) * 1000
        msg = str(e).strip().splitlines()[0] if str(e).strip() else repr(e)
        print(f"  {FAIL}  {name:26} {DIM}{ms:6.0f}ms{X}  {R}{msg}{X}")
        _results.append(("fail", name))


def warn(name: str, detail: str) -> None:
    print(f"  {WARN}  {name:26} {' ' * 8}  {Y}{detail}{X}")
    _results.append(("warn", name))


# --------------------------------------------------------------------------- #
#  individual probes
# --------------------------------------------------------------------------- #
def _model() -> str:
    import httpx

    base = settings.model_base_url.rstrip("/")
    if "<" in base or "your" in base.lower():
        raise RuntimeError(f"MODEL_BASE_URL is still a placeholder: {base}")
    r = httpx.get(
        f"{base}/models",
        headers={"Authorization": f"Bearer {settings.model_api_key}"},
        timeout=8.0,
    )
    if r.status_code == 404:
        raise RuntimeError(
            f"{base}/models -> 404. The endpoint isn't serving the OpenAI API "
            f"(is vLLM up and the tunnel pointed at it?). Try opening {base}/models in a browser."
        )
    r.raise_for_status()
    ids = [m.get("id") for m in r.json().get("data", [])]
    served = settings.model_name
    if served not in ids:
        raise RuntimeError(f"served models {ids} do not include MODEL_NAME={served!r}")
    return f"model '{served}' is being served"


def _model_deep() -> str:
    from app.llm.factory import get_llm_client
    from app.schemas.incident import Detection, Signal

    sig = Signal(
        service="payments-api", metric="error_rate", value=0.38, threshold=0.02,
        message="preflight probe",
    )
    from app.agents.detector import detect

    det = detect(sig, get_llm_client())
    assert isinstance(det, Detection)
    return f"real generate() -> Detection(is_anomaly={det.is_anomaly})"


def _postgres() -> str:
    import psycopg

    with psycopg.connect(settings.database_url, connect_timeout=5) as conn:
        ver = conn.execute("SELECT version()").fetchone()[0]
    return ver.split(",")[0]


def _qdrant() -> str:
    from qdrant_client import QdrantClient

    c = QdrantClient(url=settings.qdrant_url, timeout=5)
    cols = [x.name for x in c.get_collections().collections]
    here = settings.qdrant_collection
    note = f"collection '{here}' exists" if here in cols else f"collection '{here}' will be created on first use"
    return f"reachable; {note}"


def _redis() -> str:
    import redis

    c = redis.Redis.from_url(settings.redis_url, socket_connect_timeout=5)
    c.ping()
    return "PONG"


def _gpu() -> str:
    from app.telemetry.gpu import get_gpu_monitor

    gpus = get_gpu_monitor().sample()
    if not gpus:
        raise RuntimeError("rocm-smi returned no devices")
    g = gpus[0]
    return f"{g.device}: {g.gpu_util_pct:.0f}% util, {g.vram_used_gb:.0f}/{g.vram_total_gb:.0f} GB"


def _otel() -> str:
    import importlib

    importlib.import_module("opentelemetry.sdk.trace")  # libs installed?
    ep = settings.otel_endpoint
    if not ep:
        return "console exporter (no OTEL_ENDPOINT set)"
    host, _, port = ep.replace("http://", "").replace("https://", "").partition(":")
    port = int(port or 4317)
    with socket.create_connection((host, port), timeout=5):
        pass
    return f"collector reachable at {host}:{port}"


def _github() -> str:
    import httpx

    if not settings.github_token:
        raise RuntimeError("GITHUB_TOKEN is empty")
    r = httpx.get(
        f"https://api.github.com/repos/{settings.github_repo}",
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        },
        timeout=8.0,
    )
    r.raise_for_status()
    perms = r.json().get("permissions", {})
    if not perms.get("push", False):
        raise RuntimeError(f"token cannot push to {settings.github_repo} (need contents:write)")
    return f"{settings.github_repo} reachable; push=ok"


def _frontend() -> str:
    import pathlib

    dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist" / "index.html"
    if not dist.is_file():
        raise RuntimeError("frontend/dist not built -- run: cd frontend && npm run build")
    return "built dashboard present"


# --------------------------------------------------------------------------- #
def main() -> int:
    deep = "--deep" in sys.argv
    print(f"\n{B}AGENTS_026 pre-flight{X}  {DIM}(MODEL_MODE={settings.model_mode}, "
          f"STORE={settings.store_mode}, RAG={settings.rag_mode}, "
          f"TELEMETRY={settings.telemetry_mode}, GPU={settings.gpu_monitor_mode}, "
          f"TRACE={settings.trace_mode}, GITHUB={settings.github_mode}){X}\n")

    check("model endpoint", settings.model_mode == "live", _model)
    if deep:
        check("model generate()", settings.model_mode == "live", _model_deep)
    check("postgres", settings.store_mode == "postgres", _postgres)
    check("qdrant (RAG)", settings.rag_mode == "qdrant", _qdrant)
    check("redis (telemetry)", settings.telemetry_mode == "redis", _redis)
    check("MI300X gpu monitor", settings.gpu_monitor_mode == "rocm", _gpu)
    check("opentelemetry", settings.trace_mode == "otel", _otel)
    check("github api", settings.github_mode == "live", _github)
    check("frontend build", True, _frontend)

    # Things preflight can't probe but you must not forget:
    if settings.github_mode == "live":
        warn("webhook tunnel", "verify cloudflared/ngrok is up + the repo webhook URL matches it")
    if settings.gpu_monitor_mode == "rocm":
        warn("gpu monitor host", "rocm-smi only works when THIS process runs on the MI300X pod")
    if settings.rag_mode == "qdrant" and settings.embed_mode == "live":
        warn("embed dim", f"EMBED_DIM={settings.embed_dim} must equal your served embedder's output dim")

    fails = sum(1 for s, _ in _results if s == "fail")
    passes = sum(1 for s, _ in _results if s == "pass")
    print(f"\n  {B}{passes} passed, {fails} failed{X}, "
          f"{sum(1 for s, _ in _results if s == 'skip')} skipped, "
          f"{sum(1 for s, _ in _results if s == 'warn')} warnings\n")
    if fails:
        print(f"  {R}✗ NOT demo-ready.{X} Fix the FAIL rows above, then re-run.\n")
        return 1
    print(f"  {G}✓ All enabled backends are green. You're demo-ready.{X}\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
