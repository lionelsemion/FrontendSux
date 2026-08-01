"""Building and rendering the sidebar navigation tree from registered pages."""

from __future__ import annotations

from htpy import a, li, nav, strong, ul


def label_for_segment(segment: str) -> str:
    """Turn a URL path segment into a human-readable label, e.g. 'word-count' -> 'Word Count'."""

    return segment.replace("-", " ").replace("_", " ").title()


def build_page_tree(pages: list[tuple[str, str]]) -> dict[str, dict]:
    """
    Arrange registered (path, title) pages into a tree keyed by URL path segment.

    Each node is {"path": str | None, "title": str | None, "children": dict}.
    A node's "path"/"title" are set only if that exact path was registered;
    intermediate segments that were never exposed themselves act as unlinked
    grouping nodes, labeled from their URL segment instead.
    """

    root: dict[str, dict] = {}

    for path, page_title in pages:
        segments = [segment for segment in path.strip("/").split("/") if segment]

        level = root
        for index, segment in enumerate(segments):
            node = level.setdefault(segment, {"path": None, "title": None, "children": {}})
            if index == len(segments) - 1:
                node["path"] = path
                node["title"] = page_title
            level = node["children"]

    return root


def render_nav_items(tree: dict[str, dict]) -> list:
    items = []

    for segment, node in tree.items():
        label_text = node["title"] or label_for_segment(segment)
        heading = a(href=node["path"])[label_text] if node["path"] else strong[label_text]

        if node["children"]:
            items.append(li[heading, ul[render_nav_items(node["children"])]])
        else:
            items.append(li[heading])

    return items


def render_nav(pages: list[tuple[str, str]]):
    tree = build_page_tree(pages)
    return nav[ul[render_nav_items(tree)]]
