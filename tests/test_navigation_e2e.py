import pytest
from playwright.sync_api import Page, expect


def test_home_page_lists_all_top_level_and_grouped_pages(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    # The nav is duplicated as two CSS-switched variants (desktop/mobile, see
    # LAYOUT_STYLE) -- ":visible" picks whichever one is actually shown at
    # the current viewport, since a bare "nav" locator would strict-mode
    # -violate on the always-present hidden one.
    nav = page.locator("nav:visible")
    expect(nav.get_by_role("link", name="Calculator", exact=True)).to_be_visible()
    expect(nav.get_by_text("Text", exact=True)).to_be_visible()
    expect(nav.get_by_role("link", name="Uppercase")).to_be_visible()
    expect(nav.get_by_role("link", name="Reverse")).to_be_visible()
    expect(nav.get_by_role("link", name="Word Count", exact=True)).to_be_visible()
    expect(nav.get_by_text("Random", exact=True)).to_be_visible()
    expect(nav.get_by_role("link", name="Dice")).to_be_visible()
    expect(nav.get_by_role("link", name="Coin")).to_be_visible()


def test_clicking_a_nav_link_navigates_to_that_page(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    page.locator("nav:visible").get_by_role("link", name="Calculator", exact=True).click()

    expect(page).to_have_url(live_server_url + "/calculator/")
    expect(page.locator("input[name='a']")).to_be_visible()


def test_header_item_link_navigates_to_its_expose_d_page(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    page.locator("header").get_by_role("link", name="Login", exact=True).click()

    expect(page).to_have_url(live_server_url + "/demo/login/")
    expect(page.get_by_role("heading", name="Login", level=1)).to_be_visible()


def test_grouped_page_is_reachable_and_functional(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    page.locator("nav:visible").get_by_role("link", name="Uppercase").click()
    expect(page).to_have_url(live_server_url + "/text/uppercase/")

    page.fill("input[name='text']", "hello")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("HELLO")


def test_nav_is_present_and_consistent_across_pages(page: Page, live_server_url: str):
    for path in ("/", "/calculator/", "/text/uppercase/", "/random/dice/"):
        page.goto(live_server_url + path)
        nav = page.locator("nav:visible")
        expect(nav.get_by_role("link", name="Calculator", exact=True)).to_be_visible()


def test_page_heading_shows_the_expose_title(page: Page, live_server_url: str):
    page.goto(live_server_url + "/calculator/")
    expect(page.get_by_role("heading", name="Calculator", level=1)).to_be_visible()

    page.goto(live_server_url + "/text/word-count/")
    expect(page.get_by_role("heading", name="Word Count", level=1)).to_be_visible()


def test_sidebar_collapses_and_expands_via_native_details_disclosure(
    page: Page, live_server_url: str
):
    # The <details>-based disclosure is the mobile variant of the nav (see
    # LAYOUT_STYLE) -- the desktop variant is a plain, always-visible nav
    # with no toggle at all, so this needs a narrow viewport to exercise.
    page.set_viewport_size({"width": 375, "height": 700})
    page.goto(live_server_url + "/calculator/")

    nav_link = page.locator(".nav-mobile").get_by_role(
        "link", name="Calculator", exact=True
    )
    expect(nav_link).to_be_hidden()

    # Collapsing is pure HTML <details>/<summary> — no JS is loaded for it.
    page.get_by_text("Navigation", exact=True).click()
    expect(nav_link).to_be_visible()

    page.get_by_text("Navigation", exact=True).click()
    expect(nav_link).to_be_hidden()


def test_desktop_sidebar_nav_is_always_visible_without_expanding(
    page: Page, live_server_url: str
):
    page.goto(live_server_url + "/calculator/")

    nav_link = page.locator(".nav-desktop").get_by_role(
        "link", name="Calculator", exact=True
    )
    expect(nav_link).to_be_visible()


def test_main_content_is_not_glued_to_the_top_of_the_page(page: Page, live_server_url: str):
    page.goto(live_server_url + "/calculator/")

    heading_box = page.get_by_role("heading", name="Calculator", level=1).bounding_box()
    assert heading_box is not None
    assert heading_box["y"] > 10


def test_header_content_is_not_glued_to_the_top_of_the_page(page: Page, live_server_url: str):
    # Regression test: Pico's default body>header padding-block (~1rem) reads
    # as cramped for a thin nav bar right at the viewport's top edge, even
    # though that same amount is fine for the much bigger <main> above.
    page.goto(live_server_url + "/")

    switcher_box = page.locator("details.dropdown summary").bounding_box()
    assert switcher_box is not None
    assert switcher_box["y"] > 15


def test_theme_switcher_is_vertically_centered_with_other_header_content(
    page: Page, live_server_url: str
):
    # Regression test: Pico's <nav> has no align-items of its own (flex
    # default: stretch) and instead centers content *within* each nav>ul via
    # a nav-ul-specific rule -- fine for the site_name/header_item groups,
    # which are <ul>s, but the theme switcher's <details> isn't one, so
    # without an explicit align-items:center on the nav itself, it renders
    # stretched with nothing centering its own content, offset from its
    # <ul>-based siblings.
    page.goto(live_server_url + "/")

    switcher_box = page.locator("details.dropdown summary").bounding_box()
    # "Login" also appears in the sidebar nav (it's a real @expose(...)'d
    # page too) -- scope to the header landmark specifically.
    login_box = page.get_by_role("banner").get_by_role(
        "link", name="Login", exact=True
    ).bounding_box()
    assert switcher_box is not None
    assert login_box is not None

    switcher_center = switcher_box["y"] + switcher_box["height"] / 2
    login_center = login_box["y"] + login_box["height"] / 2
    assert switcher_center == pytest.approx(login_center, abs=2)


def test_form_fields_align_despite_different_label_lengths(page: Page, live_server_url: str):
    # Regression test: a field's <label> wraps its text and its input
    # together; Pico's .grid leaves each cell at its default alignment
    # (stretch), which stretches the cell to the row's height (set by
    # whichever label wraps the most) without pushing shorter labels'
    # content down to compensate -- so a short, single-line label's input
    # sits higher than a long, wrapped label's input, even in the same row.
    # Narrow enough that "A Rather Long Label That Wraps" actually wraps
    # while "A"/"C" don't.
    page.set_viewport_size({"width": 800, "height": 500})
    page.goto(live_server_url + "/demo/field-alignment/")

    a_box = page.locator("[name='a']").bounding_box()
    b_box = page.locator("[name='b']").bounding_box()
    c_box = page.locator("[name='c']").bounding_box()
    assert a_box is not None and b_box is not None and c_box is not None

    # The long label must actually wrap for this test to mean anything.
    label_box = page.get_by_text("A Rather Long Label That Wraps").bounding_box()
    assert label_box is not None
    assert label_box["height"] > 20  # one line of this text is ~20px tall

    assert a_box["y"] == pytest.approx(b_box["y"], abs=2)
    assert b_box["y"] == pytest.approx(c_box["y"], abs=2)
