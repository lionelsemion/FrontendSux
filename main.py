from __future__ import annotations

from pathlib import Path
import random
from datetime import date, datetime, timedelta
from math import ceil
from typing import Annotated, Any, Literal

from htpy import label
from PIL import Image
from pydantic_extra_types.color import Color

from frontend_sux import FrontendSux, html_template


app = FrontendSux()

WIDGETS_DIR = Path(__file__).parent / "widgets"


class Rating:
    """
    A 1-5 star rating. Demonstrates frontend_sux's extension mechanism for
    types forms.py doesn't know about: implementing __form_input__ /
    __form_coerce__ / __form_output__ makes a type usable as a parameter or
    return type exactly like a built-in one (see frontend_sux.SupportsFormField).

    The input widget is hand-authored HTML/CSS (a radio-button group with
    CSS-only hover/checked star styling) loaded via html_template — the kind
    of markup that's awkward to build as nested htpy calls but trivial as a
    .html file. The output rendering uses plain htpy instead, since it's a
    single short line; the two hooks are independent and can each pick
    whichever is more convenient.
    """

    def __init__(self, stars: int):
        if not 1 <= stars <= 5:
            raise ValueError("stars must be between 1 and 5")
        self.stars = stars

    @classmethod
    def __form_input__(
        cls, name: str, default: Any, label_text: str, *, required: bool
    ):
        selected = default.stars if isinstance(default, cls) else None
        return html_template(WIDGETS_DIR / "rating.html").substitute(
            name=name,
            label_text=label_text,
            required="required" if required else "",
            **{f"checked_{n}": "checked" if selected == n else "" for n in range(1, 6)},
        )

    @classmethod
    def __form_coerce__(cls, raw_value: str) -> "Rating":
        return cls(int(raw_value))

    def __form_encode__(self) -> str:
        return str(self.stars)

    def __form_output__(self, label_text: str):
        return label[f"{label_text}: ", "★" * self.stars + "☆" * (5 - self.stars)]


@app.expose(["/calculator/"], "Calculator", result_placement="replace")
def calculator(
    a: Annotated[int, "First number"],
    b: Annotated[int, "Second number"],
    op: Annotated[Literal["*", "+", "-"], "Operator"],
) -> int:
    match op:
        case "*":
            return a * b
        case "+":
            return a + b
        case "-":
            return a - b


@app.expose(["/text/uppercase/"], "Uppercase")
def uppercase(text: Annotated[str, "Text"]) -> str:
    return text.upper()


@app.expose(["/text/reverse/"], "Reverse")
def reverse(text: Annotated[str, "Text"]) -> str:
    return text[::-1]


@app.expose(["/text/word-count/"], "Word Count")
def word_count(text: Annotated[str, "Text"]) -> int:
    return len(text.split())


@app.expose(["/text/word-count-live/"], "Live Word Count", submit="on-change")
def word_count_live(text: Annotated[str, "Text"]) -> int:
    return len(text.split())


@app.expose(["/text/analyze/"], "Analyze Text")
def analyze_text(
    text: Annotated[str, "Text"],
) -> tuple[Annotated[int, "Word count"], Annotated[bool, "Is palindrome"]]:
    cleaned = text.lower().replace(" ", "")
    return len(text.split()), cleaned == cleaned[::-1]


@app.expose(["/text/analyze-detailed/"], "Analyze Text (Detailed)")
def analyze_text_detailed(
    text: Annotated[str, "Text"],
) -> tuple[
    Annotated[int, "Word count"],
    tuple[Annotated[bool, "Is palindrome"], Annotated[str, "Reversed"]],
]:
    cleaned = text.lower().replace(" ", "")
    return len(text.split()), (cleaned == cleaned[::-1], text[::-1])


@app.expose(["/text/is-palindrome/"], "Is Palindrome")
def is_palindrome(text: Annotated[str, "Text"]) -> bool:
    cleaned = text.lower().replace(" ", "")
    return cleaned == cleaned[::-1]


@app.expose(["/random/dice/"], "Dice")
def roll_dice(sides: Annotated[int, "Sides"] = 6) -> int:
    return random.randint(1, sides)


@app.expose(["/random/coin/"], "Coin")
def flip_coin() -> Literal["heads", "tails"]:
    return random.choice(["heads", "tails"])


@app.expose(["/demo/confirm/"], "Greet (With Confirmation)", submit="button-extra-confirmation")
def greet_with_confirmation(name: Annotated[str, "Name"]) -> str:
    return f"Hello, {name}!"


@app.header_item("Login")
@app.expose(["/demo/login/"], "Login")
def login_placeholder() -> str:
    return "Not a real login -- demonstrates header_item() stacked with expose()."


@app.expose(["/clock/now/"], "Clock", submit=(1.0, "seconds interval"))
def clock_now() -> str:
    return datetime.now().strftime("%H:%M:%S")


@app.expose(["/finance/tip/"], "Tip Calculator")
def tip_calculator(
    amount: Annotated[float, "Bill amount"],
    tip_percent: Annotated[float, "Tip percent"] = 15.0,
    round_up: Annotated[bool, "Round up to whole currency unit"] = False,
) -> float:
    total = amount * (1 + tip_percent / 100)
    return float(ceil(total)) if round_up else round(total, 2)


@app.expose(["/color/invert/"], "Invert Color")
def invert_color(color: Annotated[Color, "Color"]) -> Color:
    r, g, b = color.as_rgb_tuple()[:3]
    return Color((255 - r, 255 - g, 255 - b))


@app.expose(["/date/add-days/"], "Add Days")
def add_days(
    start_date: Annotated[date, "Start date"],
    days: Annotated[int, "Days"],
) -> date:
    return start_date + timedelta(days=days)


@app.expose(["/date/add-hours/"], "Add Hours")
def add_hours(
    start: Annotated[datetime, "Start"],
    hours: Annotated[int, "Hours"],
) -> datetime:
    return start + timedelta(hours=hours)


@app.expose(["/image/grayscale/"], "Grayscale")
def grayscale(photo: Annotated[Image.Image, "Photo"]) -> Image.Image:
    return photo.convert("L")


@app.expose(["/rating/average/"], "Average Rating")
def average_rating(
    a: Annotated[Rating, "First rating"],
    b: Annotated[Rating, "Second rating"],
) -> Rating:
    return Rating(round((a.stars + b.stars) / 2))


@app.expose(["/rating/live-average/"], "Live Average Rating", submit="on-change")
def live_average_rating(
    a: Annotated[Rating, "First rating"],
    b: Annotated[Rating, "Second rating"],
) -> Rating:
    return Rating(round((a.stars + b.stars) / 2))


@app.expose(["/rating/rate-and-double/"], "Rate and Double")
def rate_and_double(
    rating: Annotated[Rating, "Rating"],
) -> tuple[Annotated[Rating, "Same rating"], Annotated[int, "Stars as number"]]:
    return rating, rating.stars


@app.expose(["/strmult"], "Multiply Strings")
def string_multiplier(text: str, count: int) -> str:
    return text * count
