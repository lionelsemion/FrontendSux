"""The FrontendSux FastAPI subclass: page layout, routing, and the `expose` decorator."""

from __future__ import annotations

from functools import wraps
import inspect
from typing import Any, Literal, get_args, get_origin, get_type_hints

from htpy import (
    a,
    aside,
    body,
    button,
    details,
    div,
    form,
    h1,
    head,
    header,
    hgroup,
    html,
    li,
    link,
    main,
    meta,
    nav,
    p,
    script,
    strong,
    style,
    summary,
    title,
    ul,
)
from htpy.starlette import HtpyResponse
from markupsafe import Markup

from fastapi import FastAPI, Request
from PIL import Image as PILImage

from .forms import (
    coerce_form_value,
    encode_image,
    function_inputs,
    output_for_value,
    resolve_annotation,
    tuple_element_annotations,
)
from .navigation import render_nav


SubmitMode = (
    Literal["button", "button-extra-confirmation", "on-change"]
    | tuple[float, Literal["seconds interval"]]
)

ON_CHANGE_DEBOUNCE_MS = 500


def _submit_form_attrs(submit: SubmitMode) -> tuple[dict[str, str], bool]:
    """
    Translate an expose(submit=...) mode into (extra <form> attributes,
    whether to render a submit button).

    "button"                      -> htmx's default submit-triggered request, with a button.
    "button-extra-confirmation"   -> same, plus hx-confirm; a button.
    "on-change"                   -> hx-trigger="input delay:<N>ms"; no button.
    (seconds, "seconds interval") -> hx-trigger="every <ms>ms" polling; no button.
    """

    if submit == "button":
        return {}, True

    if submit == "button-extra-confirmation":
        return {"hx_confirm": "Are you sure you want to submit?"}, True

    if submit == "on-change":
        # "input" (not "change") so text fields update as you type rather than
        # only on blur -- browsers fire "change" for a text <input> only when
        # it loses focus, which reads as "not actually live" for exactly the
        # kind of preview this mode exists for. "delay" debounces a burst of
        # keystrokes into one request instead of one per keystroke. "input"
        # fires for <select>/checkboxes too in evergreen browsers, so one
        # trigger spec covers every field type a form can contain.
        #
        # Deliberately no "changed" modifier: it suppresses a trigger when
        # *that specific element's* value is unchanged since it last fired --
        # correct for a text <input>/<select> (one element, one value), but
        # wrong for a radio-button-based custom widget like Rating (multiple
        # <input>s sharing a name, each with a fixed, distinct value that
        # never itself changes -- only which one is checked does). Cycling a
        # radio group back to a value it already visited once (e.g. 3 stars
        # -> 5 stars -> 3 stars again) re-fires that same <input value="3">,
        # which "changed" would wrongly suppress as "unchanged" even though
        # the group's selection genuinely changed. "input" alone doesn't have
        # this problem, and is redundant with "changed" for plain text fields
        # anyway (it only ever fires on an actual value change to begin with).
        return {"hx_trigger": f"input delay:{ON_CHANGE_DEBOUNCE_MS}ms"}, False

    if isinstance(submit, tuple):
        seconds, tag = submit
        if tag != "seconds interval":
            raise ValueError(
                f"Unsupported submit mode: {submit!r}. A tuple must be "
                '(seconds, "seconds interval").'
            )
        if not seconds > 0:
            raise ValueError(
                f"submit interval must be a positive number of seconds, got {seconds!r}"
            )
        return {"hx_trigger": f"every {round(seconds * 1000)}ms"}, False

    raise ValueError(f"Unsupported submit mode: {submit!r}")


def _tuple_needs_manual_encoding(annotation: type) -> bool:
    """
    Whether a tuple return annotation contains, at any depth, a leaf type
    FastAPI/pydantic can't natively serialize (PIL.Image.Image or a
    SupportsFormField type) -- and therefore needs expose()'s manual JSON
    encoding on the API route instead of relying on FastAPI's automatic
    response model.
    """

    for raw_element_annotation in get_args(annotation):
        if raw_element_annotation is Ellipsis:
            continue
        element_annotation, _ = resolve_annotation(raw_element_annotation)
        if get_origin(element_annotation) is tuple:
            if _tuple_needs_manual_encoding(element_annotation):
                return True
        elif element_annotation is PILImage.Image or hasattr(
            element_annotation, "__form_output__"
        ):
            return True
    return False


def _encode_tuple_return_value(annotation: type, value: tuple) -> list:
    """
    Recursively encode a tuple return value for the JSON API route: nested
    tuples become nested JSON arrays, Image/SupportsFormField leaves are
    encoded the same way they would be alone (see expose()'s api_wrapper),
    and any other leaf passes through as-is (already natively serializable).
    """

    element_annotations = tuple_element_annotations(annotation, len(value))
    encoded = []
    for raw_element_annotation, element_value in zip(element_annotations, value):
        element_annotation, _ = resolve_annotation(raw_element_annotation)
        if get_origin(element_annotation) is tuple:
            encoded.append(_encode_tuple_return_value(element_annotation, element_value))
        elif element_annotation is PILImage.Image:
            data, content_type = encode_image(element_value)
            encoded.append({"data": data, "content_type": content_type})
        elif hasattr(element_annotation, "__form_output__"):
            encoded.append(element_value.__form_encode__())
        else:
            encoded.append(element_value)
    return encoded


def _find_type_missing_form_encode(annotation: type) -> type | None:
    """
    Recursively find a return-type leaf that implements __form_output__ (so
    forms.output_for_value can render it) but not __form_encode__ (so the
    JSON API route has no way to serialize it) -- at the top level or nested
    inside a tuple return annotation. Returns the offending type, or None if
    every such leaf is properly encodable.
    """

    if get_origin(annotation) is tuple:
        for raw_element_annotation in get_args(annotation):
            if raw_element_annotation is Ellipsis:
                continue
            element_annotation, _ = resolve_annotation(raw_element_annotation)
            found = _find_type_missing_form_encode(element_annotation)
            if found is not None:
                return found
        return None
    if hasattr(annotation, "__form_output__") and not hasattr(annotation, "__form_encode__"):
        return annotation
    return None


LAYOUT_STYLE = Markup("""
.layout {
    display: grid;
    grid-template-columns: 1fr;
    gap: 1rem;
}
.nav-desktop {
    display: none;
}
@media (min-width: 768px) {
    .layout {
        grid-template-columns: auto 1fr;
        gap: 2rem;
    }
    .nav-desktop {
        display: block;
    }
    .nav-mobile {
        display: none;
    }
}
/* Pico gives body>header its usual padding-block (~1rem), same as
   body>main -- fine for main, since there's enough content mass under it
   that 1rem doesn't read as cramped, but a thin single-line nav bar sitting
   right at the very top of the viewport with that same 1rem looks glued to
   the edge. Only the top side needs it; the existing bottom padding already
   separates the header from main reasonably. */
body > header {
    padding-block-start: 2rem;
}
/* Pico's nav has no align-items of its own (flex default: stretch), and
   compensates by centering *within* each nav>ul itself (nav ul has
   align-items:center) -- fine for the site_name/header_items groups, which
   are <ul>s, but the theme switcher's <details> isn't one, so it just gets
   stretched with nothing centering its own content, leaving it visually
   off-center against the <ul> groups beside it. Centering the whole nav
   directly fixes the <details> case without needing to fake it into a <ul>
   just to inherit Pico's own centering rule. */
header > nav {
    align-items: center;
}
""")

# Runs in <head>, before the stylesheet, so a stored preference is applied
# before first paint -- otherwise the page would flash the OS-default theme
# and then immediately switch, for anyone who picked a non-default one.
# Pico applies dark mode automatically from prefers-color-scheme on its own
# when data-theme isn't set at all, so this only has anything to do when a
# stored override exists.
#
# Wrapped in Markup (like LAYOUT_STYLE above): <script>/<style> are HTML
# "raw text" elements, so a literal &#34; sent inside one isn't decoded back
# into a `"` by the browser the way it would be in normal element content --
# it's just broken JS/CSS syntax. htpy's default escaping is exactly right
# for untrusted values (Rating's label text, etc.); code we authored
# ourselves needs the trusted-string path instead, the same one
# html_template() already uses for hand-authored widget HTML.
THEME_INIT_SCRIPT = Markup("""
(function () {
    var stored = localStorage.getItem("theme");
    if (stored) {
        document.documentElement.setAttribute("data-theme", stored);
    }
})();
""")

# Paired with _render_theme_switcher()'s <details> -- uses
# document.currentScript.previousElementSibling to find it, so this script
# element must immediately follow it in the DOM (see where it's used).
THEME_SWITCHER_SCRIPT = Markup("""
(function () {
    var switcher = document.currentScript.previousElementSibling;
    var summary = switcher.querySelector("summary");
    var label = function (choice) {
        return "Theme: " + choice.charAt(0).toUpperCase() + choice.slice(1);
    };
    summary.textContent = label(localStorage.getItem("theme") || "auto");
    switcher.querySelectorAll("[data-theme-choice]").forEach(function (link) {
        link.addEventListener("click", function (event) {
            event.preventDefault();
            var choice = link.getAttribute("data-theme-choice");
            if (choice === "auto") {
                document.documentElement.removeAttribute("data-theme");
                localStorage.removeItem("theme");
            } else {
                document.documentElement.setAttribute("data-theme", choice);
                localStorage.setItem("theme", choice);
            }
            summary.textContent = label(choice);
            switcher.removeAttribute("open");
        });
    });
})();
""")


class FrontendSux(FastAPI):
    """A FastAPI app that can auto-generate an HTML+htmx frontend for a function."""

    def __init__(self, *args, site_name: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[tuple[str, str]] = []
        self._header_items: list[tuple[str, str | None, Any]] = []
        self._site_name = site_name
        self.get("/")(self._render_home)

    def _render_home(self):
        return self._render_page(
            self._site_name or "Home",
            hgroup[
                h1[self._site_name or "Today's menu"],
                p["Pick a page from the navigation to get started."],
            ],
            is_home=True,
        )

    def _render_header_item(self, item: tuple[str, str | None, Any]):
        title_text, href, item_content = item
        children = [item_content, title_text] if item_content is not None else [title_text]
        if href:
            return li[a(href=href)[children]]
        # No matching @expose(...) was stacked under this header_item -- there's
        # no page to link to, so it renders as plain, unlinked text/content.
        return li[children]

    def _render_theme_switcher(self):
        # A <details class="dropdown"> is Pico's own built-in dropdown-menu
        # component -- CSS-driven positioning/visibility, no JS needed for
        # that part. "Theme: Auto" is just the initial server-rendered guess;
        # THEME_SWITCHER_SCRIPT corrects it from localStorage immediately
        # after (and it must stay its immediate next sibling -- see there).
        return [
            details(class_="dropdown")[
                summary["Theme: Auto"],
                ul[
                    li[a(href="#", data_theme_choice="light")["Light"]],
                    li[a(href="#", data_theme_choice="dark")["Dark"]],
                    li[a(href="#", data_theme_choice="auto")["Auto"]],
                ],
            ],
            script[THEME_SWITCHER_SCRIPT],
        ]

    def _render_header(self):
        # Pico CSS's own convention for a <header><nav>: each direct <ul>
        # child of the nav is its own group, the first flush left and any
        # further ones pushed right -- exactly "brand on the left, menu
        # items on the right" with no custom CSS of our own needed. The
        # theme switcher is always the last group (rightmost), and always
        # present -- unlike site_name/header_items, it's on by default with
        # no way to opt out (nothing has asked for one yet).
        groups = []
        if self._site_name:
            groups.append(ul[li[strong[self._site_name]]])
        if self._header_items:
            groups.append(ul[[self._render_header_item(item) for item in self._header_items]])
        groups.append(self._render_theme_switcher())

        return header(class_="container")[nav[groups]]

    def _render_page(self, page_title: str, content, *, is_home: bool = False):
        # is_home skips the "· site_name" suffix below: _render_home already
        # passes site_name itself as page_title (so the home page's own
        # heading/title show the brand, not the literal word "Home"), and
        # suffixing again would double it up into "Fabric · Fabric".
        if self._site_name and not is_home:
            full_title = f"{page_title} · {self._site_name}"
        else:
            full_title = page_title

        body_children = [
            self._render_header(),
        ]
        body_children.append(
            main(class_="container")[
                div(class_="layout")[
                    # Two variants, CSS-switched by viewport width (see
                    # LAYOUT_STYLE): a persistent sidebar on desktop and a
                    # <details>-based disclosure — collapsed by default —
                    # on mobile. A single element can't have a different
                    # default open/closed state per breakpoint, so this
                    # is duplicated rather than reused; whichever one is
                    # display:none is excluded from the accessibility
                    # tree, so there's only ever one "Navigation" landmark
                    # exposed at a time.
                    aside(class_="nav-desktop")[render_nav(self._pages)],
                    aside(class_="nav-mobile")[
                        details[
                            summary["Navigation"],
                            render_nav(self._pages),
                        ]
                    ],
                    div[content],
                ]
            ]
        )

        return HtpyResponse(
            html[
                head[
                    title[full_title],
                    meta(charset="utf-8"),
                    meta(
                        name="viewport",
                        content="width=device-width, initial-scale=1",
                    ),
                    script[THEME_INIT_SCRIPT],
                    link(
                        rel="stylesheet",
                        href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css",
                    ),
                    script(src="https://unpkg.com/htmx.org@2.0.4"),
                    style[LAYOUT_STYLE],
                ],
                body[body_children],
            ]
        )

    def expose(
        self,
        frontend_paths: list[str],
        title: str,
        api_path: str | None = None,
        method: Literal["put", "post"] = "put",
        result_placement: Literal["replace", "below"] = "below",
        submit: SubmitMode = "button",
    ):
        if api_path is None:
            api_path = "/api" + frontend_paths[0]

        form_attrs, show_submit_button = _submit_form_attrs(submit)

        def wrapper(func):
            signature = inspect.signature(func)
            hints = get_type_hints(func, include_extras=True)

            return_annotation = hints.get("return", signature.return_annotation)
            return_annotation, return_label = resolve_annotation(return_annotation)
            return_label = return_label or "Result"

            # Parameters/returns whose (resolved) annotation FastAPI/pydantic can't
            # bind or serialize on its own: PIL.Image.Image (a built-in special
            # case) and any type implementing the SupportsFormField protocol.
            image_param_names = {
                name
                for name, parameter in signature.parameters.items()
                if resolve_annotation(hints.get(name, parameter.annotation))[0]
                is PILImage.Image
            }
            custom_param_names = {
                name
                for name, parameter in signature.parameters.items()
                if hasattr(
                    resolve_annotation(hints.get(name, parameter.annotation))[0],
                    "__form_coerce__",
                )
            }
            returns_image = return_annotation is PILImage.Image
            returns_custom = hasattr(return_annotation, "__form_output__")
            returns_tuple_requiring_encoding = get_origin(
                return_annotation
            ) is tuple and _tuple_needs_manual_encoding(return_annotation)

            missing_encode_type = _find_type_missing_form_encode(return_annotation)
            if missing_encode_type is not None:
                raise TypeError(
                    f"{missing_encode_type!r} is used as (part of) the return type of "
                    f"{func.__name__!r} but doesn't implement __form_encode__, which "
                    "SupportsFormField types need in order to be served from the JSON "
                    "API route (PUT/POST api_path). Add a __form_encode__(self) -> str method."
                )

            string_bound_param_names = image_param_names | custom_param_names

            if (
                string_bound_param_names
                or returns_image
                or returns_custom
                or returns_tuple_requiring_encoding
            ):
                # These params are exposed to FastAPI as plain strings (decoded via
                # coerce_form_value, the same helper the form path uses) and an
                # Image/custom return value is JSON-encoded instead of passed
                # through as-is, since FastAPI can't build a response model for
                # either directly.
                api_signature = signature.replace(
                    parameters=[
                        parameter.replace(annotation=str)
                        if name in string_bound_param_names
                        else parameter
                        for name, parameter in signature.parameters.items()
                    ],
                    return_annotation=dict
                    if (returns_image or returns_custom)
                    else list
                    if returns_tuple_requiring_encoding
                    else signature.return_annotation,
                )

                async def api_wrapper(**kwargs):
                    for name in string_bound_param_names:
                        annotation = resolve_annotation(
                            hints.get(name, signature.parameters[name].annotation)
                        )[0]
                        kwargs[name] = coerce_form_value(annotation, kwargs[name])
                    result = func(**kwargs)
                    if returns_image:
                        data, content_type = encode_image(result)
                        return {"data": data, "content_type": content_type}
                    if returns_custom:
                        return {"value": result.__form_encode__()}
                    if returns_tuple_requiring_encoding:
                        return _encode_tuple_return_value(return_annotation, result)
                    return result

                api_wrapper.__signature__ = api_signature
            else:

                @wraps(func)
                async def api_wrapper(*args, **kwargs):
                    return func(*args, **kwargs)

            def render_form(path: str):
                form_children = [div(class_="grid")[function_inputs(func)]]
                if show_submit_button:
                    form_children.append(button(type="submit")["Submit"])

                content = [
                    h1[title],
                    form(
                        id="form",
                        hx_post=path,
                        hx_target="this" if result_placement == "replace" else "#output",
                        hx_swap="outerHTML"
                        if result_placement == "replace"
                        else "innerHTML",
                        enctype="multipart/form-data" if image_param_names else None,
                        hx_encoding="multipart/form-data" if image_param_names else None,
                        **form_attrs,
                    )[form_children],
                ]

                if result_placement == "below":
                    content.append(div(id="output"))

                return self._render_page(title, content)

            async def form_submit_wrapper(request: Request) -> HtpyResponse:
                form_data = await request.form()

                kwargs = {}
                for name, parameter in signature.parameters.items():
                    annotation = hints.get(name, parameter.annotation)
                    annotation, _ = resolve_annotation(annotation)
                    kwargs[name] = coerce_form_value(annotation, form_data.get(name))

                result = func(**kwargs)
                fragment = output_for_value(return_annotation, result, return_label)

                if result_placement == "replace":
                    fragment = div(class_="grid")[
                        fragment,
                        a(href=frontend_paths[0])["↺ Submit again"],
                    ]

                return HtpyResponse(fragment)

            {"put": self.put, "post": self.post}[method](api_path)(api_wrapper)

            self._pages.append((frontend_paths[0], title))

            for path in frontend_paths:
                self.get(path)(lambda path=path: render_form(path))
                self.post(path)(form_submit_wrapper)

            # Read by header_item(), when stacked on top of this decorator, to
            # link a header item at the page this function was just exposed at
            # -- see header_item()'s docstring for the stacking order this
            # relies on.
            func.__frontendsux_frontend_paths__ = tuple(frontend_paths)

            return func

        return wrapper

    def header_item(self, title: str, content: Any = None):
        """
        Register an item in the site header (a <header><nav> rendered above
        every page, alongside site_name -- see FrontendSux.__init__ -- and
        separate from the sidebar nav built from expose()'d pages).

        Stack on top of @expose(...) -- apply header_item as the *outer*
        decorator, i.e. closest to the def -- to turn it into a link to that
        page:

            @app.header_item("Login")
            @app.expose(["/login/"], "Login")
            def login(...): ...

        This relies on decorator application order: Python applies
        @app.expose(...) first (it's innermost), which registers the page
        and returns the original function with its frontend path(s) stashed
        on it; @app.header_item(...) then reads that back. Order matters --
        header_item has nothing to find if it runs first.

        Used without a matching @expose(...) underneath, a header item
        currently renders as plain, unlinked text -- there's no
        dropdown/popover content mechanism yet; that would be a reasonable
        follow-up if a real use case for one shows up.

        `content` renders *before* the title and is handled exactly like any
        other HTML in this codebase: a plain str is escaped, while an htpy
        Node or markupsafe.Markup (e.g. from html_template()) is embedded as
        trusted markup -- there's no separate templating mechanism for it,
        matching how label text and custom widgets already work.
        """

        def decorator(func):
            frontend_paths = getattr(func, "__frontendsux_frontend_paths__", None)
            href = frontend_paths[0] if frontend_paths else None
            self._header_items.append((title, href, content))
            return func

        return decorator
