# RepoMedic

**Issue-to-patch software engineering agent** — given a GitHub issue and repository, RepoMedic clones into an isolated workspace, maps the code, reproduces the failure, proposes a surgical patch, runs tests in a sandbox, and parks a diff + PR summary for human review.

![RepoMedic](docs/architecture.svg)

> Coding agents are impressive only when they can navigate a real repository, reproduce a bug, change the correct files, and prove the patch works. RepoMedic focuses on that full loop.

---

## Demo

| Surface | URL (local) |
|--------|-------------|
| Review UI | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/api/v1/health |

**Happy path:** create a synthetic task against the bundled buggy calculator → watch status move through clone/index/reproduce/patch/verify → download the `.patch` → approve in the UI.

```bash
# after stack is up
python scripts/seed_synthetic_task.py
```

---

## Architecture

```
GitHub webhook/API → FastAPI → Redis/ARQ → Worker
                              ↓
              sandbox · code navigation · repair agent · test runner
                              ↓
                     PostgreSQL evidence store → Next.js review UI
```

See [docs/architecture.md](docs/architecture.md) for the diagram and safety boundaries.

| Component | Role |
|-----------|------|
| `apps/api` | FastAPI — tasks, webhooks, review, diff download |
| `services/worker` | ARQ worker — LangGraph repair loop |
| `apps/web` | Next.js review queue + task detail |
| `packages/repomedic_core` | Models, indexer, sandbox, patching, agent nodes |
| `evals/` | Curated issues + offline benchmark |
| `postman/` | API collection |

---

## Hard problems (and how we handle them)

1. **Safe command execution** — Docker sandbox with memory/CPU limits, timeouts, and optional network disable. Local fallback for dev when Docker is unavailable.
2. **Context selection** — AST/heuristic symbol index + keyword search; never dump the full repo into the model.
3. **Verification** — Reproduction evidence is captured before patching; post-patch tests/lint are stored as first-class evidence rows.
4. **Destructive / hallucinated edits** — Patch validator enforces path bounds, forbids `.env`/`.git`, caps files changed and diff size; human approval is required before any “done” state.

---

## Evaluation

| Metric | Dataset | How to run |
|--------|---------|------------|
| Offline support success | 10 curated cases in `evals/datasets/curated_issues.json` | `python evals/run_benchmark.py` |

Graders cover path safety, index quality, pre-patch failure reproduction, retrieval/checklist signals, and PR-summary completeness. Extend the JSON and re-run — report writes to `evals/last_report.json`.

---

## Safety & reliability

- No secrets in git — copy `.env.example` → `.env`
- Structured LLM outputs via Pydantic schemas
- Agent traces persisted per step (tool, timing, payloads)
- Review gate: `awaiting_review` → approve / reject / needs_changes
- `ALLOW_AUTO_PR=false` by default (draft PR creation is opt-in)

**Known limitations:** MVP targets Python (TypeScript/JS supported for indexing/search; full TS repair needs a richer fixture). LLM patch quality depends on your model key. Sandbox image must be built for hard isolation (`docker compose --profile build-sandbox build sandbox`).

---

## Run locally

### Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for host-side tests/evals)
- Node 22+ (optional if you run web via Compose)
- OpenAI API key (or set `SYNTHETIC_MODE=true` for offline demos)
- GitHub token (for live issue/repo clone; skip with synthetic fixture)

### 1. Configure env

```bash
cd repo-medic
cp .env.example .env
# fill OPENAI_API_KEY, GITHUB_TOKEN, passwords, etc.
```

For a fully offline first run, set:

```env
SYNTHETIC_MODE=true
SANDBOX_ENABLED=false
```

### 2. Start the stack

```bash
# optional: build the sandbox image used by the worker
docker compose --profile build-sandbox build sandbox

docker compose up --build
```

Services:

| Service | Port |
|---------|------|
| Web | 3000 |
| API | 8000 |
| Postgres | 5433 (host) → 5432 (container) |
| Cloned repos | `./workspaces/<task_id>/repo` (host) → `/app/workspaces/...` in worker |
| Redis | 6379 |

### 3. Seed a synthetic repair

```bash
pip install -e ".[dev]"
python scripts/seed_synthetic_task.py
```

Open the printed review URL, wait for `awaiting_review`, inspect diff/evidence, approve.

### Host-mode API / worker (optional)

```bash
# terminals with .env loaded and Postgres/Redis up
pip install -e ".[dev]"

# API
cd apps/api
set PYTHONPATH=../../packages;..
uvicorn app.main:app --reload --port 8000

# Worker
cd services/worker
set PYTHONPATH=../../packages
arq worker.WorkerSettings

# Web
cd apps/web
npm install && npm run dev
```

---

## API examples

**Create from issue URL**

```http
POST /api/v1/tasks/from-url
Content-Type: application/json

{
  "issue_url": "https://github.com/owner/repo/issues/42",
  "language": "python"
}
```

**Synthetic task**

```http
POST /api/v1/tasks
Content-Type: application/json

{
  "github_owner": "local",
  "github_repo": "sample-python",
  "issue_number": 1,
  "language": "python",
  "synthetic": true,
  "issue_title": "divide by zero should raise",
  "issue_body": "divide(1,0) must raise ZeroDivisionError"
}
```

**Download patch**

```http
GET /api/v1/tasks/{id}/diff/raw
```

Import `postman/RepoMedic.postman_collection.json` for the full set (health, tasks, review, webhook).

---

## Tests & CI

```bash
pytest -q
ruff check packages tests services apps/api
python evals/run_benchmark.py
```

GitHub Actions (`.github/workflows/ci.yml`) runs lint, pytest, eval smoke, and Next.js build on every push/PR.

---

## Tradeoffs

| Chose | Deferred |
|-------|----------|
| One-issue-at-a-time queue | Multi-tenant scheduling / priority lanes |
| Python-first fixtures + heuristic TS indexing | Deep tree-sitter multi-language pack |
| Human review required | Automatic draft PR (`ALLOW_AUTO_PR`) |
| ARQ + Redis | Celery/Temporal for larger fleets |
| Clean Next.js review UI | Full design-system / auth product surface |

---

## Roadmap

- [ ] Self-review agent pass before human queue
- [ ] Automatic draft PR creation when approved
- [ ] Richer TypeScript fixture + Jest evidence path
- [ ] Expand eval set toward 30+ scored repair scenarios
- [ ] Stream worker progress over SSE/WebSocket

---

## License

MIT — use freely in portfolio and production experiments.