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
