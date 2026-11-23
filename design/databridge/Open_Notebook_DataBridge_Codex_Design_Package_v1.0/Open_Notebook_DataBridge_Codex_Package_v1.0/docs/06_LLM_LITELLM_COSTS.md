# 06 — LiteLLM, API Model Configuration and Cost Tracking

## Approved requirement

All eligible language-model calls from DataBridge route via **LiteLLM Proxy**, while existing Open Notebook model management remains compatible. An OpenAI-compatible API base URL and API key are configurable, and the deployment default model is defined in `.env`, initially **GPT-6 Astra** / API ID `gpt-6-astra` (verified against official OpenAI model docs on Oct. 29, 2026).

## Respect upstream Esperanto model management

Open Notebook's model registry uses `open_notebook/ai/` and the Esperanto `AIFactory` model abstraction, which converts to LangChain. It also allows `OpenAI-Compatible` provider credentials and model registration. A clean implementation routes upstream's OpenAI-Compatible model through LiteLLM's internal base URL, and bootstraps the required provider/model/default settings from `.env`. Keep legacy non-DataBridge sources working, and test full in-product default selection. Do not replace LangGraph's chat nodes with raw, inconsistent OpenAI SDK calls.

Suggested env contract:

```dotenv
LLM_PROVIDER=openai
LLM_MODEL=gpt-6-astra
LLM_PROVIDER_MODEL=openai/gpt-6-astra
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=<server-side-only-secret>
LITELLM_PROXY_URL=http://litellm:4000
LITELLM_MASTER_KEY=<server-side-admin-secret>
LITELLM_SALT_KEY=<stable-server-side-encryption-secret>
LITELLM_APP_VIRTUAL_KEY=<separate-application-key>
LITELLM_DATABASE_URL=postgresql://... # dedicated LiteLLM DB
USAGE_TRACKING_ENABLED=true
USAGE_CURRENCY=USD
```

`LLM_MODEL` is the public alias used in the app; `LLM_PROVIDER_MODEL` is the provider-qualified routing target. Verify exact LiteLLM YAML environment expansion against pinned image, and implement idempotent bootstrapping (do not require the end user to add a model manually via Settings). UI may display `Managed by .env` rather than silently overriding user changes.

## LiteLLM Proxy and persistent spend

Run LiteLLM Proxy as a separate internal container with a **dedicated PostgreSQL DB** (`DATABASE_URL`). The documented spend-log API is `/spend/logs/v2`; the absence of a database disables reliable cumulative spend and proxy key budgets. Use a real application-scoped virtual key, not master key in client code. Keep `LITELLM_SALT_KEY` stable; changing it can invalidate stored encrypted provider secrets. Pin the image tag/digest and use official health endpoints after verifying them for that version.

## Usage tracking requirements

For each eligible request capture or correlate:

- Request/trace ID, notebook ID, chat session ID, user/tenant ID (if known), agent/task ID, timestamp and model alias/backend.
- Input tokens, output tokens, cached input tokens, reasoning token totals if the provider reports them; never invent categories not in provider metadata.
- Estimated cost in USD from LiteLLM price map (or provider-reported billing if available), pricing status (`priced`, `unpriced`, `estimated`, `provider_billed`), and error/denial state.
- Latency, status code, retries (deduplicate any retries so spend isn't double counted), and budget remaining when available.

Use LiteLLM's canonical spend logs and aggregation for cost; optionally cache a narrow aggregate in SurrealDB for UI performance, but avoid double counting. If the model is missing pricing or a rate is unknown, **display “Cost unavailable”**, not `$0.00`. A provider charge can differ from estimated LiteLLM spend, especially cache/tier/long-context pricing; show a disclaimer and pricing freshness.

### Dashboard screens

1. Compact header: current session total tokens and estimated USD spend.
2. Detailed dashboard: current session, today, 7d, all-time; by model, notebook, user/agent, request/task; request count; input/output/cached distribution; trend chart; limit warnings.
3. Execution drawer: per-query LLM calls, token/cost contribution and model identity; tool/MCP execution is separately timed and not falsely billed as LLM tokens.
4. Admin: budget caps and alert thresholds, export/retention policy, key/model health and cost-map refresh warnings.

## Compatibility and provider routing

The OpenAI-compatible target may be the OpenAI API or another trusted compatible endpoint. Configuring an arbitrary endpoint by an unprivileged user is NOT allowed (data exfil risk). Verify provider compatibility for chat/Responses API and selected reasoning params; if `gpt-6-astra` is unavailable to the supplied account, show a configuration error and let the operator set a different model in `.env`. Never silently switch models without preserving evidence and dashboard attribution.

## Embeddings and non-chat models

Open Notebook may use separate embedding/speech or transformation models. Do not assume the GPT-6 Astra model supports embedding. Preserve existing embedding configuration, document whether its calls route through LiteLLM, and label any unmetered service separately. In the MVP, define metering coverage explicitly; never claim 'total AI cost' if provider calls bypass gateway.

## Acceptance

- `.env` default `gpt-6-astra` reaches model through LiteLLM via existing upstream framework; mock-compatible endpoint test.
- Changing `.env` + restart changes default without manual GUI steps; bootstrapping idempotent.
- Real usage logs (or deterministic simulated proxy records for automated tests) render input/output and cost with correct units and date filtering.
- Spend logs persist after PostgreSQL/LiteLLM container restart; missing price does not appear as free usage.
- Budget cap is actually enforced on a test key; master key absent from browser and server logs.
