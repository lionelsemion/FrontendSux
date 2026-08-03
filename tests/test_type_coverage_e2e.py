from io import BytesIO
import re

from PIL import Image
from playwright.sync_api import Page, expect


def _tiny_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (3, 3), color=(0, 0, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_is_palindrome_str_in_bool_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/text/is-palindrome/")

    page.fill("input[name='text']", "Racecar")
    page.click("button[type='submit']")
    expect(page.locator("#output")).to_contain_text("✓")

    page.fill("input[name='text']", "hello")
    page.click("button[type='submit']")
    expect(page.locator("#output")).to_contain_text("✗")


def test_tip_calculator_float_and_bool_in_float_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/finance/tip/")

    page.fill("input[name='amount']", "100")
    page.fill("input[name='tip_percent']", "20")
    page.check("input[name='round_up']")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("Result: 120.0")


def test_invert_color_color_in_color_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/color/invert/")

    page.fill("input[name='color']", "#000000")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("#fff")


def test_add_days_date_in_date_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/date/add-days/")

    page.fill("input[name='start_date']", "2026-01-01")
    page.fill("input[name='days']", "10")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("2026-01-11")


def test_add_hours_datetime_in_datetime_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/date/add-hours/")

    page.fill("input[name='start']", "2026-01-01T10:00")
    page.fill("input[name='hours']", "5")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("2026-01-01T15:00:00")


def test_grayscale_image_in_image_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/image/grayscale/")

    page.set_input_files(
        "input[name='photo']",
        {"name": "photo.png", "mimeType": "image/png", "buffer": _tiny_png_bytes()},
    )
    page.click("button[type='submit']")

    expect(page.locator("#output img")).to_have_attribute(
        "src", re.compile(r"^data:image/png;base64,")
    )


def test_analyze_text_str_in_nested_tuple_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/text/analyze-detailed/")

    page.fill("input[name='text']", "abc")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("Word count: 1")
    expect(page.locator("#output")).to_contain_text("Is palindrome: ✗")
    expect(page.locator("#output")).to_contain_text("Reversed: cba")


def test_rating_average_custom_type_in_custom_type_out(page: Page, live_server_url: str):
    page.goto(live_server_url + "/rating/average/")

    # The star widget is a hand-authored HTML/CSS radio group loaded via
    # html_template (see Rating in main.py) -- clicking the star label
    # selects the underlying (visually hidden) radio input.
    page.click("label[for='a-4']")
    page.click("label[for='b-2']")
    page.click("button[type='submit']")

    expect(page.locator("#output")).to_contain_text("★★★☆☆")


def test_new_pages_are_grouped_correctly_in_nav(page: Page, live_server_url: str):
    page.goto(live_server_url + "/")

    nav = page.locator("nav:visible")
    expect(nav.get_by_text("Finance", exact=True)).to_be_visible()
    expect(nav.get_by_role("link", name="Tip Calculator")).to_be_visible()

    expect(nav.get_by_text("Color", exact=True)).to_be_visible()
    expect(nav.get_by_role("link", name="Invert Color")).to_be_visible()

    expect(nav.get_by_text("Date", exact=True)).to_be_visible()
    expect(nav.get_by_role("link", name="Add Days")).to_be_visible()
    expect(nav.get_by_role("link", name="Add Hours")).to_be_visible()

    expect(nav.get_by_role("link", name="Is Palindrome")).to_be_visible()
