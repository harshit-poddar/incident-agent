"""Keep the test suite hermetic regardless of a local .env.

A live demo .env may set GITHUB_MODE=live / MODEL_MODE=live; tests must never
hit the network or open real PRs, so force everything back to the offline mocks.
get_*_client() read these settings at call time, so overriding the singleton
here is enough."""
from app.config import settings

settings.github_mode = "mock"
settings.github_webhook_secret = ""   # tests post unsigned payloads
settings.vuln_fixer_mode = "mock"     # never hit the fine-tuned endpoint in tests
settings.model_mode = "mock"
settings.store_mode = "memory"
settings.telemetry_mode = "mock"
settings.gpu_monitor_mode = "mock"
settings.rag_mode = "memory"
settings.embed_mode = "mock"
settings.trace_mode = "memory"   # no OpenTelemetry deps in the test path
