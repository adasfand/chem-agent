# Repository Guidelines

## Project Structure & Module Organization

`src/chem_agent/` contains configuration, knowledge retrieval, deterministic calculations, validated execution, model integration, CLI, FastAPI service, and the independent Vue/TypeScript frontend in `web/`. Keep numerical functions independent of model calls. `data/knowledge/` contains 71 teaching and official-source knowledge cards; `examples/tasks.json` defines demonstration inputs. `tests/` contains offline regression tests. `docs/` holds the research report and verified workflow evidence. Generated private records belong in ignored `runs/`; delivery archives belong in `dist/`.

Root planning reports describe proposals; consult `README.md` and code for implemented behavior.

## Build, Test, and Development Commands

- `uv sync --locked`: install the pinned runtime and development dependencies.
- `uv run chem-agent doctor`: check configuration without calling a model.
- `uv run chem-agent index`: rebuild retrieval in memory and write a document manifest.
- `uv run chem-agent search "显热公式"`: run offline retrieval.
- `uv run chem-agent ui`: start the local interface.
- `uv run pytest`: run offline Python tests.
- `node --test tests/frontend_state.test.cjs`: check frontend state transitions offline (Node 22+).
- `uv run ruff check src tests scripts app.py cli.py`: check code style.
- `uv run ruff format --check src tests scripts app.py cli.py`: verify formatting.
- `uv run python scripts/validate_live.py`: run billable DeepSeek acceptance cases when authorized.
- `uv run python scripts/package.py`: create the source delivery ZIP using an explicit allowlist.

## Coding Style & Naming Conventions

Use Python 3.11–3.13, four-space indentation, explicit input/output types, `snake_case` functions/modules, and `PascalCase` classes. Follow the Ruff settings in `pyproject.toml`. Preserve Chinese documentation, source attribution, units, and calculation assumptions. Keep changes focused; avoid adding unrelated frameworks.

## Testing Guidelines

Use pytest and `tests/test_*.py`. Cover reference calculations, incompatible units, missing inputs, retrieval provenance, actual result references, model failure, cancellation, report export, and session isolation. Default tests must work without credentials or model requests. No numeric coverage threshold is imposed. Distinguish offline checks, actual live calls, and replayed records.

For local browser checks, first reuse the user's running backend at `http://127.0.0.1:7860` and Vue frontend at `http://127.0.0.1:5173`. Preserve user-owned service processes; a separate service requires current user authorization. Use one or two representative billable examples to demonstrate the actual workbench flow. Show functional evidence through retrieval paths, execution plans, tool parameters/results, result references and citations.

## Commit & Pull Request Guidelines

The original history contains a single prototype upload. Use concise imperative subjects such as `fix: validate units in result references`, with `feat`, `fix`, `docs`, or `chore` prefixes. Describe changes, validation, limitations, and related issues. Include screenshots for UI changes. Tag verified deliveries as `vX.Y.Z`.

## Security & Configuration

Keep keys in local environment variables or a locally configured key file. Never commit `.env`, credentials, or private run histories. Only vetted, redacted traces belong in `docs/validation/`. Preserve the packaging allowlist; do not distribute `.venv`, `.local`, or raw `runs/`.
