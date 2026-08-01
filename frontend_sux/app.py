"""The FrontendSux FastAPI subclass: page layout, routing, and the `expose` decorator."""

from __future__ import annotations

from functools import wraps
import inspect
from typing import Literal, get_type_hints

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
)
from .navigation import render_nav


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pages: list[tuple[str, str]] = []
        self.get("/")(self._render_home)

    def _render_home(self):
        return self._render_page(
            "Home",
            hgroup[
                h1["Today's menu"],
                p["Pick a page from the navigation to get started."],
            ],
        )

    def _render_page(self, page_title: str, content):
        return HtpyResponse(
            html[
                head[
                    title[page_title],
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
    ):
        if api_path is None:
            api_path = "/api" + frontend_paths[0]

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

            if returns_custom and not hasattr(return_annotation, "__form_encode__"):
                raise TypeError(
                    f"{return_annotation!r} is the return type of {func.__name__!r} "
                    "but doesn't implement __form_encode__, which SupportsFormField "
                    "types need in order to be served from the JSON API route "
                    "(PUT/POST api_path). Add a __form_encode__(self) -> str method."
                )

            string_bound_param_names = image_param_names | custom_param_names

            if string_bound_param_names or returns_image or returns_custom:
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
                    return result

                api_wrapper.__signature__ = api_signature
            else:

                @wraps(func)
                async def api_wrapper(*args, **kwargs):
                    return func(*args, **kwargs)

            def render_form(path: str):
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
                    )[
                        div(class_="grid")[function_inputs(func)],
                        button(type="submit")["Submit"],
                    ],
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
