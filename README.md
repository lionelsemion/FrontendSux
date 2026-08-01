# FrontendSux

A `FastAPI` subclass that auto-generates an HTML+htmx frontend for plain
Python functions. Decorate a function with `@app.expose(...)` and get: a form
page with one input per parameter (inferred from type annotations), a
form-submit route that renders the result, and a JSON API route — all from
one function.

> [!WARNING]
> **This is a vibe-coded library.** It was built quickly with heavy AI
> assistance and has not had a security review, a stability review, or any
> production hardening. Treat it as a prototyping toy, not infrastructure.
> **Do not use this in production**, and don't expose it on the public
> internet or point it at untrusted input without auditing it yourself first.

## Install

Not published to PyPI. Install straight from this repo:

```bash
uv add git+https://github.com/lionelsemion/FrontendSux.git
# or, pinned to a tag:
uv add git+https://github.com/lionelsemion/FrontendSux.git@v0.1.0
```

(or the `pip install git+https://...` equivalent).

## Usage

```python
from typing import Annotated
from frontend_sux import FrontendSux

app = FrontendSux()


@app.expose(["/shout/"], title="Shout")
def shout(text: Annotated[str, "Text"]) -> Annotated[str, "Result"]:
    return text.upper()
```

Run it with `fastapi dev` / `uvicorn` like any FastAPI app — visit `/shout/`
for the generated form, or `PUT /api/shout/` for the JSON API.

See `main.py` in this repo for a full example app covering every supported
parameter/return type, and `CLAUDE.md` for architecture notes and how to add
a custom form-field type.

## Development

This repo is both the library (`frontend_sux/`) and its own example/test app
(`main.py`, `widgets/`, `tests/`). Those latter three aren't shipped as part
of the installable package.

Run the tests: `uv run pytest`. Non-browser subset only:

```bash
uv run pytest --ignore=tests/test_calculator_e2e.py \
  --ignore=tests/test_navigation_e2e.py \
  --ignore=tests/test_type_coverage_e2e.py
```

Browser tests need `uv run playwright install` once first.
