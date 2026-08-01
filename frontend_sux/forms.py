"""Conversions between Python type annotations and HTML form inputs/outputs."""

from __future__ import annotations

import base64
from datetime import date, datetime
from io import BytesIO
import inspect
from typing import Annotated, Any, Literal, Protocol, get_args, get_origin, get_type_hints, runtime_checkable

from htpy import div, img, input, label, option, select
from PIL import Image as PILImage
from pydantic_extra_types.color import Color
from starlette.datastructures import UploadFile


@runtime_checkable
class SupportsFormField(Protocol):
    """
    Optional protocol a type can implement to plug into input_for_parameter /
    coerce_form_value / output_for_value without those functions knowing
    about it. Dispatch uses hasattr, not isinstance, so implementing these
    methods is enough — inheriting from this Protocol is only for
    documentation/type-checking, never required.
    """

    @classmethod
    def __form_input__(
        cls, name: str, default: Any, label_text: str, *, required: bool
    ):
        """Render an <input>-like Node. `default` is None when `required`."""
        ...

    @classmethod
    def __form_coerce__(cls, raw_value: Any) -> "SupportsFormField":
        """Build an instance from a submitted form/query value."""
        ...

    def __form_output__(self, label_text: str):
        """Render this value as an output Node."""
        ...

    def __form_encode__(self) -> str:
        """
        Encode this instance back to a string __form_coerce__ can parse.

        Optional — only required if the type is also used as a *return*
        type on an exposed route. PIL.Image.Image/str/int/etc. all get a
        native JSON representation FastAPI can build a response model from;
        an arbitrary custom type doesn't, so app.py's JSON API route falls
        back to this to serve it as {"value": <encoded>}. expose() raises a
        clear error at decoration time if this is missing where needed,
        instead of leaving it to fail inside FastAPI's route setup.
        """
        ...


def encode_image(image: PILImage.Image) -> tuple[str, str]:
    """Encode a PIL image to (base64_data, content_type), e.g. ("iVBOR...", "image/png")."""

    image_format = image.format or "PNG"
    buffer = BytesIO()
    image.save(buffer, format=image_format)
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return data, f"image/{image_format.lower()}"


def resolve_annotation(annotation):
    """Strip Annotated[...] down to (bare_type, label_or_None)."""

    label_text = None

    if get_origin(annotation) is Annotated:
        annotation, *metadata = get_args(annotation)
        if metadata:
            label_text = metadata[0]

    return annotation, label_text


def input_for_parameter(
    name: str,
    annotation: type,
    default: Any = inspect.Parameter.empty,
    label_text: str | None = None,
):
    if label_text is None:
        label_text = name

    attrs = {"name": name}

    required = default is inspect.Parameter.empty

    if not required:
        if isinstance(default, bool):
            attrs["checked"] = str(default)
        elif default is not None:
            attrs["value"] = str(default)

    if get_origin(annotation) is Literal:
        choices = get_args(annotation)
        element = select(
            name=name,
            required=required,
        )[
            [
                option(
                    value=str(choice),
                    selected=not required and choice == default,
                )[str(choice)]
                for choice in choices
            ]
        ]
    elif annotation is str:
        element = input(
            type="text",
            required=required,
            **attrs,
        )
    elif annotation is int:
        element = input(
            type="number",
            step="1",
            required=required,
            **attrs,
        )
    elif annotation is float:
        element = input(
            type="number",
            step="any",
            required=required,
            **attrs,
        )
    elif annotation is Color:
        element = input(
            type="color",
            required=required,
            **attrs,
        )
    elif annotation is datetime:
        element = input(
            type="datetime-local",
            required=required,
            **attrs,
        )
    elif annotation is date:
        element = input(
            type="date",
            required=required,
            **attrs,
        )
    elif annotation is bool:
        # Checkboxes conventionally go input-then-text (<input> Text), the
        # reverse of every other input type here -- both visually (Pico's
        # checkbox spacing assumes that order) and semantically. Early
        # return instead of falling through to the label_text-then-element
        # wrap below.
        element = input(
            type="checkbox",
            required=required,
            **attrs,
        )
        return label[element, " ", label_text]
    elif annotation is PILImage.Image:
        # File inputs can't carry a default value, so `attrs` (value/checked) is unused here.
        element = input(
            type="file",
            accept="image/*",
            required=required,
            name=name,
        )
    elif hasattr(annotation, "__form_input__"):
        # Unlike the built-in branches, this isn't wrapped in an outer
        # label[label_text, ...] below — a custom widget may be a group of
        # controls (e.g. radio buttons) where an outer <label> would be
        # semantically wrong, so it owns its own labeling entirely.
        return annotation.__form_input__(
            name=name,
            default=None if required else default,
            label_text=label_text,
            required=required,
        )
    else:
        raise TypeError(f"Unsupported parameter type: {annotation}")

    return label[label_text, element]


def coerce_form_value(annotation: type, raw_value: Any):
    if annotation is bool:
        return raw_value is not None

    if annotation is PILImage.Image:
        # Multipart form submissions hand us an UploadFile; the JSON API route
        # (which has no native file upload) hands us a base64-encoded string instead.
        if isinstance(raw_value, UploadFile):
            raw_bytes = raw_value.file.read()
        elif isinstance(raw_value, str):
            raw_bytes = base64.b64decode(raw_value)
        else:
            raise TypeError(
                f"Expected an uploaded file or a base64 string, got {raw_value!r}"
            )
        return PILImage.open(BytesIO(raw_bytes))

    if hasattr(annotation, "__form_coerce__"):
        return annotation.__form_coerce__(raw_value)

    if not isinstance(raw_value, str):
        raise TypeError(f"Expected a form field value, got {raw_value!r}")

    if get_origin(annotation) is Literal:
        choices = get_args(annotation)
        return next(choice for choice in choices if str(choice) == raw_value)

    if annotation is str:
        return raw_value

    if annotation is int:
        return int(raw_value)

    if annotation is float:
        return float(raw_value)

    if annotation is Color:
        return Color(raw_value)

    if annotation is datetime:
        return datetime.fromisoformat(raw_value)

    if annotation is date:
        return date.fromisoformat(raw_value)

    raise TypeError(f"Unsupported parameter type: {annotation}")


def output_for_value(annotation: type, value: Any, label_text: str = "Result"):
    if annotation is Color:
        swatch = value.as_hex()
        element = div(style="display:flex; align-items:center; gap:0.5rem;")[
            div(
                style=f"width:1.5rem; height:1.5rem; border-radius:4px; "
                f"background-color:{swatch};"
            ),
            swatch,
        ]
    elif annotation is bool:
        element = "✓" if value else "✗"
    elif annotation is str or annotation is int or annotation is float:
        element = str(value)
    elif annotation is datetime or annotation is date:
        element = value.isoformat()
    elif get_origin(annotation) is Literal:
        element = str(value)
    elif annotation is PILImage.Image:
        data, content_type = encode_image(value)
        element = img(src=f"data:{content_type};base64,{data}", alt=label_text)
    elif hasattr(annotation, "__form_output__"):
        # Also unwrapped, for the same reason as __form_input__ above.
        return value.__form_output__(label_text)
    else:
        raise TypeError(f"Unsupported return type: {annotation}")

    return label[f"{label_text}: ", element]


def function_inputs(fn):
    """
    Generate HTPy inputs for a function's parameters.

    Uses:
      - annotations for input type
      - defaults for initial values
      - missing defaults for required fields
    """

    signature = inspect.signature(fn)
    hints = get_type_hints(fn, include_extras=True)

    inputs = []

    for name, parameter in signature.parameters.items():
        annotation = hints.get(name, parameter.annotation)

        if annotation is inspect.Parameter.empty:
            raise TypeError(f"Parameter {name!r} has no type annotation")

        annotation, label_text = resolve_annotation(annotation)

        inputs.append(
            input_for_parameter(
                name=name,
                annotation=annotation,
                default=parameter.default,
                label_text=label_text or name,
            )
        )

    return inputs
