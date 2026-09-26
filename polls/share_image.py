"""1200×630 PNG preview card for link sharing (Open Graph image), drawn with Pillow."""
import io
import unicodedata
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 630
FONT_PATH = Path(__file__).resolve().parent / "assets" / "fonts" / "PlusJakartaSans.ttf"

BG = "#FAF8FF"
TEXT = "#1E1B2E"
MUTED = "#6B6880"
OPTION_COLORS = ["#7C3AED", "#EC4899", "#F97316", "#14B8A6", "#EAB308"]
OPTION_SOFT = ["#F1EAFE", "#FDE8F3", "#FFEEDF", "#DDF7F3", "#FEF6D6"]


@lru_cache(maxsize=16)
def font(size, weight="Bold"):
    f = ImageFont.truetype(str(FONT_PATH), size)
    f.set_variation_by_name(weight)
    return f


def clean(text):
    """Drop emoji / symbols the font cannot draw."""
    kept = "".join(ch for ch in text if unicodedata.category(ch) not in ("So", "Cs", "Co") and ord(ch) <= 0xFFFF)
    return " ".join(kept.split())


def wrap(draw, text, fnt, max_width, max_lines):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            line = trial
            continue
        if line:
            lines.append(line)
        line = word
        if len(lines) == max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        while last and draw.textlength(last + "…", font=fnt) > max_width:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def gradient_bar(image, height=14):
    bar = Image.new("RGB", (WIDTH, height))
    start, end = (124, 58, 237), (219, 39, 119)
    px = bar.load()
    for x in range(WIDTH):
        t = x / (WIDTH - 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(start, end))
        for y in range(height):
            px[x, y] = color
    image.paste(bar, (0, 0))


def render_poll_card(poll, options, total_votes):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    gradient_bar(image)
    draw = ImageDraw.Draw(image)
    margin = 72

    draw.text((margin, 52), "kararsızım", font=font(40, "ExtraBold"), fill="#7C3AED")
    draw.text((WIDTH - margin, 62), clean(poll.category_label), font=font(26, "SemiBold"), fill=MUTED, anchor="ra")

    q_font = font(56 if len(poll.question) < 70 else 46, "ExtraBold")
    y = 130
    for line in wrap(draw, clean(poll.question), q_font, WIDTH - 2 * margin, 3):
        draw.text((margin, y), line, font=q_font, fill=TEXT)
        y += q_font.size + 12

    y += 18
    o_font = font(30, "SemiBold")
    shown = options[:5]
    row_h = 58 if len(shown) > 3 else 66
    for i, option in enumerate(shown):
        if y + row_h > HEIGHT - 90:
            rest = len(options) - i
            draw.text((WIDTH - margin, HEIGHT - 58), f"+{rest} seçenek daha", font=font(26, "Bold"), fill="#7C3AED", anchor="rs")
            break
        draw.rounded_rectangle((margin, y, WIDTH - margin, y + row_h - 12), radius=16, fill=OPTION_SOFT[i])
        cy = y + (row_h - 12) // 2
        draw.ellipse((margin + 22, cy - 9, margin + 40, cy + 9), fill=OPTION_COLORS[i])
        text = wrap(draw, clean(option.text), o_font, WIDTH - 2 * margin - 90, 1)
        draw.text((margin + 60, cy), text[0] if text else "", font=o_font, fill=TEXT, anchor="lm")
        y += row_h

    footer = f"@{poll.author.username}  ·  {total_votes} oy  ·  Sen olsan hangisini seçerdin?"
    draw.text((margin, HEIGHT - 58), footer, font=font(26, "SemiBold"), fill=MUTED, anchor="ls")

    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()
