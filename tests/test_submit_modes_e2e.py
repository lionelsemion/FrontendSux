import re

from playwright.sync_api import Page, expect


def test_button_mode_is_the_default_and_needs_a_click(page: Page, live_server_url: str):
    page.goto(live_server_url + "/text/uppercase/")

    expect(page.locator("button[type='submit']")).to_have_count(1)

    page.fill("input[name='text']", "hi")
    expect(page.locator("#output")).to_be_empty()

    page.click("button[type='submit']")
    expect(page.locator("#output")).to_contain_text("HI")


def test_on_change_updates_without_a_submit_button(page: Page, live_server_url: str):
    page.goto(live_server_url + "/text/word-count-live/")

    expect(page.locator("button[type='submit']")).to_have_count(0)

    text_input = page.locator("input[name='text']")
    text_input.fill("one two three")
    text_input.blur()

    expect(page.locator("#output")).to_contain_text("Result: 3")


def test_interval_polls_automatically_without_any_interaction(page: Page, live_server_url: str):
    page.goto(live_server_url + "/clock/now/")

    expect(page.locator("button[type='submit']")).to_have_count(0)

    output = page.locator("#output")
    expect(output).to_have_text(re.compile(r"\d{2}:\d{2}:\d{2}"), timeout=2000)
    first = output.inner_text()

    page.wait_for_timeout(1200)
    second = output.inner_text()

    assert second != first


def test_button_extra_confirmation_blocks_the_request_when_dismissed(
    page: Page, live_server_url: str
):
    page.goto(live_server_url + "/demo/confirm/")
    page.fill("input[name='name']", "Ada")

    messages = []
    page.once("dialog", lambda dialog: (messages.append(dialog.message), dialog.dismiss()))
    page.click("button[type='submit']")
    page.wait_for_timeout(200)

    assert messages == ["Are you sure you want to submit?"]
    expect(page.locator("#output")).to_be_empty()


def test_button_extra_confirmation_proceeds_when_accepted(page: Page, live_server_url: str):
    page.goto(live_server_url + "/demo/confirm/")
    page.fill("input[name='name']", "Ada")

    page.once("dialog", lambda dialog: dialog.accept())
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("Hello, Ada!")
