# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

NextHire AI's API. Modelled on `../../HGS/hgs-backend` (itself on `sp-company-backend`):
same layering, envelope, exception mapping, config loader and Makefile targets.
When in doubt, read how hgs-backend does it. Deviations: `../docs/ARCHITECTURE.md` §5.

## Commands (no make on the dev machine — direct forms)

```bash
python -m venv venv && ./venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env                                                         # MONGODB_URL, SECRET_KEY, ADMIN_*, GEMINI_API_KEY
docker compose up -d mongo                                                   # MongoDB 8 -> 127.0.0.1:27018 (container nexthire-mongodb)
./venv/Scripts/python.exe scripts/seed_demo_data.py [--dry-run]             # starter sources (+ demo seeker), idempotent
./venv/Scripts/python.exe -m uvicorn src.api.app:app --port 8002 --reload   # /docs, /health; scheduler starts too

./venv/Scripts/python.exe -m pytest tests -q --no-cov
./venv/Scripts/python.exe -m pytest tests/integration/test_source_and_run_routes.py -v --no-cov
./venv/Scripts/python.exe -m ruff format --check . && ./venv/Scripts/python.exe -m ruff check .
./venv/Scripts/python.exe -m mypy src/ scripts/ --ignore-missing-imports
./venv/Scripts/python.exe -m bandit -r src/ --ini .bandit
```

## Layout

```
src/api/app.py         factory: CORS -> ResponseWrapper -> AuditContext, handlers, /health; lifespan ensures indexes, starts the scheduler
src/api/v1/router.py   THE URL map — prefixes assigned here only
src/modules/<name>/    api/{routes,dependencies.py} · application/{schemas,use_cases,services} ·
                       domain/{entities,enums,services,value_objects} · infrastructure/{repositories,external,scorers}
src/shared/            kernel ported from hgs-backend, plus ai/gemini_client.py and tasks/{scheduler,dispatcher}.py
```

Modules: `user`, `auth` (login/register/me/logout), `job_source`, `collection`
(runs + connectors under `infrastructure/external/connectors/`), `job`
(search, moderation, public stats; `JobPresenter` decorates cards), `saved_job`,
`tracker` (applications), `preference`, `recommendation` (pre-filter +
Gemini/heuristic scorers), `notification`, `dashboard`.

## Rules

- Use cases raise domain exceptions; the mapping is in
  `shared/api/exception_handlers/business_handlers.py` (`ExternalServiceError` → 502).
- Routes return bare payloads; `ResponseWrapperMiddleware` adds the envelope.
- Roles: `Depends(hasAccess(roles=SIGNED_IN | ADMIN_ONLY))`. Ownership: every
  per-user repository method takes `user_id` and filters on it.
- Database: MongoDB via PyMongo (sync). Entities extend `MongoDocument`
  (`shared/domain/entities/document.py`): `__collection__`, `__indexes__`;
  `id` is `_id`, enums stored by value, `date` as UTC-midnight datetime.
  `MongoSession` (`shared/infrastructure/database.py`) is the unit of work:
  `add`+`commit` inserts a new entity or `$set`s only the changed fields of a
  loaded one. No transactions, no foreign keys — a hard delete cascades in
  the repository. Unique collisions raise `pymongo.errors.DuplicateKeyError`.
  Query helpers (`contains_ci`, `resolve_sort_column`, `sort_spec`) live in
  `shared/infrastructure/ordering.py`.
- Collection: `StartRunUseCase` claims the source with an atomic update
  (`JobSourceRepository.claim`), `ExecuteRunUseCase` does the work on its own
  session. Routes hand work to `get_task_dispatcher()`; tests swap in
  `InlineTaskDispatcher` and `get_session_factory`.
- A connector returns `CollectedJob`s and never touches the DB; register it in
  `connectors/registry.py` and give its type a rule in `source_config.py`.
  All outbound HTTP goes through `HttpFetcher` (timeouts, size cap, no private hosts).
- Gemini only through `GeminiClient`; scoring falls back to `HeuristicScorer`.
  Postings go to the model as JSON data; output is validated in `parse_verdicts`.
- MongoDB keeps milliseconds: don't compare datetimes for exact equality
  against microsecond values. `shared/domain/time.as_utc` for naive inputs.
- New collection: entity with `__collection__` + `__indexes__` and its package
  in `discover_entities()`. Indexes are created on startup (`ensure_indexes`);
  changing an existing index's options means dropping it by hand first.

## Tests

`tests/conftest.py` sets `ENVIRONMENT=test` (→ `config/.env.test`: no
scheduler, no Gemini key) and patches mongomock to encode UUIDs as the app
does. Integration tests run the real app over HTTP against an in-memory
mongomock database with every index created; `FakeConnector` + `fake_connector` replace connectors, and the
scorer is overridden to `HeuristicScorer`. Unit tests use `httpx.MockTransport`
and a fake resolver — nothing touches the network.
Assertions go through the envelope: `response.json()["data"]`.
