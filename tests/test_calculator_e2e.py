import pytest
from playwright.sync_api import Page, expect


@pytest.mark.parametrize(
    ("a", "b", "op", "expected"),
    [
        ("3", "4", "+", "7"),
        ("10", "4", "-", "6"),
        ("5", "6", "*", "30"),
    ],
)
def test_calculator_form_submit(
    page: Page, live_server_url: str, a: str, b: str, op: str, expected: str
):
    page.goto(f"{live_server_url}/calculator/")

    page.fill("input[name='a']", a)
    page.fill("input[name='b']", b)
    page.select_option("select[name='op']", op)
    page.click("button[type='submit']")

    # result_placement="replace" swaps the whole #form with the result fragment.
    expect(page.locator("#form")).to_have_count(0)
    expect(page.get_by_text(f"Result: {expected}")).to_be_visible()
    expect(page.get_by_role("link", name="↺ Submit again")).to_be_visible()


def test_calculator_requires_inputs(page: Page, live_server_url: str):
    page.goto(f"{live_server_url}/calculator/")

    page.click("button[type='submit']")

    # Browser-native required validation should block submission,
    # so the form is never replaced and no result appears.
    expect(page.locator("#form")).to_be_visible()
    expect(page.get_by_text("Result:")).to_have_count(0)
