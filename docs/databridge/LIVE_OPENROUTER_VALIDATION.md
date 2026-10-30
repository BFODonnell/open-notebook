# Live GPT-6 Astra through OpenRouter

Date: 2026-10-29 (America/New_York); UTC evidence timestamps fall on October 30.
The owner explicitly selected GPT-6 Astra after discovery confirmed its OpenRouter
ID, `openai/gpt-6-astra`.

## Corrected behavior

The original live-catalog stack still used the P1 model fixture. Source chat
returned its fixed “42” response; research rejected it as invalid JSON. Saving a
provider credential had not automatically selected a real model.

The live stack now loads the app-stored encrypted credential into LiteLLM and uses
alias `openrouter-gpt-6-astra`. Both chat defaults follow the existing environment
bootstrap. One session explicitly referencing the old managed model was moved to
the new model. The old generated model was relabeled `validation-fixture-disabled`;
historical messages were retained. The placeholder now returns `model_not_found`
instead of invented answers. Separate offline acceptance fixtures are unchanged.

No new LLM framework, database or SQL authority was introduced. The requested
official OpenRouter API is the provider endpoint. Credentials stay encrypted in
SurrealDB; a short-lived app container uses the existing database network and
encryption implementation. The launcher captures the decrypted key only in memory
and passes it to the LiteLLM environment, never a second file or the frontend.
Stable encryption configuration and volumes remain necessary after restart.

## Executed validation

- Model discovery with the saved credential succeeded.
- Real source chat described the NTD schema/provenance document and distinguished
  it from raw records and observed ridership results.
- GPT-6 Astra planned a record-count query grouped by Report Year. The P2 policy
  accepted it; the test inspected the bounded SQL, requested review and submitted
  its one-use approval. Real MCP results matched the live-import counts: 2022
  **12,906**; 2023 **12,801**; 2024 **12,966**; 2025 **13,043**.
- Live synthesis passed exact cell/hash/query/version verification. The verified
  answer persisted in the existing notebook conversation.
- LiteLLM persisted planning/synthesis tokens and estimated costs with notebook,
  session and task attribution. Those two calls' recorded estimate was **$0.0943725**;
  it excludes the separate source-chat call and is not a provider invoice. The
  existing **$20 lifetime app-key budget** was preserved, not reset.
- Full stack stop/start reloaded the encrypted credential while the API was stopped.
  The live defaults, answer, evidence and usage records survived. The persistence
  check made no additional paid request.
- Six new negative/configuration tests cover cold-start secret handling, unapproved
  provider rejection, fixture DNS/CA exclusion, safe credential-read failure and
  rejection of fabricated placeholder answers. Full backend: **1,254 passed**.

[Sanitized evidence](evidence/live-openrouter-astra-2026-10-29.json) contains actual
model/query/version/usage identifiers and the answer, with no provider key or
approval bearer. [Setup and paid-check commands](../../scripts/databridge_live/README.md)
document reproduction without copying the provider key.

OpenRouter's [model listing](https://openrouter.ai/openai/gpt-6-astra) and live model
catalog supplied identity/pricing. Reviewed base rates were $10/M input and $50/M
output; cache and high-context tiers differ. LiteLLM estimates are not invoices.

## Remaining scope

This validates live provider access and bounded source-chat/planning/MCP/synthesis
for this model/account, not every question, provider outage, pricing tier or
analytical claim. Earlier controlled failure/budget tests remain the failure
evidence. Browser E2E, other engines, translations and NTD/Census/NOAA alignment
remain outstanding. Comma-formatted NTD measures still need reviewed normalization
before numerical ridership analysis. Source chat discusses documentation; use
notebook chat for approved database queries. No subsequent phase has begun.
