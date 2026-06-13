# incident-agent-demo — the watched deployment

This is the **deployed service** the incident agent watches. It is a tiny Java
`payments-api` with a deliberately planted **CWE-89 SQL injection**. Its deploy
job runs a security scan that **fails on the vulnerability**, which triggers the
agent end-to-end:

```
push / Run workflow
   -> security-scan job runs  -> SAST finds CWE-89 -> job FAILS (exit 1)
   -> GitHub fires workflow_run(failure) webhook
   -> incident agent: detector + diagnoser (common model) find the issue
   -> ROUTED to the fine-tuned "vuln-fixer" agent  -> proposes the patched file
   -> [HUMAN APPROVAL GATE]
   -> agent opens a fix PR on THIS repo  -> RESOLVED
```

The top agents (detect/diagnose/verify) use the common base model; only the
*fix* is produced by the fine-tuned model. Restarting a service, fixing a CI
failure, and patching a CWE all ride the same gated flow — only the specialist
behind the fix changes.

## Layout

```
.github/workflows/security-scan.yml   the deploy job (build -> SAST -> deploy)
src/main/java/com/acme/payments/PaymentRepository.java   the vulnerable code
scripts/sast_scan.py                  minimal SAST (swap for CodeQL/Semgrep)
pom.xml                               Maven build
```

> These files live under `examples/` in the agent repo for convenience. To run
> the live demo, push them to a real repo named `incident-agent-demo` (or any
> repo) and point its webhook at the agent.

## One-time wiring (live demo)

1. **Run the agent** with live integrations (separate terminal, on/near the pod):

   ```bash
   GITHUB_MODE=live \
   GITHUB_TOKEN=<PAT with repo scope> \
   GITHUB_BASE_BRANCH=main \
   VULN_FIXER_MODE=live \
   VULN_FIXER_BASE_URL=http://<POD_HOST>:8000/v1 \
   uvicorn app.main:app --port 8080
   ```

   The PAT must be able to read this repo's run logs and open PRs on it.

2. **Expose the webhook** (the runner must reach the agent):

   ```bash
   ngrok http 8080      # or cloudflared / any tunnel
   ```

3. **Add the repo webhook** (this repo → Settings → Webhooks → Add webhook):
   - Payload URL: `https://<tunnel>/github/webhook`
   - Content type: `application/json`
   - Secret: match the agent's `GITHUB_WEBHOOK_SECRET` (optional in dev)
   - Events: **Workflow runs**

## Trigger it

- Push to `main`, or **Actions → security-scan → Run workflow**.
- The job fails on the SAST step. Within a second or two the agent opens an
  incident (visible at `GET /incidents/latest` and on the dashboard), paused at
  the approval gate with the proposed patch.
- Approve: `POST /incidents/{id}/approve {"approved": true}` (or the dashboard
  **✓ Approve** button) → the agent opens the fix PR on this repo.

The PR replaces the string-concatenated query with a parameterised
`PreparedStatement`, keeping the class and method signatures intact.

## No-network fallback

If the runner, tunnel, or wifi is flaky on stage, drive the identical routed
path offline with no GitHub and no GPU:

```bash
curl -X POST http://localhost:8080/github/simulate-vuln
# then approve the returned incident id
```

This synthesises the same failed `security-scan` run; the agent routes it to the
vuln-fixer (mock = a canned, genuinely-secure rewrite) and records the PR
offline. See the agent repo's `DEMO.md` (Act III) and `scripts/vuln_demo.py`.
