import re

from playwright.sync_api import Page, expect


def test_button_mode_is_the_default_and_needs_a_click(page: Page, live_server_url: str):
    page.goto(live_server_url + "/text/uppercase/")

    expect(page.locator("button[type='submit']")).to_have_count(1)

    page.fill("input[name='text']", "hi")
    expect(page.locator("#output")).to_be_empty()

    page.click("button[type='submit']")
    expect(page.locator("#output")).to_contain_text("HI")


def test_on_change_updates_live_while_typing_with_no_blur_and_no_button(
    page: Page, live_server_url: str
):
    page.goto(live_server_url + "/text/word-count-live/")

    expect(page.locator("button[type='submit']")).to_have_count(0)

    # Deliberately no .blur()/Tab/click afterward -- this is the whole point
    # of the fix: hx-trigger="input ..." (not "change") means the request
    # fires from typing itself. A stale "change"-only trigger would leave
    # #output empty here, since a text <input>'s "change" event only fires
    # on blur, never while the field still has focus.
    page.locator("input[name='text']").fill("one two three")

    expect(page.locator("#output")).to_contain_text("Result: 3", timeout=2000)


def test_on_change_re_fires_when_a_radio_group_cycles_back_to_a_visited_value(
    page: Page, live_server_url: str
):
    # Regression test for a real bug: htmx's "changed" trigger modifier (an
    # earlier version of this mode's hx-trigger included it) tracks a
    # *per-element* value history, but a radio button's own `value` never
    # changes -- only which radio in the group is checked does. That made
    # "changed" wrongly suppress a request when the group's selection cycled
    # back to a value one of its radios already fired once before, even
    # though the group's actual selection had genuinely changed in between.
    page.goto(live_server_url + "/rating/live-average/")

    page.click("label[for='a-3']")
    page.click("label[for='b-3']")
    expect(page.locator("#output")).to_contain_text("★★★☆☆", timeout=2000)

    page.click("label[for='a-5']")
    expect(page.locator("#output")).to_contain_text("★★★★☆", timeout=2000)

    # This is the second time the "a" rating's own value=3 radio fires (its
    # first firing was the very first click above) -- the case a lingering
    # "changed" modifier would wrongly suppress.
    page.click("label[for='a-3']")
    expect(page.locator("#output")).to_contain_text("★★★☆☆", timeout=2000)


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
