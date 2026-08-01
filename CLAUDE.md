# FrontendSux

A `FastAPI` subclass that auto-generates an HTML+htmx frontend for plain Python
functions. Decorate a function with `@app.expose(...)` and get: a form page
with one input per parameter (inferred from type annotations), a form-submit
route that renders the result, and a JSON API route — all from one function.

## Architecture

```
frontend_sux/
  forms.py       Type annotation <-> HTML conversions (stateless functions)
  navigation.py  Sidebar nav tree, built from registered (path, title) pairs
  app.py         FrontendSux(FastAPI) — page layout, routing, expose()
  templates.py   html_template() — load a .html file as trusted markup
  __init__.py    Public exports: FrontendSux, SupportsFormField, html_template
main.py          Example app: every @app.expose(...) route lives here
widgets/         Hand-authored .html widgets loaded via html_template()
```

`app.py` depends on `forms.py` and `navigation.py`; those two never depend on
`app.py` or on each other. Keep it that way — if a helper in `forms.py` starts
needing routing/page context, it belongs in `app.py` instead.

### `forms.py`
Pure functions mapping a Python type annotation to a rendered `<input>`
(`input_for_parameter`), a submitted form value back to a Python value
(`coerce_form_value`), and a Python value to rendered output
(`output_for_value`). `resolve_annotation` strips `Annotated[T, "Label"]` down
to `(T, "Label")`. `function_inputs` drives `input_for_parameter` across a
whole function signature.

Every one of these three type-dispatch functions (`input_for_parameter`,
`coerce_form_value`, `output_for_value`) has a branch per supported type and
raises `TypeError` on an unhandled one — **adding support for a new
parameter/return type means adding a branch to all three**, plus a test in
`tests/test_forms.py`.

Built-in types: `str`, `int`, `float`, `bool`, `date`, `datetime`, `Color`
(pydantic-extra-types), `Literal[...]` (rendered as `<select>`), and
`PIL.Image.Image` (rendered as a file input; output as a base64 `data:` URI
`<img>`). Beyond these, any type can plug in without touching `forms.py` —
see "Custom types" below.

#### The `Image` type is special-cased outside `forms.py` too

`PIL.Image.Image` isn't pydantic-compatible, so FastAPI can't bind or
serialize it directly the way it can every other supported type. `app.py`'s
`expose()` detects Image-typed parameters/return values at decoration time
and handles the JSON API route (`PUT`/`POST api_path`) itself instead of
relying on FastAPI's automatic signature binding for those fields:
- Image *parameters* are exposed to FastAPI as plain `str` query params
  (base64-encoded) and decoded back to `PIL.Image.Image` via
  `coerce_form_value` — the same function the HTML form path uses, just fed a
  base64 string instead of an `UploadFile`.
- An Image *return value* is encoded with `forms.encode_image` and returned
  as JSON `{"data": "<base64>", "content_type": "image/png"}` instead of a
  bare value.
- The HTML form path is unaffected by any of this — it already worked
  generically through `coerce_form_value`/`output_for_value`; it just also
  needs the `<form>` to be rendered with `enctype="multipart/form-data"` /
  `hx-encoding="multipart/form-data"` when an Image parameter is present, or
  the browser/htmx won't include the file's bytes in the submission.

Because plain `str` params are always bound from the query string regardless
of HTTP method (FastAPI only puts a param in the body if it's a pydantic
model or explicitly wrapped in `Body(...)`), base64 image data on the API
route travels as a query parameter, same as every other scalar type in this
project. Fine for the example app; a real API serving large images would want
an explicit `Body(...)` or a dedicated multipart API endpoint instead.

If a future built-in type needs similarly special handling (not natively
bindable/serializable by FastAPI/pydantic), follow the same pattern: keep
`forms.py`'s three functions as the single source of truth for the
conversion logic, and have `expose()` detect the type and adapt the API
route's signature/response around it — don't duplicate the conversion logic
in `app.py`.

#### Custom types (`SupportsFormField`)

App code (e.g. `main.py`) can make its own type usable as a parameter or
return type — no edits to `forms.py` — by implementing the
`SupportsFormField` protocol (`frontend_sux.SupportsFormField`, defined in
`forms.py`):

```python
class Rating:
    @classmethod
    def __form_input__(cls, name, default, label_text, *, required): ...  # -> Node
    @classmethod
    def __form_coerce__(cls, raw_value: str) -> "Rating": ...
    def __form_output__(self, label_text: str): ...  # -> Node
    def __form_encode__(self) -> str: ...  # only if used as a *return* type
```

`forms.py`'s three dispatch functions fall back to these via `hasattr` (not
`isinstance`) as their last branch before raising `TypeError` — implementing
the methods is enough, inheriting from the Protocol is optional and purely
for static type-checking. See `main.py`'s `Rating` for a full example
(`/rating/average/`).

Rules that fall out of this:
- `__form_input__`/`__form_output__` are **not** wrapped in the built-in
  `label[label_text, element]` the way built-in types are — a custom widget
  may be a group of controls (e.g. a radio-button set) where an outer
  `<label>` would be semantically wrong, so it owns its labeling entirely
  (see `Rating`'s `<fieldset><legend>`).
- `default` passed to `__form_input__` is normalized to `None` when
  `required` is `True` — never the `inspect.Parameter.empty` sentinel.
- `__form_encode__` is only required if the type is also used as a *return*
  type on some `@app.expose(...)` route — that's the only path that needs a
  string a custom type's `__form_coerce__` can parse back, since FastAPI
  can't build a JSON response model for an arbitrary custom type the way it
  can for `str`/`int`/`Color`/etc. `expose()` checks for it at decoration
  time and raises a clear `TypeError` if it's missing, rather than letting
  it fail inside FastAPI's route setup. The JSON API then returns
  `{"value": "<encoded>"}` for that route instead of the bare value.
- A custom type used only as a *parameter* doesn't need `__form_encode__` —
  it's exposed to FastAPI as a plain `str` query param on the API route
  (like Image's base64 handling) and decoded via `__form_coerce__` /
  `coerce_form_value`, same as the form path.
- Unlike Image, a custom type's `<form>` isn't automatically switched to
  `multipart/form-data` — only `PIL.Image.Image` triggers that today. A
  custom type that itself needs a file upload would need that support added
  to `app.py` alongside it.

#### `templates.py` — building a custom widget from a static `.html` file

`frontend_sux.html_template(path)` loads (and caches) a `.html` file as a
`string.Template` and returns trusted, unescaped markup via
`.substitute(**kwargs)` (backed by `markupsafe.Markup`, the same
"trusted-string" protocol Flask/Jinja2/Django use — htpy embeds anything
with `__html__()` unescaped). Use this from inside a custom type's
`__form_input__`/`__form_output__` when the widget has real HTML/CSS/JS
that's more natural to hand-author than build as nested htpy calls; use
plain htpy directly when it isn't (a custom type's hooks can freely mix
both — `Rating.__form_input__` uses `html_template`, `Rating.__form_output__`
uses htpy).

Placeholders are `$name` (not `{name}`), so they don't collide with literal
`{}`'s in embedded CSS/JS. `.substitute()` raises `KeyError` on any unfilled
placeholder rather than silently leaving it in — and there's no
loops/conditionals support (it's `string.Template`, not a real template
engine); reach for htpy directly if a widget needs those. Widget `.html`
files for the example app live in `widgets/`.

### `navigation.py`
Turns the flat list of `(path, title)` pairs the app has registered into a
nested tree (`build_page_tree`) and renders it as a `<nav><ul>` (`render_nav`).
Path segments that were never exposed themselves (e.g. `/text/` when only
`/text/uppercase/` is registered) become unlinked grouping nodes, labeled by
title-casing the URL segment (`label_for_segment`).

### `app.py`
`FrontendSux.expose(frontend_paths, title, api_path=None, method="put",
result_placement="below")` is the one decorator apps use. Per call it
registers, for each path in `frontend_paths`:
- `GET path` — the form page (inputs from `function_inputs`)
- `POST path` — form submission; renders an htmx fragment via `output_for_value`
- `PUT/POST api_path` — the same function as a plain JSON API (defaults to
  `/api` + first frontend path)

`result_placement="below"` swaps an `#output` div in place; `"replace"` swaps
the whole `#form` and appends a "Submit again" link. The decorator returns the
original undecorated function, so exposed functions stay directly callable
and testable.

## Conventions

- Every exposed function parameter and return type must be annotated;
  `Annotated[T, "Label text"]` supplies the human-readable label (falls back
  to the parameter name / "Result").
- `main.py` is both the example app and what `tests/conftest.py`'s
  `live_server_url` fixture boots for e2e tests — new example routes go there.
- Frontend paths end in `/` (e.g. `/text/uppercase/`), matching the nav
  tree's path-segment splitting.
- **Every supported form-field type and every supported return type must
  have an example route in `main.py` and a matching test in `tests/`.**
  `main.py` doubles as the type-coverage matrix — e.g. `is_palindrome`
  covers str-in/bool-out, `invert_color` covers Color-in/Color-out,
  `add_hours` covers datetime-in/int-in/datetime-out, `grayscale` covers
  Image-in/Image-out. When `forms.py` gains
  a new branch in `input_for_parameter`/`coerce_form_value`/`output_for_value`
  for a new type, add a route in `main.py` that exercises it as both a
  parameter and (if applicable) a return value, a unit test in
  `tests/test_forms.py`, and an e2e case in
  `tests/test_type_coverage_e2e.py`. This applies to `forms.py`'s built-in
  types specifically (a closed set); a one-off app-specific `SupportsFormField`
  type doesn't need this — but the extension mechanism itself does, which is
  what `main.py`'s `Rating` example + its tests are for. Keep at least one
  working example of it around; don't delete `Rating` as "unused example code."

## Tests

- `tests/test_forms.py`, `tests/test_navigation.py`, `tests/test_templates.py`
  — unit tests for the pure helpers, one file per module above.
- `tests/test_expose_integration.py` — `FrontendSux` + `TestClient`, no
  browser; covers routing, both `result_placement` modes, API vs. form
  behavior.
- `tests/test_*_e2e.py` — Playwright browser tests against the live
  `main.py` app (`live_server_url` fixture in `conftest.py`). Run with
  `uv run pytest --browser chromium` (requires `playwright install` once).

Run everything: `uv run pytest`. Run just the fast, non-browser suite:
`uv run pytest --ignore=tests/test_calculator_e2e.py --ignore=tests/test_navigation_e2e.py --ignore=tests/test_type_coverage_e2e.py`.
