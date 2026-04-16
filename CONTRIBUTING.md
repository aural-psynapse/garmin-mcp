# Contributing

## Local development (no Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml
export GARMIN_MCP_CONFIG=$PWD/config.yaml
cd src && PYTHONPATH=. uvicorn main:app --host 127.0.0.1 --port 8765
```

## Code style

- Python 3.12+
- Type hints on public functions
- Format and lint: `make lint` (runs `ruff check` and `ruff format --check` on `src/` and `tests/`)
- Apply formatting: `make format`
- Optional [pre-commit](https://pre-commit.com): `pip install pre-commit && pre-commit install` — hooks match CI (`ruff`, `ruff-format`)

## Adding a new tool

1. Add a function in `src/tools/<module>.py` and register inside `register(mcp)`.
2. Add a toggle in `ToolToggles` in `src/config.py` and `config.example.yaml`.
3. Extend SQLite in `src/database.py` if new persistence is needed.
4. If syncing from Garmin is required, add logic only in `src/sync.py` (tools read DB only, except `get_my_context`).
5. Add unit tests under `tests/unit/tools/` and e2e coverage if applicable.

## Adding a new user

Add a `users[]` block in `config.yaml` with all required fields (see `config.example.yaml`).

## Adding a new flag rule

1. Add threshold fields to per-user `flag_rules` in `src/config.py` with defaults.
2. Add a flag type constant in `src/tools/flags.py` or a shared `src/flag_constants.py`.
3. Implement evaluation in `src/sync.py` following existing patterns.
4. Register the rule in the flag evaluation loop after sync.
5. Add boundary unit tests (e.g. under `tests/unit/` or `tests/unit/tools/`).
6. Document in `context.md` and `config.example.yaml`.

## Tests

```bash
pytest tests/ -v --cov=src
```

## Pull requests

- One logical change per PR.
- Include tests for behavior changes.
- Describe what changed and why in full sentences.
