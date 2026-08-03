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

#### Tuple and nested-tuple return values

A function can return `tuple[...]` (fixed arity, e.g. `tuple[int, bool]`),
arbitrarily nested (`tuple[int, tuple[bool, str]]`), or the homogeneous
variadic form (`tuple[int, ...]`). `output_for_value` detects
`get_origin(annotation) is tuple` *before* its scalar branches (it's a
container, not a leaf), recurses element-by-element via
`forms.tuple_element_annotations` (which expands the `tuple[X, ...]` form to
match the runtime arity) and `resolve_annotation` (so each element can carry
its own `Annotated[T, "Label"]`), and wraps the results in a
`div(class_="grid")`. An element with no label of its own falls back to
`f"{label_text} {index + 1}"` -- so an unlabeled `tuple[int, int]` returned
from a route whose result label is "Result" renders "Result 1" / "Result 2",
and nesting composes naturally (a nested tuple's own fallback label becomes
the *parent* label the next level down falls back against).

This is deliberately **return-only** -- there's no tuple support in
`input_for_parameter`/`coerce_form_value`, unlike every other type in the
paragraph above. A tuple isn't "a type with its own widget" the way `Color`
or `Rating` is; it's a generic combinator over whatever `output_for_value`
already knows how to render, and there's no equally generic notion of "a
tuple input" to build a single HTML control for. If a real need for
structured *input* shows up later, it should get its own design rather than
retrofitting this mechanism.

`app.py`'s API route needs the parallel-but-separate concern of *JSON*
encoding (not HTML rendering) for a tuple return value, for exactly the same
reason Image/custom-type returns already needed it: pydantic can serialize
`tuple[str, int]` on its own, but not a tuple containing a
`PIL.Image.Image` or a `SupportsFormField` leaf at any depth. `app.py`
detects that case recursively (`_tuple_needs_manual_encoding`) and encodes
matching the tuple's shape (`_encode_tuple_return_value`, nested tuples ->
nested JSON arrays); the missing-`__form_encode__` decoration-time check
(`_find_type_missing_form_encode`) recurses the same way, so a custom type
nested inside a tuple return gets the same clear error as one used directly.
When *no* leaf needs manual encoding, expose() doesn't do anything special
at all -- the existing `@wraps(func)` passthrough branch already lets
FastAPI/pydantic serialize the plain tuple natively.

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
result_placement="below", submit="button")` is the one decorator apps use.
Per call it registers, for each path in `frontend_paths`:
- `GET path` — the form page (inputs from `function_inputs`)
- `POST path` — form submission; renders an htmx fragment via `output_for_value`
- `PUT/POST api_path` — the same function as a plain JSON API (defaults to
  `/api` + first frontend path)

`result_placement="below"` swaps an `#output` div in place; `"replace"` swaps
the whole `#form` and appends a "Submit again" link. The decorator returns the
original undecorated function, so exposed functions stay directly callable
and testable.

#### `submit` — how the form's request gets triggered

`submit: SubmitMode` (exported from the package root) controls what fires
the form's request and whether a "Submit" button is rendered at all;
`_submit_form_attrs` (module-level in `app.py`) is the single place that
maps a mode to (extra `<form>` attributes, show_submit_button), and is where
all validation of the mode itself happens — eagerly, in `expose()` before
`wrapper` is even defined, so a bad `submit=` value raises as soon as
`expose(...)` is called rather than waiting for the function to be invoked.

- `"button"` (default) — unchanged pre-`submit`-parameter behavior: a
  "Submit" button, htmx's implicit submit-triggered request.
- `"button-extra-confirmation"` — same, plus `hx-confirm`, which makes
  htmx run the browser's native `confirm()` before issuing the request and
  abort it entirely if the user cancels. No custom modal/JS — htmx already
  has this built in.
- `"on-change"` — no button; `hx-trigger="input delay:<N>ms"`
  (`ON_CHANGE_DEBOUNCE_MS`, currently 500) on the `<form>`. Deliberately
  `input`, not `change`: a text `<input>` only fires `change` on blur, which
  reads as "not actually live" for exactly the kind of preview this mode is
  for -- typing into a field wouldn't update anything until you clicked or
  tabbed away. `input` fires per keystroke (also for `<select>`/checkboxes
  in evergreen browsers, so one attribute on the form covers every field
  type); `delay` debounces a burst of keystrokes into one request instead of
  one per keystroke. This bubbles from any descendant input up to the form,
  so it works for however many parameters the function has, including zero.

  **Deliberately no `changed` modifier**, despite that being the more
  "obvious" htmx idiom to pair with a debounce delay -- it was there
  originally and got removed after a real bug surfaced. `changed` suppresses
  a trigger when *that specific element's* value is unchanged since it last
  fired, which is right for a text `<input>`/`<select>` (one element, one
  value) but wrong for a radio-button-based custom widget like `Rating`
  (`main.py`): its five `<input type=radio>`s share a `name`, but each has a
  *fixed* `value` ("1"-"5") that never itself changes -- only which one is
  checked does. Cycling a radio group back to a value it already visited
  (3 stars -> 5 stars -> 3 stars again) re-fires that same `value="3"`
  radio, which `changed` sees as "unchanged since it last fired" and wrongly
  suppresses, even though the group's actual selection genuinely changed.
  `input` alone doesn't have this problem (and was redundant with `changed`
  for plain text fields anyway -- it only fires on a real value change to
  begin with). See `/rating/live-average/` in `main.py` and
  `test_on_change_re_fires_when_a_radio_group_cycles_back_to_a_visited_value`
  in `tests/test_submit_modes_e2e.py` -- this can only be demonstrated with
  a real browser; a `TestClient` test can only see the static `hx-trigger=`
  string, not htmx's runtime behavior.
- `(seconds, "seconds interval")` — no button; `hx-trigger="every
  <N>ms"`. Converted to milliseconds (rounded) rather than passing seconds
  through directly, since htmx's polling trigger syntax doesn't parse
  fractional seconds — this is what lets `submit=(0.5, "seconds
  interval")` work at all. The literal second tuple element exists purely
  so a call site reads as self-documenting (`submit=(2.0, "seconds
  interval")`) without needing to check the docstring for what the float
  means; `_submit_form_attrs` still validates it's exactly that string and
  that the interval is positive.

Every mode is independent of `result_placement`/parameter/return types —
`form_submit_wrapper` (the `POST path` handler) doesn't know or care what
triggered the request that reached it.

#### `site_name` — optional site branding

`FrontendSux(site_name=...)` is `None` by default (every existing behavior
and rendered string is unchanged when omitted). When set, it's appended to
every page's `<title>` (`"{page_title} · {site_name}"`), used as both the
home page's own title and its `<h1>` (replacing the generic "Home" /
"Today's menu"), and shown as the left-hand brand in the header (below).
See a *consuming* app's `main.py` (e.g. a site built on this library) for an
example of turning it on; this library's own `main.py` leaves it unset,
since it's demonstrating the library unbranded -- the one `header_item()`
example there is what makes its own header appear at all.

#### The header, and `header_item()` for custom header menu items

Every page now renders an optional `<header class="container"><nav>...`
above `<main>`, built by `_render_header()` and only rendered at all when
there's something to put in it (`self._site_name or self._header_items`)
-- an app using neither sees no visual change and no empty bar. Two
independent things can populate it:

- **`site_name`** (above) -- rendered as `<strong>{site_name}</strong>` in
  its own `<ul>`.
- **`FrontendSux.header_item(title, content=None)`** -- a decorator
  factory, registering into `self._header_items` (rendered as a second
  `<ul>`, in registration order). It's meant to be stacked directly on top
  of `@expose(...)` (applied second/outermost, i.e. above it in source):

  ```python
  @app.header_item("Login")
  @app.expose(["/login/"], "Login")
  def login(...): ...
  ```

  `expose()` stashes the frontend path(s) it just registered onto the
  (otherwise-unwrapped) function it returns, as
  `func.__frontendsux_frontend_paths__` -- purely so a `header_item()`
  applied afterward has something to read. `header_item()` looks for that
  attribute and, if present, renders as `<a href="{first frontend path}">`;
  if absent (no `@expose(...)` underneath), it renders as plain unlinked
  text instead -- there's currently no dropdown/popover content mechanism
  for the "no page to link to" case; a real use case for one would be a
  reasonable follow-up, not something to build speculatively now.

  `content` (rendered *before* `title`) is handled exactly like any other
  HTML in this codebase -- a plain `str` is escaped, an htpy `Node` or
  `markupsafe.Markup` (e.g. from `html_template()`) is embedded as trusted
  markup -- there's no separate templating mechanism for it, matching label
  text and custom widgets.

Each group rendering "spaced apart, brand-ish stuff left, the rest right"
comes for free from Pico CSS's own `<header><nav>` convention (multiple
direct children of a `nav` space themselves apart) -- no custom CSS needed
here, consistent with how `LAYOUT_STYLE` above is kept to just the
sidebar's responsive breakpoint and nothing else.

#### The theme switcher

A light/dark/auto switcher is in the header **unconditionally, on by
default, with no way to opt out** -- unlike `site_name`/`header_items`,
nothing gates it, and `_render_header()` (above) always renders a header
now because of it. It's the last (rightmost) group.

Mechanism is Pico's own, confirmed against Pico's real docs rather than
assumed: a `data-theme="light"|"dark"` attribute on `<html>` overrides
Pico's own automatic `prefers-color-scheme`-based dark mode, which is
already zero-JS/zero-config when the attribute isn't set at all. So the
only things `FrontendSux` needs to own are (a) a UI to set/clear that
attribute, and (b) persistence across visits, since neither is Pico's job:

- **UI**: `_render_theme_switcher()` -- a `<details class="dropdown">`,
  Pico's own built-in CSS-only dropdown-menu component (already used
  elsewhere in this codebase, in the plain, non-`dropdown`-styled form, for
  the mobile nav disclosure), with three `<a data-theme-choice="...">`
  options.
- **Persistence**: plain `localStorage` (key `"theme"`), read/written by
  `THEME_SWITCHER_SCRIPT`, which also updates the summary text and closes
  the dropdown on choice, and `THEME_INIT_SCRIPT`, which reapplies a stored
  choice on every page load. `THEME_INIT_SCRIPT` specifically runs early in
  `<head>`, before the Pico stylesheet `<link>` -- applying the attribute
  after first paint would flash the OS-default theme and then immediately
  switch, for anyone who'd picked a non-default one.

`THEME_SWITCHER_SCRIPT` finds its own `<details>` via
`document.currentScript.previousElementSibling` rather than an `id`
(there's only ever one switcher per page, but this avoids needing to
invent one) -- which means the `<script>` returned alongside it from
`_render_theme_switcher()` must stay its immediate next sibling in the DOM.

**A real bug worth remembering, found and fixed while building this**:
`<script>` and `<style>` are HTML *raw text* elements -- their content
isn't reparsed as markup at all, so a literal `&#34;` sent inside one is
**not** decoded back into a `"` by the browser, it's just broken JS/CSS
syntax. htpy escapes a plain `str` child the same way regardless of the
parent tag, which is exactly correct for untrusted values (label text, a
custom type's rendered output, ...) but silently wrong for JS/CSS *we*
authored and embedded directly -- every quote in `THEME_INIT_SCRIPT`/
`THEME_SWITCHER_SCRIPT` turned into `&#34;`, which would have made both
scripts throw a syntax error and do nothing at all, caught by a
`TestClient` test asserting the literal (unescaped) source is present.
Fixed by wrapping both, and `LAYOUT_STYLE`, in `markupsafe.Markup(...)` at
definition time -- the same trusted-string path `html_template()` already
uses for hand-authored widget HTML. `LAYOUT_STYLE` itself had no
quote/`<`/`>`/`&` characters, so it was never visibly broken by the same
issue, but was fixed the same way on the theory that "was never visibly
broken" isn't "was correct" -- the next person to add a CSS child
combinator (`>`) to it would have hit the exact same failure mode.

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
- **This "example route + test" rule isn't limited to `forms.py`'s type
  dispatch — it applies to any new `expose()`/app-level capability.**
  `submit=`'s four modes, tuple/nested-tuple return values, and
  `header_item()` are three examples: none of them is a `forms.py`
  built-in type, but each mode, each return shape (flat tuple, nested
  tuple, a tuple containing a `SupportsFormField`/`Image` leaf), and each
  `header_item()` behavior (stacked-with-`expose` link, standalone
  unlinked text, plain vs. trusted `content`) still has its own route in
  `main.py` and its own test(s). Tuple support is return-only by design
  (see `forms.py`'s section above) — don't add it to
  `input_for_parameter`/`coerce_form_value` without a real driving use case.

## Commit messages

- Imperative mood, present tense ("Add tuple return support", not "Added" /
  "Adds"); summary line under ~72 characters, no trailing period.
- A body is optional but, when the *why* isn't obvious from the summary
  alone, prefer adding one over a longer summary line — wrap around 72
  columns.
- Land a capability as one commit, not split across several: when a change
  adds or alters a supported parameter/return type or an `expose()`
  capability, its `main.py` example route(s), unit test(s), and e2e case
  belong in the *same* commit as the implementation — this is the natural
  consequence of the "example route + test" convention above, not a
  separate rule to remember.
- Prefixing with a Conventional-Commits-style tag (`feat:`, `fix:`, `docs:`,
  `test:`, `chore:`, `refactor:`) is welcome when a change clearly fits one
  bucket, but isn't mandatory — don't force a tag onto a commit that's
  genuinely mixed (e.g. a bug fix discovered while adding a feature is
  still one coherent commit).

## Tests

- `tests/test_forms.py`, `tests/test_navigation.py`, `tests/test_templates.py`
  — unit tests for the pure helpers, one file per module above.
- `tests/test_expose_integration.py` — `FrontendSux` + `TestClient`, no
  browser; covers routing, both `result_placement` modes, API vs. form
  behavior.
- `tests/test_*_e2e.py` — Playwright browser tests against the live
  `main.py` app (`live_server_url` fixture in `conftest.py`). Run with
  `uv run pytest --browser chromium` (requires `playwright install` once).
  `test_submit_modes_e2e.py` specifically covers the parts of `submit=`
  that a `TestClient`-based test can't: the browser actually withholding a
  request until a confirm dialog is accepted, `on-change` firing from a
  real `change` event, and `every <N>ms` polling firing on its own without
  any interaction. `test_theme_switcher_e2e.py` is the same idea applied to
  the theme switcher -- a `TestClient` test can see the dropdown's static
  markup, but proving `localStorage` persistence (survives a reload, a
  navigation to a different page) needs a real browser actually running
  the JS.

Run everything: `uv run pytest`. Run just the fast, non-browser suite:
`uv run pytest --ignore=tests/test_calculator_e2e.py --ignore=tests/test_navigation_e2e.py --ignore=tests/test_type_coverage_e2e.py`.
