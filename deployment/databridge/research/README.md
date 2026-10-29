# Conversational database research (Phase 4)

Requires accepted Phase 1, MCP and ingestion deployments. Keep stable credentials
and existing volumes. Add the research overlay to enable notebook chat planning:

```powershell
docker compose --env-file .env.databridge -f compose.databridge.yml -f compose.databridge-mcp.yml -f compose.databridge-ingestion.yml -f compose.databridge-research.yml up -d --build --wait --wait-timeout 180
```

Without this overlay `DATABRIDGE_RESEARCH_ENABLED` defaults to false. Startup runs
migration 28. No extra Python dependencies or MCP server are required. Existing
Esperanto credentials/models, default model configuration, LangGraph checkpoints,
SurrealDB, LiteLLM PostgreSQL accounting and background worker remain in place.

## Use

1. Open a notebook chat, then search the Open Data Explorer for a dataset.
2. Inspect metadata, choose an importable resource, validate/preview it and Import
   into that notebook. Wait for `ready`; no manual database registration is needed.
3. Return to the same notebook chat and ask a supported single-table data question.
   Newly ready imports are discovered on each question, even in an existing session.
4. Review the dataset title, immutable version and canonical SQL. Click **Review
   SQL** to obtain a fresh plan, then explicitly approve execution. Review labels
   are localized through the existing locale dictionaries.
5. Inspect the verified values, query, version, result/database hashes and provenance.
   For a supported annual aggregation, the card also shows the deterministic trend.

The exact fixture demonstration is “Total trips” -> 700, or “Annual trend with
document context” -> 2022:100, 2023:150, 2024:200, 2025:250, change 150. These are
synthetic test values, never official DOT findings. Actual model planning quality
and live provider access still require validation. Generated SQL must be reviewed
for intended filters, grain, units and denominator even when the security gate passes.

## Failure and recovery

- Expired/replayed/invalid approvals cannot execute. Reload requires fresh review;
  browser storage contains no approval bearer. Connection changes or new imports
  invalidate pending conversational approval; ask a new question in that case.
- A service failure produces no findings. After recovery, review and approve again.
- If the query succeeded but synthesis failed, **Resume answer** uses the stored
  evidence and bills only a new synthesis call. It never reruns SQL.
- Interrupted execution/synthesis claims expire after ten minutes. Resume reconciles
  a unique saved successful MCP run or refuses an indeterminate outcome. Do not
  reset approval state or delete evidence to force a retry.
- `/api/databridge/research/{id}` and review/execute/resume require the correct
  notebook and chat session plus application authentication. No sensitive diagnostics
  or credentials are added to responses. Existing shared-password limitations apply.

Planning and synthesis appear as `database_plan` and `database_synthesize` in the
existing usage ledger, with notebook/session correlation. Pricing/budget limitations
remain as documented in [Phase 1](../README.md). Selecting another existing provider
uses Esperanto normally; only gateway-routed calls have LiteLLM monetary accounting.

## Live catalog key and test separation

Store `DATAGOV_API_KEY=...` in the root `.env.databridge`, excluded from Git and
Docker build context. It is backend-only. Do not paste it into chat, screenshots,
committed files or frontend variables. Recreate with Compose `up` after editing;
`restart` alone does not reload environment variables. Preserve other secrets.

**Never load a personal key with `scripts/databridge_p3/provider.compose.yml`.**
That disposable fixture maps the official catalog/publisher hostnames to a local
synthetic TLS server. Use only the production overlays above for live acquisition;
remove fixture DNS mappings and test CA configuration. The Data.gov key goes only
to the official catalog endpoint, never to publisher downloads or the model.

Cross-source joins remain disabled. Follow the
[NTD/Census/NOAA preparation contract](../../../docs/databridge/NTD_CROSS_SOURCE_PREPARATION.md)
before any comparison. Back up notebook/checkpoint, SurrealDB, published versions
and LiteLLM volumes together. Remove the research overlay to disable the feature;
retain migration data and volumes so historical evidence remains intact.
