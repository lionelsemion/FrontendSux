import base64
from io import BytesIO
from typing import Annotated, Literal

import pytest
from fastapi.testclient import TestClient
from htpy import input as htpy_input
from htpy import label as htpy_label
from htpy import strong as htpy_strong
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


class TestSubmitModes:
    def test_default_is_button_with_no_special_trigger(self):
        client = TestClient(build_app())
        response = client.get("/greet/")

        assert "<button" in response.text
        assert "hx-trigger" not in response.text
        assert "hx-confirm" not in response.text

    def test_button_extra_confirmation_keeps_button_and_adds_hx_confirm(self):
        client = TestClient(build_app(submit="button-extra-confirmation"))
        response = client.get("/greet/")

        assert "<button" in response.text
        assert 'hx-confirm="Are you sure you want to submit?"' in response.text

    def test_on_change_hides_button_and_triggers_debounced_input_event(self):
        client = TestClient(build_app(submit="on-change"))
        response = client.get("/greet/")

        assert "<button" not in response.text
        assert 'hx-trigger="input delay:500ms"' in response.text

    def test_interval_hides_button_and_triggers_every_n_milliseconds(self):
        client = TestClient(build_app(submit=(2.5, "seconds interval")))
        response = client.get("/greet/")

        assert "<button" not in response.text
        assert 'hx-trigger="every 2500ms"' in response.text

    def test_post_route_behavior_is_unaffected_by_submit_mode(self):
        client = TestClient(build_app(submit="on-change"))
        response = client.post("/greet/", data={"name": "Ada"})

        assert "Hello, Ada!" in response.text

    def test_invalid_interval_tag_raises_at_decoration_time(self):
        app = FrontendSux()

        with pytest.raises(ValueError, match="seconds interval"):

            @app.expose(["/broken/"], "Broken", submit=(1.0, "wrong tag"))
            def broken() -> str:
                return "x"

    def test_non_positive_interval_raises_at_decoration_time(self):
        app = FrontendSux()

        with pytest.raises(ValueError, match="positive"):

            @app.expose(["/broken/"], "Broken", submit=(0, "seconds interval"))
            def broken() -> str:
                return "x"

    def test_unsupported_submit_mode_raises_at_decoration_time(self):
        app = FrontendSux()

        with pytest.raises(ValueError, match="Unsupported submit mode"):

            @app.expose(["/broken/"], "Broken", submit="click-really-hard")
            def broken() -> str:
                return "x"


class TestSiteName:
    def test_no_site_name_leaves_title_unchanged(self):
        client = TestClient(build_app())
        response = client.get("/greet/")

        assert "<title>Greet</title>" in response.text

    def test_site_name_is_appended_to_every_page_title(self):
        app = FrontendSux(site_name="Fabric")

        @app.expose(["/greet/"], "Greet")
        def greet(name: Annotated[str, "Name"]) -> str:
            return f"Hi, {name}!"

        client = TestClient(app)
        response = client.get("/greet/")

        assert "<title>Greet · Fabric</title>" in response.text

    def test_site_name_used_as_home_heading(self):
        client = TestClient(FrontendSux(site_name="Fabric"))
        response = client.get("/")

        assert "<h1>Fabric</h1>" in response.text

    def test_site_name_is_not_duplicated_in_the_home_page_title(self):
        # The home page already uses site_name as its own page_title (for the
        # heading above) -- _render_page must not *also* suffix "· site_name"
        # on top of that, or the title tag would read "Fabric · Fabric".
        client = TestClient(FrontendSux(site_name="Fabric"))
        response = client.get("/")

        assert "<title>Fabric</title>" in response.text
        assert "Fabric · Fabric" not in response.text

    def test_default_home_heading_unchanged_without_site_name(self):
        client = TestClient(FrontendSux())
        response = client.get("/")

        assert "<h1>Today&#39;s menu</h1>" in response.text


class TestHeader:
    def test_header_still_renders_for_the_theme_switcher_alone(self):
        # The header itself is unconditional now (the theme switcher is
        # on by default, with no opt-out), even though the brand/menu-item
        # groups inside it are still conditional.
        client = TestClient(build_app())
        response = client.get("/greet/")

        assert "<header" in response.text
        assert '<details class="dropdown">' in response.text
        assert "<strong>" not in response.text

    def test_header_renders_with_only_site_name_set(self):
        client = TestClient(FrontendSux(site_name="Fabric"))
        response = client.get("/")

        assert "<header" in response.text
        assert "<strong>Fabric</strong>" in response.text

    def test_header_item_stacked_with_expose_renders_as_a_link_to_that_page(self):
        app = FrontendSux()

        @app.header_item("Login")
        @app.expose(["/login/"], "Login")
        def login() -> str:
            return "Welcome"

        client = TestClient(app)
        response = client.get("/login/")

        assert '<header' in response.text
        assert '<a href="/login/">Login</a>' in response.text

    def test_header_item_without_a_matching_expose_renders_unlinked(self):
        app = FrontendSux()

        @app.header_item("Just Text")
        def not_exposed():
            pass

        client = TestClient(app)
        response = client.get("/")

        assert "<li>Just Text</li>" in response.text
        assert '<a href="/login/">Just Text</a>' not in response.text

    def test_header_item_content_renders_before_the_title(self):
        app = FrontendSux()

        @app.header_item("Login", content="* ")
        @app.expose(["/login/"], "Login")
        def login() -> str:
            return "Welcome"

        client = TestClient(app)
        response = client.get("/login/")

        assert '<a href="/login/">* Login</a>' in response.text

    def test_header_item_string_content_is_escaped(self):
        app = FrontendSux()

        @app.header_item("Login", content="<script>")
        @app.expose(["/login/"], "Login")
        def login() -> str:
            return "Welcome"

        client = TestClient(app)
        response = client.get("/login/")

        # A positive check on the exact escaped rendering, not just "no raw
        # <script> anywhere in the page" -- the page legitimately contains a
        # real <script> tag elsewhere now (the theme switcher's).
        assert '<a href="/login/">&lt;script&gt;Login</a>' in response.text
        assert "&lt;script&gt;" in response.text

    def test_header_item_trusted_markup_content_is_embedded_unescaped(self):
        app = FrontendSux()

        @app.header_item("Login", content=htpy_strong["VIP"])
        @app.expose(["/login/"], "Login")
        def login() -> str:
            return "Welcome"

        client = TestClient(app)
        response = client.get("/login/")

        assert "<strong>VIP</strong>Login" in response.text

    def test_multiple_header_items_render_in_registration_order(self):
        app = FrontendSux()

        @app.header_item("First")
        @app.expose(["/first/"], "First")
        def first() -> str:
            return "x"

        @app.header_item("Second")
        @app.expose(["/second/"], "Second")
        def second() -> str:
            return "x"

        client = TestClient(app)
        response = client.get("/")

        assert response.text.index('>First</a>') < response.text.index('>Second</a>')

    def test_header_items_appear_alongside_the_site_name_brand(self):
        app = FrontendSux(site_name="Fabric")

        @app.header_item("Login")
        @app.expose(["/login/"], "Login")
        def login() -> str:
            return "Welcome"

        client = TestClient(app)
        response = client.get("/")

        assert "<strong>Fabric</strong>" in response.text
        assert '<a href="/login/">Login</a>' in response.text


class TestThemeSwitcher:
    def test_theme_init_script_present_in_head_before_the_stylesheet(self):
        client = TestClient(build_app())
        response = client.get("/greet/")

        head = response.text.split("<head>")[1].split("</head>")[0]
        assert 'localStorage.getItem("theme")' in head
        assert head.index("localStorage.getItem") < head.index("pico.min.css")

    def test_script_content_is_not_html_escaped(self):
        # Regression test: <script> is an HTML "raw text" element, so a
        # literal &#34; sent inside one is *not* decoded back into `"` by the
        # browser -- it's just broken JS syntax. A plain (non-Markup) string
        # passed to htpy's script[...] gets HTML-escaped like any other
        # value, which silently turned every quote in these scripts into
        # &#34; and would have made the whole feature non-functional.
        client = TestClient(build_app())
        response = client.get("/greet/")

        assert "&#34;" not in response.text
        assert "&quot;" not in response.text

    def test_dropdown_offers_light_dark_and_auto(self):
        client = TestClient(build_app())
        response = client.get("/greet/")

        assert '<details class="dropdown">' in response.text
        assert '<a href="#" data-theme-choice="light">Light</a>' in response.text
        assert '<a href="#" data-theme-choice="dark">Dark</a>' in response.text
        assert '<a href="#" data-theme-choice="auto">Auto</a>' in response.text

    def test_switcher_script_immediately_follows_the_details_element(self):
        # THEME_SWITCHER_SCRIPT finds its <details> via
        # document.currentScript.previousElementSibling -- this only works
        # if nothing else is rendered between them.
        client = TestClient(build_app())
        response = client.get("/greet/").text

        details_end = response.index("</details>") + len("</details>")
        assert response[details_end : details_end + len("<script>")] == "<script>"

    def test_present_even_alongside_site_name_and_header_items(self):
        app = FrontendSux(site_name="Fabric")

        @app.header_item("Login")
        @app.expose(["/login/"], "Login")
        def login() -> str:
            return "Welcome"

        client = TestClient(app)
        response = client.get("/")

        assert "<strong>Fabric</strong>" in response.text
        assert '<a href="/login/">Login</a>' in response.text
        assert '<details class="dropdown">' in response.text


def build_tuple_app() -> FrontendSux:
    app = FrontendSux()

    @app.expose(["/analyze/"], "Analyze")
    def analyze(
        text: Annotated[str, "Text"],
    ) -> tuple[Annotated[int, "Length"], Annotated[bool, "Empty"]]:
        return len(text), len(text) == 0

    return app


def build_nested_tuple_app() -> FrontendSux:
    app = FrontendSux()

    @app.expose(["/nested/"], "Nested")
    def nested() -> tuple[int, tuple[str, bool]]:
        return 1, ("two", True)

    return app


def build_tuple_with_custom_return_app() -> FrontendSux:
    """A plain int parameter (no custom/Image param) with a tuple return
    containing a custom type -- isolates that the API route's manual JSON
    encoding is triggered by the *return* type alone."""

    app = FrontendSux()

    @app.expose(["/make-rank/"], "Make Rank")
    def make_rank(
        value: Annotated[int, "Value"],
    ) -> tuple[Annotated[int, "Doubled"], Annotated[Rank, "As Rank"]]:
        return value * 2, Rank(value)

    return app


class TestTupleReturnRoutes:
    def test_frontend_form_renders_every_element_of_flat_tuple(self):
        client = TestClient(build_tuple_app())
        response = client.post("/analyze/", data={"text": "hi"})

        assert "Length: 2" in response.text
        assert "Empty: ✗" in response.text

    def test_frontend_form_renders_nested_tuple_recursively(self):
        client = TestClient(build_nested_tuple_app())
        response = client.post("/nested/", data={})

        assert "Result 1: 1" in response.text
        assert "Result 2 1: two" in response.text
        assert "Result 2 2: ✓" in response.text

    def test_api_route_serves_plain_tuple_as_json_array_natively(self):
        client = TestClient(build_tuple_app())
        response = client.put("/api/analyze/", params={"text": "hi"})

        assert response.status_code == 200
        assert response.json() == [2, False]

    def test_api_route_serves_nested_tuple_as_nested_json_array_natively(self):
        client = TestClient(build_nested_tuple_app())
        response = client.put("/api/nested/", params={})

        assert response.status_code == 200
        assert response.json() == [1, ["two", True]]

    def test_api_route_manually_encodes_return_only_tuple_with_custom_type(self):
        client = TestClient(build_tuple_with_custom_return_app())
        response = client.put("/api/make-rank/", params={"value": 5})

        assert response.status_code == 200
        assert response.json() == [10, "5"]

    def test_frontend_form_renders_tuple_containing_custom_type(self):
        client = TestClient(build_tuple_with_custom_return_app())
        response = client.post("/make-rank/", data={"value": "5"})

        assert "Doubled: 10" in response.text
        assert "As Rank: 5" in response.text

    def test_missing_form_encode_detected_inside_nested_tuple(self):
        app = FrontendSux()

        with pytest.raises(TypeError, match="__form_encode__"):

            @app.expose(["/broken-tuple/"], "Broken Tuple")
            def broken() -> tuple[int, RankWithoutEncode]:
                return 1, RankWithoutEncode(2)


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
        # Scoped to the sidebar nav specifically (via its wrapping <aside>) --
        # the header's own nav legitimately has <a> links now (theme switcher
        # options), so a blanket "first <nav>...</nav> in the whole document"
        # split would find the wrong one.
        sidebar = response.text.split('<aside class="nav-desktop">')[1]
        sidebar_nav = sidebar.split("<nav>")[1].split("</nav>")[0]
        assert "<a" not in sidebar_nav


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
