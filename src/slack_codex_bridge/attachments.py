from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


IMAGE_MARKER_RE = re.compile(r"\[\[image:(?P<path>[^\]]+)\]\]")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@dataclass(slots=True)
class ParsedResponse:
    text: str
    image_paths: list[Path]


def parse_response_attachments(message: str) -> ParsedResponse:
    image_paths = [Path(match.group("path").strip()).expanduser() for match in IMAGE_MARKER_RE.finditer(message)]
    text = IMAGE_MARKER_RE.sub("", message)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return ParsedResponse(text=text, image_paths=image_paths)


def validate_image_path(path: Path, workspace_root: Path) -> str | None:
    if not path.is_absolute():
        return "image path must be absolute"
    if path.suffix.lower() not in ALLOWED_IMAGE_SUFFIXES:
        return "unsupported image type"
    if not path.exists() or not path.is_file():
        return "image file does not exist"

    resolved = path.resolve()
    allowed_roots = (workspace_root.resolve(), Path("/tmp").resolve())
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        return "image path must be inside the current workspace or /tmp"
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
