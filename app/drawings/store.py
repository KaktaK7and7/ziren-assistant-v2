import base64
import binascii
import hashlib
import io
import json
import re
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError

from app.storage.local_store import APP_DIR


MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_LIBRARY_ITEMS = 200
DRAWING_ID_RE = re.compile(r"^[a-f0-9]{32}$")
PNG_DATA_URL_PREFIX = "data:image/png;base64,"


class DrawingStore:
    def __init__(
        self,
        user_id: str | int,
        app_dir: Path | None = None,
    ) -> None:
        account_key = hashlib.sha256(
            str(user_id).encode("utf-8"),
        ).hexdigest()[:16]
        self.root = (app_dir or APP_DIR) / "drawings" / account_key
        self._lock = Lock()

    def _ensure_root(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _decode_png_data_url(image_data_url: object) -> bytes:
        value = str(image_data_url or "")

        if not value.startswith(PNG_DATA_URL_PREFIX):
            raise ValueError("Drawing must be a PNG data URL")

        try:
            image_bytes = base64.b64decode(
                value[len(PNG_DATA_URL_PREFIX):],
                validate=True,
            )
        except (binascii.Error, ValueError) as error:
            raise ValueError("Drawing has invalid base64 data") from error

        if (
            len(image_bytes) < 8
            or len(image_bytes) > MAX_IMAGE_BYTES
            or not image_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        ):
            raise ValueError("Drawing has invalid PNG data")

        return image_bytes

    @staticmethod
    def _clean_text(value: object, limit: int) -> str:
        safe = re.sub(r"[\x00-\x1f\x7f]", " ", str(value or ""))
        return " ".join(safe.split())[:limit].strip()

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except (OSError, ValueError, json.JSONDecodeError):
            return None

        return data if isinstance(data, dict) else None

    @staticmethod
    def _data_url(path: Path, mime_type: str) -> str:
        return (
            f"data:{mime_type};base64,"
            + base64.b64encode(path.read_bytes()).decode("ascii")
        )

    def save(
        self,
        drawing_request: dict[str, Any],
        generated: dict[str, Any],
    ) -> dict[str, Any]:
        image_bytes = self._decode_png_data_url(
            generated.get("image_data_url"),
        )
        drawing_id = uuid4().hex
        drawing_dir = self.root / drawing_id
        image_path = drawing_dir / "drawing.png"
        thumbnail_path = drawing_dir / "thumbnail.jpg"
        metadata_path = drawing_dir / "metadata.json"

        title = self._clean_text(
            drawing_request.get("title"),
            80,
        ) or "Без названия"
        kind = self._clean_text(
            drawing_request.get("kind"),
            20,
        ).lower()

        if kind not in {"sketch", "technical", "story"}:
            kind = "sketch"

        metadata = {
            "id": drawing_id,
            "title": title,
            "kind": kind,
            "story_relevant": (
                bool(drawing_request.get("story_relevant"))
                or kind == "story"
            ),
            "description": self._clean_text(
                drawing_request.get("prompt"),
                1600,
            ),
            "completion_line": self._clean_text(
                drawing_request.get("completion_line"),
                240,
            ),
            "created_at": datetime.now().astimezone().isoformat(),
            "mime_type": "image/png",
            "model": self._clean_text(generated.get("model"), 80),
            "sha256": hashlib.sha256(image_bytes).hexdigest(),
        }

        expected_sha = self._clean_text(generated.get("sha256"), 64)
        if expected_sha and expected_sha != metadata["sha256"]:
            raise ValueError("Drawing checksum mismatch")

        with self._lock:
            self._ensure_root()
            drawing_dir.mkdir()

            try:
                image_path.write_bytes(image_bytes)
                with Image.open(io.BytesIO(image_bytes)) as image:
                    image.load()
                    thumbnail = image.convert("RGB")
                    thumbnail.thumbnail((640, 640))
                    thumbnail.save(
                        thumbnail_path,
                        format="JPEG",
                        quality=84,
                        optimize=True,
                    )

                temporary_metadata = metadata_path.with_suffix(".tmp")
                temporary_metadata.write_text(
                    json.dumps(
                        metadata,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                temporary_metadata.replace(metadata_path)
            except (OSError, UnidentifiedImageError, ValueError):
                for path in (
                    metadata_path.with_suffix(".tmp"),
                    metadata_path,
                    thumbnail_path,
                    image_path,
                ):
                    if path.exists():
                        path.unlink()

                if drawing_dir.exists():
                    drawing_dir.rmdir()
                raise

        return self.get(drawing_id, include_image=False)

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            if not self.root.exists():
                return []

            items: list[dict[str, Any]] = []
            for drawing_dir in self.root.iterdir():
                if (
                    not drawing_dir.is_dir()
                    or not DRAWING_ID_RE.fullmatch(drawing_dir.name)
                ):
                    continue

                metadata = self._read_json(
                    drawing_dir / "metadata.json",
                )
                thumbnail_path = drawing_dir / "thumbnail.jpg"

                if not metadata or not thumbnail_path.exists():
                    continue

                items.append({
                    **metadata,
                    "thumbnail_data_url": self._data_url(
                        thumbnail_path,
                        "image/jpeg",
                    ),
                })

            items.sort(
                key=lambda item: str(item.get("created_at", "")),
                reverse=True,
            )
            return items[:MAX_LIBRARY_ITEMS]

    def get(
        self,
        drawing_id: str,
        include_image: bool = True,
    ) -> dict[str, Any]:
        if not DRAWING_ID_RE.fullmatch(str(drawing_id or "")):
            raise KeyError("Unknown drawing")

        with self._lock:
            drawing_dir = self.root / drawing_id
            metadata = self._read_json(drawing_dir / "metadata.json")
            thumbnail_path = drawing_dir / "thumbnail.jpg"
            image_path = drawing_dir / "drawing.png"

            if (
                not metadata
                or not thumbnail_path.exists()
                or not image_path.exists()
            ):
                raise KeyError("Unknown drawing")

            item = {
                **metadata,
                "thumbnail_data_url": self._data_url(
                    thumbnail_path,
                    "image/jpeg",
                ),
            }

            if include_image:
                item["image_data_url"] = self._data_url(
                    image_path,
                    "image/png",
                )

            return item
