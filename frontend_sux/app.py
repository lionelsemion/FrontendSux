"""The FrontendSux FastAPI subclass: page layout, routing, and the `expose` decorator."""

from __future__ import annotations

from functools import wraps
import inspect
from typing import Literal, get_args, get_origin, get_type_hints

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
    hgroup,
    html,
    link,
    main,
    meta,
    p,
    script,
    style,
    summary,
    title,
)
from htpy.starlette import HtpyResponse

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


def _submit_form_attrs(submit: SubmitMode) -> tuple[dict[str, str], bool]:
    """
    Translate an expose(submit=...) mode into (extra <form> attributes,
    whether to render a submit button).

    "button"                      -> htmx's default submit-triggered request, with a button.
    "button-extra-confirmation"   -> same, plus hx-confirm; a button.
    "on-change"                   -> hx-trigger="change" (bubbles up from any input's
                                      change event); no button.
    (seconds, "seconds interval") -> hx-trigger="every <ms>ms" polling; no button.
    """

    if submit == "button":
        return {}, True

    if submit == "button-extra-confirmation":
        return {"hx_confirm": "Are you sure you want to submit?"}, True

    if submit == "on-change":
        return {"hx_trigger": "change"}, False

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


LAYOUT_STYLE = """
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
"""


class FrontendSux(FastAPI):
    """A FastAPI app that can auto-generate an HTML+htmx frontend for a function."""

    def __init__(self, *args, site_name: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[tuple[str, str]] = []
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

    def _render_page(self, page_title: str, content, *, is_home: bool = False):
        # is_home skips the "· site_name" suffix below: _render_home already
        # passes site_name itself as page_title (so the home page's own
        # heading/title show the brand, not the literal word "Home"), and
        # suffixing again would double it up into "Fabric · Fabric".
        if self._site_name and not is_home:
            full_title = f"{page_title} · {self._site_name}"
        else:
            full_title = page_title
        return HtpyResponse(
            html[
                head[
                    title[full_title],
                    meta(charset="utf-8"),
                    meta(
                        name="viewport",
                        content="width=device-width, initial-scale=1",
                    ),
                    link(
                        rel="stylesheet",
                        href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css",
                    ),
                    script(src="https://unpkg.com/htmx.org@2.0.4"),
                    style[LAYOUT_STYLE],
                ],
                body[
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
                ],
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

            return func

        return wrapper
