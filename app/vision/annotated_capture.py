from __future__ import annotations

import base64
import hashlib
import io
from typing import Any

from PIL import Image, ImageDraw


JPEG_DATA_URL_PREFIX = "data:image/jpeg;base64,"
PNG_DATA_URL_PREFIX = "data:image/png;base64,"


ANNOTATION_COLORS = {
    "target": "#00e5ff",
    "step": "#57f2c1",
    "text": "#9b8cff",
    "warning": "#ffb84d",
}


def render_annotated_capture(
    image_data_url: str,
    analysis: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not image_data_url.startswith(JPEG_DATA_URL_PREFIX):
        raise ValueError("Screen source must be a JPEG data URL")

    image_bytes = base64.b64decode(
        image_data_url[len(JPEG_DATA_URL_PREFIX):],
        validate=True,
    )
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")

    draw = ImageDraw.Draw(image)
    line_width = max(3, round(min(image.size) * 0.004))
    badge_radius = max(12, round(min(image.size) * 0.018))
    labels: list[str] = []

    for index, annotation in enumerate(analysis.get("annotations") or [], 1):
        x1 = round(float(annotation["x"]) * image.width)
        y1 = round(float(annotation["y"]) * image.height)
        x2 = round(
            (float(annotation["x"]) + float(annotation["width"]))
            * image.width,
        )
        y2 = round(
            (float(annotation["y"]) + float(annotation["height"]))
            * image.height,
        )
        color = ANNOTATION_COLORS.get(
            str(annotation.get("kind")),
            ANNOTATION_COLORS["target"],
        )
        draw.rounded_rectangle(
            (x1, y1, x2, y2),
            radius=max(4, line_width * 2),
            outline=color,
            width=line_width,
        )

        badge_x = max(badge_radius + 2, min(image.width - badge_radius - 2, x1))
        badge_y = max(badge_radius + 2, y1 - badge_radius - 8)
        draw.line(
            (badge_x, badge_y + badge_radius, x1, y1),
            fill=color,
            width=line_width,
        )
        arrow_size = max(7, line_width * 2)
        draw.polygon(
            (
                (x1, y1),
                (x1 - arrow_size, y1 - arrow_size * 2),
                (x1 + arrow_size, y1 - arrow_size * 2),
            ),
            fill=color,
        )
        draw.ellipse(
            (
                badge_x - badge_radius,
                badge_y - badge_radius,
                badge_x + badge_radius,
                badge_y + badge_radius,
            ),
            fill="#071116",
            outline=color,
            width=line_width,
        )
        marker = str(annotation.get("step") or index)
        draw.text(
            (badge_x, badge_y),
            marker,
            fill="#ffffff",
            anchor="mm",
        )
        labels.append(f"{marker}. {annotation.get('label', '')}")

    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    png_bytes = buffer.getvalue()
    mode_labels = {
        "explain": "Разбор экрана",
        "translate": "Перевод с экрана",
        "guide": "План действий",
        "annotate": "Карта экрана",
    }
    title = mode_labels.get(str(analysis.get("mode")), "Разбор экрана")
    answer = str(analysis.get("answer") or "").strip()
    description_parts = [answer] if answer else []
    if labels:
        description_parts.append("Отметки:\n" + "\n".join(labels))
    description = "\n\n".join(description_parts)

    return (
        {
            "kind": "screen",
            "title": title,
            "prompt": description[:1600],
            "story_relevant": False,
            "completion_line": (
                "Я сохранила разбор в Холст. Там останутся рамки и порядок шагов."
            ),
        },
        {
            "image_data_url": (
                PNG_DATA_URL_PREFIX
                + base64.b64encode(png_bytes).decode("ascii")
            ),
            "model": "ziren-local-screen-annotation",
            "sha256": hashlib.sha256(png_bytes).hexdigest(),
        },
    )
