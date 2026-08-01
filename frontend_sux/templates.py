"""Loading static .html files as trusted markup for hand-authored custom widgets."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from string import Template

from markupsafe import Markup


class HtmlTemplate:
    """A parsed .html file. .substitute(...) fills in $placeholders and
    returns trusted markup, embeddable directly as an htpy child without
    being escaped."""

    def __init__(self, template: Template):
        self._template = template

    def substitute(self, **kwargs: object) -> Markup:
        return Markup(self._template.substitute(**kwargs))


@lru_cache(maxsize=None)
def _load(path: Path) -> HtmlTemplate:
    return HtmlTemplate(Template(path.read_text()))


def html_template(path: str | Path) -> HtmlTemplate:
    """
    Load (and cache) a .html file as a string.Template, for building a custom
    form widget's markup from hand-authored HTML/CSS/JS instead of htpy calls
    — typically from inside a type's __form_input__/__form_output__ hook (see
    forms.SupportsFormField).

    Placeholders use $name syntax (string.Template), not {name}, so they
    don't collide with literal {}'s in embedded CSS/JS. .substitute() raises
    KeyError on any unfilled placeholder — there's no silent partial fill,
    and no loops/conditionals; reach for htpy directly if you need those.
    """

    return _load(Path(path).resolve())
