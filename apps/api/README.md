# @kanea/api

FastAPI service. Managed by Poetry; orchestrated through Nx.

## Local development

```bash
nx run api:install
nx run api:dev
```

The dev server runs at http://localhost:8000. OpenAPI docs at `/docs`.

## Targets

| Target      | Command                      |
| ----------- | ---------------------------- |
| `install`   | `poetry install`             |
| `dev`       | `uvicorn --reload`           |
| `serve`     | `uvicorn` (production-style) |
| `lint`      | `ruff check`                 |
| `format`    | `black .`                    |
| `typecheck` | `mypy app`                   |
| `test`      | `pytest`                     |
| `build`     | `poetry build`               |

## Layout

```
apps/api/
├── app/
│   ├── api/         # routers (feature code lands here)
│   ├── core/        # config, lifecycle, shared infra
│   └── main.py      # FastAPI factory + health probe
├── tests/
└── pyproject.toml
```
