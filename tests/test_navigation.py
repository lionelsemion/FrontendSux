from frontend_sux.navigation import (
    build_page_tree,
    label_for_segment,
    render_nav,
    render_nav_items,
)


class TestLabelForSegment:
    def test_hyphens_become_spaces(self):
        assert label_for_segment("word-count") == "Word Count"

    def test_underscores_become_spaces(self):
        assert label_for_segment("word_count") == "Word Count"

    def test_single_word_is_title_cased(self):
        assert label_for_segment("calculator") == "Calculator"


class TestBuildPageTree:
    def test_single_top_level_page(self):
        tree = build_page_tree([("/calculator/", "Calculator")])
        assert tree == {
            "calculator": {
                "path": "/calculator/",
                "title": "Calculator",
                "children": {},
            }
        }

    def test_nested_pages_share_a_grouping_node(self):
        tree = build_page_tree(
            [("/text/uppercase/", "Uppercase"), ("/text/reverse/", "Reverse")]
        )

        assert set(tree.keys()) == {"text"}
        text_node = tree["text"]
        assert text_node["path"] is None  # "/text/" itself was never registered
        assert text_node["title"] is None
        assert set(text_node["children"].keys()) == {"uppercase", "reverse"}
        assert text_node["children"]["uppercase"]["path"] == "/text/uppercase/"
        assert text_node["children"]["uppercase"]["title"] == "Uppercase"
        assert text_node["children"]["reverse"]["path"] == "/text/reverse/"
        assert text_node["children"]["reverse"]["title"] == "Reverse"

    def test_mixed_depth_pages(self):
        tree = build_page_tree(
            [("/calculator/", "Calculator"), ("/text/uppercase/", "Uppercase")]
        )
        assert set(tree.keys()) == {"calculator", "text"}
        assert tree["calculator"]["path"] == "/calculator/"
        assert tree["text"]["path"] is None

    def test_leaf_title_can_differ_from_url_segment(self):
        tree = build_page_tree([("/word-count/", "Count My Words")])
        assert tree["word-count"]["title"] == "Count My Words"

    def test_empty_paths_produce_empty_tree(self):
        assert build_page_tree([]) == {}


class TestRenderNavItems:
    def test_leaf_node_renders_as_link_using_its_title(self):
        tree = build_page_tree([("/calculator/", "Calculator")])
        rendered = "".join(str(item) for item in render_nav_items(tree))
        assert '<a href="/calculator/">Calculator</a>' in rendered

    def test_leaf_node_title_overrides_url_derived_label(self):
        tree = build_page_tree([("/word-count/", "Count My Words")])
        rendered = "".join(str(item) for item in render_nav_items(tree))
        assert '<a href="/word-count/">Count My Words</a>' in rendered
        assert ">Word Count<" not in rendered

    def test_grouping_node_renders_as_unlinked_strong_with_nested_list(self):
        tree = build_page_tree(
            [("/text/uppercase/", "Uppercase"), ("/text/reverse/", "Reverse")]
        )
        rendered = "".join(str(item) for item in render_nav_items(tree))

        assert "<strong>Text</strong>" in rendered
        assert "<a href=\"/text/uppercase/\">Uppercase</a>" in rendered
        assert "<a href=\"/text/reverse/\">Reverse</a>" in rendered
        assert "<ul>" in rendered  # nested list for the group's children


class TestRenderNav:
    def test_includes_all_registered_pages(self):
        rendered = str(
            render_nav(
                [
                    ("/calculator/", "Calculator"),
                    ("/text/uppercase/", "Uppercase"),
                    ("/random/dice/", "Dice"),
                ]
            )
        )
        assert '<a href="/calculator/">Calculator</a>' in rendered
        assert '<a href="/text/uppercase/">Uppercase</a>' in rendered
        assert '<a href="/random/dice/">Dice</a>' in rendered

    def test_empty_registry_renders_empty_list(self):
        rendered = str(render_nav([]))
        assert "<a" not in rendered
