import base64
from io import BytesIO
from typing import Annotated, Literal

import pytest
from fastapi.testclient import TestClient
from htpy import input as htpy_input
from htpy import label as htpy_label
from PIL import Image

from frontend_sux import FrontendSux


def build_app(**expose_kwargs) -> FrontendSux:
    app = FrontendSux()

    @app.expose(["/greet/"], "Greet", **expose_kwargs)
    def greet(
        name: Annotated[str, "Name"],
        shout: bool = False,
    ) -> str:
        message = f"Hello, {name}!"
        return message.upper() if shout else message

    return app


class TestFrontendRoute:
    def test_get_renders_form_with_inputs_and_output_container(self):
        client = TestClient(build_app())
        response = client.get("/greet/")

        assert response.status_code == 200
        assert 'name="name"' in response.text
        assert 'name="shout"' in response.text
        assert 'id="output"' in response.text

    def test_post_below_placement_returns_fragment_for_output_div(self):
        client = TestClient(build_app())
        response = client.post("/greet/", data={"name": "Ada"})

        assert response.status_code == 200
        assert "Hello, Ada!" in response.text
        # "below" placement returns just the result fragment, no outer <html>.
        assert "<html" not in response.text

    def test_post_replace_placement_includes_resubmit_link(self):
        client = TestClient(build_app(result_placement="replace"))
        response = client.post("/greet/", data={"name": "Ada"})

        assert response.status_code == 200
        assert "Hello, Ada!" in response.text
        assert 'href="/greet/"' in response.text
        assert "Submit again" in response.text

    def test_checkbox_flag_true_when_present_in_form(self):
        client = TestClient(build_app())
        response = client.post("/greet/", data={"name": "Ada", "shout": "on"})

        assert "HELLO, ADA!" in response.text

    def test_checkbox_flag_false_when_absent_from_form(self):
        client = TestClient(build_app())
        response = client.post("/greet/", data={"name": "Ada"})

        assert "Hello, Ada!" in response.text
        assert "HELLO" not in response.text

    def test_multiple_frontend_paths_all_serve_the_same_form(self):
        app = FrontendSux()

        @app.expose(["/greet/", "/hello/"], "Greet")
        def greet(name: Annotated[str, "Name"]) -> str:
            return f"Hi, {name}!"

        client = TestClient(app)
        for path in ("/greet/", "/hello/"):
            assert client.get(path).status_code == 200
            assert "Hi, Ada!" in client.post(path, data={"name": "Ada"}).text


class TestApiRoute:
    def test_default_api_path_is_derived_from_first_frontend_path(self):
        client = TestClient(build_app())
        response = client.put("/api/greet/", params={"name": "Ada", "shout": False})

        assert response.status_code == 200
        assert response.json() == "Hello, Ada!"

    def test_custom_api_path(self):
        client = TestClient(build_app(api_path="/api/v2/greet"))
        response = client.put(
            "/api/v2/greet", params={"name": "Ada", "shout": False}
        )

        assert response.status_code == 200
        assert response.json() == "Hello, Ada!"

    def test_post_method_used_when_configured(self):
        client = TestClient(build_app(method="post"))
        response = client.post("/api/greet/", params={"name": "Ada", "shout": False})

        assert response.status_code == 200
        assert response.json() == "Hello, Ada!"

    def test_put_method_rejects_post_when_configured_as_put(self):
        client = TestClient(build_app())
        response = client.post("/api/greet/", params={"name": "Ada", "shout": False})

        assert response.status_code == 405


class TestExposeReturnsOriginalFunction:
    def test_decorator_returns_the_undecorated_function(self):
        app = FrontendSux()

        @app.expose(["/greet/"], "Greet")
        def greet(name: Annotated[str, "Name"]) -> str:
            return f"Hi, {name}!"

        assert greet(name="Ada") == "Hi, Ada!"


class TestUnsupportedTypesSurfaceErrors:
    def test_unsupported_parameter_type_raises_when_form_is_rendered(self):
        app = FrontendSux()

        @app.expose(["/broken/"], "Broken")
        def broken(payload: dict) -> str:
            return str(payload)

        client = TestClient(app)
        with pytest.raises(TypeError):
            client.get("/broken/")


def build_tree_app() -> FrontendSux:
    app = FrontendSux()

    @app.expose(["/calculator/"], "Calculator")
    def calculator(a: Annotated[int, "A"]) -> int:
        return a

    @app.expose(["/text/uppercase/"], "Uppercase")
    def uppercase(text: Annotated[str, "Text"]) -> str:
        return text.upper()

    @app.expose(["/text/reverse/"], "Reverse")
    def reverse(text: Annotated[str, "Text"]) -> str:
        return text[::-1]

    return app


class TestHomePage:
    def test_home_page_is_served_at_root(self):
        client = TestClient(build_app())
        response = client.get("/")

        assert response.status_code == 200
        assert "<html" in response.text

    def test_home_page_lists_registered_pages(self):
        client = TestClient(build_tree_app())
        response = client.get("/")

        assert 'href="/calculator/"' in response.text
        assert 'href="/text/uppercase/"' in response.text
        assert 'href="/text/reverse/"' in response.text

    def test_home_page_has_no_registered_pages_when_app_is_empty(self):
        client = TestClient(FrontendSux())
        response = client.get("/")

        assert response.status_code == 200
        assert "<nav>" in response.text
        assert "<a" not in response.text.split("<nav>")[1].split("</nav>")[0]


class TestNavOnExposedPages:
    def test_exposed_page_includes_sidebar_nav(self):
        client = TestClient(build_tree_app())
        response = client.get("/calculator/")

        assert "<nav>" in response.text
        assert "<aside" in response.text

    def test_exposed_page_links_to_sibling_pages(self):
        client = TestClient(build_tree_app())
        response = client.get("/calculator/")

        # Every page's nav lists every registered page, including itself and siblings.
        assert 'href="/calculator/"' in response.text
        assert 'href="/text/uppercase/"' in response.text
        assert 'href="/text/reverse/"' in response.text

    def test_nested_pages_are_grouped_under_shared_unlinked_parent(self):
        client = TestClient(build_tree_app())
        response = client.get("/calculator/")

        # "/text/" itself was never exposed, so it's an unlinked grouping node.
        assert "<strong>Text</strong>" in response.text
        assert 'href="/text/"' not in response.text


class TestTitleParameter:
    def build_app_with_title(self, title: str) -> FrontendSux:
        app = FrontendSux()

        @app.expose(["/word-count/"], title)
        def word_count(text: Annotated[str, "Text"]) -> int:
            return len(text.split())

        return app

    def test_page_title_tag_uses_the_title_parameter(self):
        client = TestClient(self.build_app_with_title("Count My Words"))
        response = client.get("/word-count/")

        assert "<title>Count My Words</title>" in response.text

    def test_h1_uses_the_title_parameter(self):
        client = TestClient(self.build_app_with_title("Count My Words"))
        response = client.get("/word-count/")

        assert "<h1>Count My Words</h1>" in response.text

    def test_nav_label_uses_the_title_parameter_not_the_url_segment(self):
        # The path segment is "word-count" (-> "Word Count" if derived), but
        # the explicit title should win and appear verbatim in the nav.
        client = TestClient(self.build_app_with_title("Count My Words"))
        response = client.get("/word-count/")

        assert 'href="/word-count/">Count My Words</a>' in response.text
        assert ">Word Count<" not in response.text


class TestResponsiveSidebar:
    def test_desktop_variant_is_a_plain_always_visible_nav(self):
        # No <details>/<summary> disclosure on desktop -- CSS keeps this
        # variant visible and hides the mobile one (see LAYOUT_STYLE).
        client = TestClient(build_tree_app())
        response = client.get("/calculator/")

        assert '<aside class="nav-desktop"><nav>' in response.text

    def test_mobile_variant_is_wrapped_in_a_details_disclosure_collapsed_by_default(self):
        client = TestClient(build_tree_app())
        response = client.get("/calculator/")

        assert '<aside class="nav-mobile"><details>' in response.text
        assert "<summary>Navigation</summary>" in response.text
        assert "<details open>" not in response.text

    def test_layout_is_responsive_with_sidebar_stacked_above_content_on_mobile(self):
        # Below the breakpoint the layout must collapse to a single column
        # with nav (first in DOM order) stacked above the page content, not
        # pinned as a permanent side-by-side column regardless of width.
        client = TestClient(build_tree_app())
        response = client.get("/calculator/")

        assert "grid-template-columns: 1fr;" in response.text
        assert "@media (min-width: 768px)" in response.text
        assert "grid-template-columns: auto 1fr;" in response.text


def _tiny_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (3, 3), color=(0, 255, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def build_image_app() -> FrontendSux:
    app = FrontendSux()

    @app.expose(["/image/grayscale/"], "Grayscale")
    def grayscale(photo: Annotated[Image.Image, "Photo"]) -> Image.Image:
        return photo.convert("L")

    return app


class TestImageRoutes:
    def test_frontend_form_uses_multipart_encoding(self):
        client = TestClient(build_image_app())
        response = client.get("/image/grayscale/")

        assert response.status_code == 200
        assert 'enctype="multipart/form-data"' in response.text
        assert 'type="file"' in response.text

    def test_frontend_form_submit_accepts_uploaded_file_and_renders_data_uri(self):
        client = TestClient(build_image_app())
        response = client.post(
            "/image/grayscale/",
            files={"photo": ("photo.png", BytesIO(_tiny_png_bytes()), "image/png")},
        )

        assert response.status_code == 200
        assert "data:image/png;base64," in response.text

    def test_api_route_accepts_and_returns_base64_json(self):
        client = TestClient(build_image_app())
        encoded = base64.b64encode(_tiny_png_bytes()).decode()

        response = client.put("/api/image/grayscale/", params={"photo": encoded})

        assert response.status_code == 200
        body = response.json()
        assert body["content_type"] == "image/png"
        decoded = Image.open(BytesIO(base64.b64decode(body["data"])))
        assert decoded.mode == "L"
        assert decoded.size == (3, 3)


class Rank:
    """A minimal SupportsFormField type for exercising expose()'s custom-type
    handling end to end, independent of main.py's Rating example."""

    def __init__(self, value: int):
        self.value = value

    @classmethod
    def __form_input__(cls, name, default, label_text, *, required):
        return htpy_input(type="text", name=name, required=required)

    @classmethod
    def __form_coerce__(cls, raw_value):
        return cls(int(raw_value))

    def __form_encode__(self):
        return str(self.value)

    def __form_output__(self, label_text):
        return htpy_label[f"{label_text}: ", str(self.value)]


class RankWithoutEncode:
    """Same as Rank but missing __form_encode__, to test that expose() raises
    a clear error at decoration time rather than failing inside FastAPI."""

    def __init__(self, value: int):
        self.value = value

    @classmethod
    def __form_input__(cls, name, default, label_text, *, required):
        return htpy_input(type="text", name=name, required=required)

    @classmethod
    def __form_coerce__(cls, raw_value):
        return cls(int(raw_value))

    def __form_output__(self, label_text):
        return htpy_label[f"{label_text}: ", str(self.value)]


def build_rank_app() -> FrontendSux:
    app = FrontendSux()

    @app.expose(["/rank/double/"], "Double Rank")
    def double(rank: Annotated[Rank, "Rank"]) -> Rank:
        return Rank(rank.value * 2)

    return app


class TestCustomFormFieldRoutes:
    def test_frontend_form_uses_custom_input_and_output(self):
        client = TestClient(build_rank_app())
        response = client.get("/rank/double/")

        assert response.status_code == 200
        assert 'name="rank"' in response.text

    def test_frontend_form_submit_round_trips_through_custom_coerce_and_output(self):
        client = TestClient(build_rank_app())
        response = client.post("/rank/double/", data={"rank": "3"})

        assert response.status_code == 200
        assert "Result: 6" in response.text

    def test_api_route_accepts_plain_string_and_returns_encoded_value(self):
        client = TestClient(build_rank_app())
        response = client.put("/api/rank/double/", params={"rank": "5"})

        assert response.status_code == 200
        assert response.json() == {"value": "10"}

    def test_missing_form_encode_raises_at_decoration_time(self):
        app = FrontendSux()

        with pytest.raises(TypeError, match="__form_encode__"):

            @app.expose(["/rank/broken/"], "Broken Rank")
            def broken(rank: Annotated[RankWithoutEncode, "Rank"]) -> RankWithoutEncode:
                return rank
