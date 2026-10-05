# Repository Guidelines

## Project Structure & Module Organization

`src/chem_agent/` contains configuration, knowledge retrieval, deterministic calculations, validated execution, model integration, CLI, and the FastAPI service. `web/` contains the complete Vue 3 / TypeScript / Vite frontend: components, API client, state, tests, package lockfile and local `node_modules`. Build output belongs in `web/dist/`; frontend dev/preview servers serve the UI and proxy `/api` to the independent backend. Keep numerical functions independent of model calls. `data/knowledge/` contains 15 original Chinese teaching cards; `examples/tasks.json` defines demonstration inputs. `tests/` contains offline Python regression tests. `docs/` holds the technical report and historical verified sample traces. Generated private records belong in ignored `runs/`; delivery archives belong in root `dist/`.

Root planning reports describe proposals; consult `README.md` and code for implemented behavior.

## Build, Test, and Development Commands

- Activate the `chem-agent` Conda environment (Python 3.12); use `uv export --locked --no-emit-project` and `python -m pip install` as documented in README. Do not silently create a second `.venv` or change dependency versions.
- `python cli.py doctor`: check configuration without calling a model.
- `python cli.py index`: rebuild retrieval in memory and write a document manifest.
- `python cli.py search "显热公式"`: run offline retrieval.
- `python app.py`: start the API backend at `127.0.0.1:7860`; health is available at `/api/health`.
- In `src/chem_agent/web/`, run `npm ci` then `npm run dev`; development at `127.0.0.1:5173` proxies `/api` to the backend. Use the existing local Node; no global npm installs.
- In `web/`, run `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm test`, and `npm run build` for frontend verification; `npm run format` applies Prettier formatting.
- `python -m pytest`: run offline Python tests.
- `python -m ruff check src tests scripts app.py cli.py`: check code style.
- `python -m ruff format --check src tests scripts app.py cli.py`: verify formatting.
- `python scripts/validate_live.py`: run billable DeepSeek acceptance cases when authorized.
- `python scripts/package.py`: create the source delivery ZIP, including frontend source and any existing build output but excluding installed dependencies. A frontend build is optional for source packaging.
- `python scripts/package_frontend_dependencies.py`: optionally archive installed Windows frontend dependencies separately; preserve third-party license files and platform/Node/lockfile metadata.

## Coding Style & Naming Conventions

Use Python 3.11–3.13, four-space indentation, explicit input/output types, `snake_case` functions/modules, and `PascalCase` classes. Follow the Ruff settings in `pyproject.toml`. Frontend code uses TypeScript and Vue single-file components; separate API types, state, components and styling, and reuse existing helpers. Preserve Chinese documentation, source attribution, units, and calculation assumptions. Keep changes focused; avoid adding unrelated frameworks or remote CDN assets.

## Testing Guidelines

Use pytest and `tests/test_*.py`. Cover reference calculations, incompatible units, missing inputs, retrieval provenance, actual result references, model failure, cancellation, report export, and session isolation. Default tests must work without credentials or model requests. No numeric coverage threshold is imposed. Distinguish offline checks, actual live calls, and replayed records.

## Commit & Pull Request Guidelines

The original history contains a single prototype upload. Use concise imperative subjects such as `fix: validate units in result references`, with `feat`, `fix`, `docs`, or `chore` prefixes. Describe changes, validation, limitations, and related issues. Include screenshots for UI changes. Tag verified deliveries as `vX.Y.Z`.

## Security & Configuration

Keep keys in local environment variables or a locally configured key file. Never expose API keys in browser variables or commit `.env`, credentials, or private run histories. Only vetted, redacted traces belong in `docs/validation/`. Preserve packaging allowlists and prune dependency directories before traversal. Do not distribute environments, `.local`, or raw `runs/`. Main source ZIPs exclude `node_modules`; offline frontend dependency ZIPs are separate and platform-specific. Keep live model evidence distinct from offline fixture-based UI checks and historical records.
