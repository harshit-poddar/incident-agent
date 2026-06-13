from __future__ import annotations

import re
from typing import Protocol, runtime_checkable

from app.config import settings

# --- The fine-tuned prompt contract ----------------------------------------
# CRITICAL: the "vuln-fixer" adapter (a LoRA on Qwen2.5-Coder-7B) was fine-tuned
# on these EXACT strings. Reproduce them verbatim -- reformatting (even
# whitespace) degrades the tuned behaviour. This is why the vuln fixer does NOT
# ride the JSON-structured LLMClient seam: it takes its own raw prompts and
# returns raw Java inside a single ```java fence.

VULN_FIXER_SYSTEM = (
    "You are a senior application-security engineer. You fix vulnerabilities in "
    "Java code. Reply with ONLY the complete fixed Java code inside a single "
    "```java code block. Keep the original class and method signatures; change "
    "only what is needed to remove the vulnerability. If the given code is "
    "already secure, return it unchanged."
)

# The three CWEs the adapter was trained on, with their verbatim descriptions.
CWE_DESCRIPTIONS: dict[str, str] = {
    "CWE-89": "SQL Injection: untrusted input is concatenated into a SQL query",
    "CWE-78": "OS Command Injection: untrusted input reaches an OS command",
    "CWE-22": "Path Traversal: untrusted input is used to build a filesystem path",
}


class UnsupportedCWE(ValueError):
    """Raised when a CWE outside the adapter's trained set (89/78/22) is asked for."""


def build_user_prompt(code: str, cwe: str) -> str:
    """Build the verbatim USER prompt the adapter expects. Substitutes {cwe},
    {cwe_description}, {code} into the exact fine-tuning template."""
    cwe = cwe.strip().upper()
    if cwe not in CWE_DESCRIPTIONS:
        raise UnsupportedCWE(
            f"{cwe!r} is not one of the trained CWEs {sorted(CWE_DESCRIPTIONS)}."
        )
    return (
        f"Review the following Java code for a {cwe} vulnerability "
        f"({CWE_DESCRIPTIONS[cwe]}). If the vulnerability is present, fix it. "
        f"If the code is already secure, return it unchanged.\n\n"
        f"```java\n{code}\n```"
    )


_FENCE = re.compile(r"```(?:java)?\s*\n?(.*?)```", re.DOTALL)


def extract_java(text: str) -> str:
    """Pull the code out of the single ```java ... ``` fence the model returns.
    If no fence is present, return the raw text (per the integration spec)."""
    match = _FENCE.search(text)
    return match.group(1).strip() if match else text.strip()


@runtime_checkable
class VulnFixerClient(Protocol):
    """The seam to the fine-tuned Java vuln-fixer model. Mock = offline canned
    secure rewrite (CPU, no GPU); Remote = the OpenAI-compatible vLLM endpoint
    serving the 'vuln-fixer' LoRA adapter. Same DI pattern as LLMClient and
    GitHubClient -- callers receive a client, never import a concrete one."""

    def fix(self, *, code: str, cwe: str) -> str:
        """Return the patched Java source for the given CWE (code only, fence
        already stripped)."""
        ...


class RemoteVulnFixerClient:
    """Talks to the fine-tuned adapter over the OpenAI-compatible API (vLLM with
    --enable-lora). Reproduces the verbatim fine-tuning prompts and extracts the
    code from the model's ```java fence. `openai` is imported lazily so mock runs
    need no dependency and no network."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        from openai import OpenAI  # lazy: mock runs need no openai dep

        self._model = model or settings.vuln_fixer_model_name
        self._client = OpenAI(
            base_url=base_url or settings.vuln_fixer_base_url,
            api_key=api_key or settings.vuln_fixer_api_key,
        )

    def fix(self, *, code: str, cwe: str) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": VULN_FIXER_SYSTEM},
                {"role": "user", "content": build_user_prompt(code, cwe)},
            ],
            temperature=0.0,  # deterministic -- this is a code fix, not creative text
            max_tokens=1024,
        )
        return extract_java(resp.choices[0].message.content or "")


# Deterministic, genuinely-secure rewrites the mock returns -- one per trained
# CWE. They mirror what the tuned model produces: a parameterised query (89), a
# no-shell ProcessBuilder (78), and a canonical-path allow-list (22). The CWE-89
# rewrite keeps the exact class/method signatures of the vulnerable demo file
# that MockGitHubClient serves, so the proposed diff is minimal and real.
_SECURE_REWRITES: dict[str, str] = {
    "CWE-89": """\
package com.acme.payments;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

public class PaymentRepository {
    private final Connection connection;

    public PaymentRepository(Connection connection) {
        this.connection = connection;
    }

    public ResultSet findByUser(String userId) throws Exception {
        String query = "SELECT * FROM payments WHERE user_id = ?";
        PreparedStatement stmt = connection.prepareStatement(query);
        stmt.setString(1, userId);
        return stmt.executeQuery();
    }
}
""",
    "CWE-78": """\
package com.acme.ops;

import java.util.List;

public class HostPinger {
    public Process ping(String host) throws Exception {
        // No shell: pass argv directly so the host string can never be
        // interpreted as additional shell commands.
        return new ProcessBuilder(List.of("ping", "-c", "1", host)).start();
    }
}
""",
    "CWE-22": """\
package com.acme.files;

import java.io.File;
import java.nio.file.Path;

public class ReportStore {
    private final Path baseDir;

    public ReportStore(Path baseDir) {
        this.baseDir = baseDir.toAbsolutePath().normalize();
    }

    public File open(String name) throws Exception {
        Path resolved = baseDir.resolve(name).normalize();
        if (!resolved.startsWith(baseDir)) {
            throw new SecurityException("path traversal blocked: " + name);
        }
        return resolved.toFile();
    }
}
""",
}


class MockVulnFixerClient:
    """Offline stand-in: returns a deterministic, genuinely-secure rewrite for
    each trained CWE so the whole integration -- and the judge demo -- runs on
    CPU with no GPU and no network."""

    def fix(self, *, code: str, cwe: str) -> str:
        cwe = cwe.strip().upper()
        if cwe not in _SECURE_REWRITES:
            raise UnsupportedCWE(
                f"{cwe!r} is not one of the trained CWEs {sorted(_SECURE_REWRITES)}."
            )
        return _SECURE_REWRITES[cwe].rstrip("\n")


def get_vuln_fixer_client() -> VulnFixerClient:
    """Single env switch, same as every other seam (vuln_fixer_mode)."""
    if settings.vuln_fixer_mode == "live":
        return RemoteVulnFixerClient()
    return MockVulnFixerClient()


def fix_java_vulnerability(code: str, cwe: str) -> str:
    """Convenience entrypoint matching the integration spec: build the verbatim
    prompts, call the configured vuln-fixer endpoint, and return the fixed Java
    source (code only, fence stripped).

    The orchestrator must pass the CWE id. TODO: auto-detect the CWE from a SAST
    scanner finding; for now it is supplied explicitly."""
    return get_vuln_fixer_client().fix(code=code, cwe=cwe)
