from playwright.sync_api import Page, expect


def test_selecting_dark_sets_data_theme_and_updates_the_summary(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    page.locator("details.dropdown summary").click()
    page.get_by_role("link", name="Dark", exact=True).click()

    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("details.dropdown summary")).to_have_text("Theme: Dark")


def test_selecting_light_sets_data_theme_light(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    page.locator("details.dropdown summary").click()
    page.get_by_role("link", name="Light", exact=True).click()

    expect(page.locator("html")).to_have_attribute("data-theme", "light")


def test_selecting_auto_removes_the_data_theme_attribute(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    page.locator("details.dropdown summary").click()
    page.get_by_role("link", name="Dark", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")

    page.locator("details.dropdown summary").click()
    page.get_by_role("link", name="Auto", exact=True).click()

    expect(page.locator("html")).not_to_have_attribute("data-theme", "dark")
    expect(page.locator("html")).not_to_have_attribute("data-theme", "light")


def test_choosing_a_theme_closes_the_dropdown(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    dropdown = page.locator("details.dropdown")
    dropdown.locator("summary").click()
    expect(dropdown).to_have_attribute("open", "")

    page.get_by_role("link", name="Dark", exact=True).click()

    expect(dropdown).not_to_have_attribute("open", "")


def test_choice_persists_across_a_page_reload(page: Page, live_server_url: str):
    # The whole point of localStorage + THEME_INIT_SCRIPT: proves the choice
    # isn't just an in-memory DOM change for the current page load.
    page.goto(live_server_url + "/")

    page.locator("details.dropdown summary").click()
    page.get_by_role("link", name="Dark", exact=True).click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")

    page.reload()

    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("details.dropdown summary")).to_have_text("Theme: Dark")


def test_choice_persists_when_navigating_to_a_different_page(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")
    page.locator("details.dropdown summary").click()
    page.get_by_role("link", name="Dark", exact=True).click()

    page.goto(live_server_url + "/calculator/")

    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
