import pytest
from markupsafe import Markup

from frontend_sux.templates import html_template


@pytest.fixture
def template_path(tmp_path):
    path = tmp_path / "widget.html"
    path.write_text('<span class="$cls">Hello, $name!</span>')
    return path


class TestHtmlTemplate:
    def test_substitute_fills_placeholders(self, template_path):
        rendered = html_template(template_path).substitute(cls="greeting", name="Ada")
        assert str(rendered) == '<span class="greeting">Hello, Ada!</span>'

    def test_substitute_returns_trusted_markup(self, template_path):
        rendered = html_template(template_path).substitute(cls="greeting", name="Ada")
        assert isinstance(rendered, Markup)

    def test_substitute_does_not_escape_the_filled_in_value(self, template_path):
        # The whole point of loading a .html file this way is to get trusted,
        # unescaped output -- callers are responsible for what they put in.
        rendered = html_template(template_path).substitute(
            cls="greeting", name="<b>Ada</b>"
        )
        assert "<b>Ada</b>" in str(rendered)

    def test_substitute_raises_on_missing_placeholder(self, template_path):
        with pytest.raises(KeyError):
            html_template(template_path).substitute(cls="greeting")

    def test_repeated_calls_with_same_path_reuse_the_cached_template(self, template_path):
        first = html_template(template_path)
        second = html_template(template_path)
        assert first is second

    def test_accepts_a_string_path(self, template_path):
        rendered = html_template(str(template_path)).substitute(cls="greeting", name="Ada")
        assert "Ada" in str(rendered)
