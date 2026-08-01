import base64
from datetime import date, datetime
from io import BytesIO
from typing import Annotated, Literal

import pytest
from htpy import input as htpy_input
from htpy import label as htpy_label
from PIL import Image
from pydantic_extra_types.color import Color
from starlette.datastructures import UploadFile

from frontend_sux.forms import (
    coerce_form_value,
    encode_image,
    function_inputs,
    input_for_parameter,
    output_for_value,
    resolve_annotation,
)


def _tiny_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (2, 2), color=(255, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


class TestResolveAnnotation:
    def test_plain_type_has_no_label(self):
        annotation, label_text = resolve_annotation(int)
        assert annotation is int
        assert label_text is None

    def test_annotated_type_extracts_label(self):
        annotation, label_text = resolve_annotation(Annotated[int, "Amount"])
        assert annotation is int
        assert label_text == "Amount"


class TestInputForParameter:
    def test_required_str_input(self):
        rendered = str(input_for_parameter("name", str))
        assert 'type="text"' in rendered
        assert "required" in rendered
        assert 'name="name"' in rendered

    def test_optional_int_input_carries_default_value(self):
        rendered = str(input_for_parameter("age", int, default=42))
        assert 'type="number"' in rendered
        assert 'value="42"' in rendered
        assert "required" not in rendered

    def test_bool_input_is_checkbox_and_reflects_default(self):
        rendered = str(input_for_parameter("flag", bool, default=True))
        assert 'type="checkbox"' in rendered
        assert 'checked="True"' in rendered

    def test_literal_input_renders_select_with_options(self):
        rendered = str(
            input_for_parameter("op", Literal["+", "-"], default="+")
        )
        assert "<select" in rendered
        assert "<option" in rendered
        assert 'selected' in rendered

    def test_color_input_type(self):
        rendered = str(input_for_parameter("shade", Color))
        assert 'type="color"' in rendered

    def test_datetime_input_type(self):
        rendered = str(input_for_parameter("when", datetime))
        assert 'type="datetime-local"' in rendered

    def test_date_input_type(self):
        rendered = str(input_for_parameter("day", date))
        assert 'type="date"' in rendered

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            input_for_parameter("thing", dict)

    def test_custom_label_text_used(self):
        rendered = str(input_for_parameter("a", int, label_text="First number"))
        assert "First number" in rendered


class TestCoerceFormValue:
    def test_bool_present_is_true(self):
        assert coerce_form_value(bool, "on") is True

    def test_bool_absent_is_false(self):
        assert coerce_form_value(bool, None) is False

    def test_str_passthrough(self):
        assert coerce_form_value(str, "hello") == "hello"

    def test_int_conversion(self):
        assert coerce_form_value(int, "42") == 42

    def test_float_conversion(self):
        assert coerce_form_value(float, "3.14") == 3.14

    def test_literal_conversion_matches_choice(self):
        assert coerce_form_value(Literal["+", "-"], "-") == "-"

    def test_color_conversion(self):
        assert coerce_form_value(Color, "#ff0000").as_hex() == "#f00"

    def test_datetime_conversion(self):
        assert coerce_form_value(datetime, "2026-08-01T12:30") == datetime(
            2026, 8, 1, 12, 30
        )

    def test_date_conversion(self):
        assert coerce_form_value(date, "2026-08-01") == date(2026, 8, 1)

    def test_non_bool_missing_value_raises(self):
        with pytest.raises(TypeError):
            coerce_form_value(int, None)

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            coerce_form_value(dict, "{}")


class TestOutputForValue:
    def test_color_output_includes_swatch(self):
        rendered = str(output_for_value(Color, Color("#ff0000")))
        assert "#f00" in rendered

    def test_bool_output_uses_check_and_cross(self):
        assert "✓" in str(output_for_value(bool, True))
        assert "✗" in str(output_for_value(bool, False))

    def test_str_int_float_output(self):
        assert "hello" in str(output_for_value(str, "hello"))
        assert "42" in str(output_for_value(int, 42))
        assert "3.14" in str(output_for_value(float, 3.14))

    def test_date_output_isoformat(self):
        rendered = str(output_for_value(date, date(2026, 8, 1)))
        assert "2026-08-01" in rendered

    def test_literal_output(self):
        rendered = str(output_for_value(Literal["+", "-"], "+"))
        assert "+" in rendered

    def test_custom_label(self):
        rendered = str(output_for_value(int, 7, label_text="Sum"))
        assert "Sum: " in rendered

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            output_for_value(dict, {})


class TestImageIO:
    def test_input_renders_required_file_input(self):
        rendered = str(input_for_parameter("photo", Image.Image))
        assert 'type="file"' in rendered
        assert 'accept="image/*"' in rendered
        assert "required" in rendered

    def test_coerce_from_uploaded_file(self):
        upload = UploadFile(BytesIO(_tiny_png_bytes()))
        image = coerce_form_value(Image.Image, upload)
        assert image.size == (2, 2)

    def test_coerce_from_base64_string(self):
        encoded = base64.b64encode(_tiny_png_bytes()).decode()
        image = coerce_form_value(Image.Image, encoded)
        assert image.size == (2, 2)

    def test_coerce_unsupported_raw_value_raises(self):
        with pytest.raises(TypeError):
            coerce_form_value(Image.Image, 123)

    def test_output_renders_data_uri(self):
        image = Image.open(BytesIO(_tiny_png_bytes()))
        rendered = str(output_for_value(Image.Image, image))
        assert "data:image/png;base64," in rendered

    def test_encode_image_round_trips(self):
        image = Image.open(BytesIO(_tiny_png_bytes()))
        data, content_type = encode_image(image)
        assert content_type == "image/png"
        decoded = Image.open(BytesIO(base64.b64decode(data)))
        assert decoded.size == (2, 2)


class Rank:
    """A fabricated type implementing SupportsFormField, used to test that
    forms.py's dispatch functions fall back to it for unrecognized types."""

    def __init__(self, value: int):
        self.value = value

    @classmethod
    def __form_input__(cls, name, default, label_text, *, required):
        return htpy_input(
            type="text", name=name, required=required, data_kind="rank"
        )

    @classmethod
    def __form_coerce__(cls, raw_value):
        return cls(int(raw_value) * 10)

    def __form_output__(self, label_text):
        return htpy_label[f"{label_text} (custom): ", str(self.value)]


class TestCustomFormField:
    def test_input_for_parameter_delegates_to_form_input_hook(self):
        rendered = str(input_for_parameter("rank", Rank))
        assert 'data-kind="rank"' in rendered
        assert "required" in rendered

    def test_input_for_parameter_does_not_get_wrapped_in_outer_label(self):
        # __form_input__ owns its own labeling; the built-in
        # label[label_text, element] wrapper must not also apply.
        rendered = str(input_for_parameter("rank", Rank, label_text="Rank"))
        assert rendered.count("<label") == 0

    def test_input_for_parameter_passes_none_default_when_required(self):
        captured = {}

        class Capturing(Rank):
            @classmethod
            def __form_input__(cls, name, default, label_text, *, required):
                captured["default"] = default
                captured["required"] = required
                return htpy_input(name=name)

        input_for_parameter("rank", Capturing)
        assert captured == {"default": None, "required": True}

    def test_coerce_form_value_delegates_to_form_coerce_hook(self):
        rank = coerce_form_value(Rank, "4")
        assert rank.value == 40

    def test_output_for_value_delegates_to_form_output_hook(self):
        rendered = str(output_for_value(Rank, Rank(7), label_text="Rank"))
        assert "Rank (custom): 7" in rendered

    def test_output_for_value_does_not_get_wrapped_twice(self):
        rendered = str(output_for_value(Rank, Rank(7), label_text="Rank"))
        assert rendered.count("<label") == 1


class TestFunctionInputs:
    def test_generates_one_input_per_parameter(self):
        def fn(a: int, b: Annotated[str, "Name"], c: bool = False):
            ...

        inputs = function_inputs(fn)
        assert len(inputs) == 3

    def test_missing_annotation_raises(self):
        def fn(a):
            ...

        with pytest.raises(TypeError):
            function_inputs(fn)
