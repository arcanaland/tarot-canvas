"""AppStream metainfo"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from importlib.resources import files

from tarot_canvas._version import __version__
from tarot_canvas.utils.logger import logger

APP_ID = "land.arcana.TarotCanvas"
METAINFO_RESOURCE = f"{APP_ID}.appdata.xml"

COPYRIGHT = "© 2025-2026 Adam Fidel"

MAINTAINER_ROLE = "Maintainer"

FALLBACK_NAME = "Tarot Canvas"
FALLBACK_SUMMARY = "Explore and arrange tarot decks"
FALLBACK_DEVELOPER = "Adam Fidel"
FALLBACK_LICENSE = "MIT"
FALLBACK_URLS = {
    "homepage": "https://github.com/arcanaland/tarot-canvas",
    "bugtracker": "https://github.com/arcanaland/tarot-canvas/issues",
    "faq": "https://github.com/arcanaland/tarot-canvas/blob/main/docs/FAQs.md",
}


@dataclass(frozen=True)
class Person:
    name: str
    role: str
    email: str | None = None


@dataclass(frozen=True)
class AboutData:
    app_id: str = APP_ID
    name: str = FALLBACK_NAME
    summary: str = FALLBACK_SUMMARY
    developer: str = FALLBACK_DEVELOPER
    license: str = FALLBACK_LICENSE
    contact: str | None = None
    version: str = __version__
    copyright: str = COPYRIGHT
    urls: dict[str, str] = field(default_factory=lambda: dict(FALLBACK_URLS))

    @property
    def authors(self) -> list[Person]:
        return [Person(self.developer, MAINTAINER_ROLE, self.contact)]

    @property
    def homepage(self) -> str | None:
        return self.urls.get("homepage")

    @property
    def bugtracker(self) -> str | None:
        return self.urls.get("bugtracker")

    @property
    def faq(self) -> str | None:
        return self.urls.get("faq")


def _text(root: ET.Element, path: str, default: str) -> str:
    element = root.find(path)
    if element is None or not (element.text or "").strip():
        return default
    return element.text.strip()


def load_about_data() -> AboutData:
    """Parse the bundled metainfo XML."""
    try:
        raw = (
            files("tarot_canvas.resources").joinpath(METAINFO_RESOURCE).read_text(encoding="utf-8")
        )
        root = ET.fromstring(raw)
    except Exception as exc:
        logger.warning(f"Could not read {METAINFO_RESOURCE}, using fallback metadata: {exc}")
        return AboutData()

    urls = {
        url.get("type"): (url.text or "").strip()
        for url in root.findall("url")
        if url.get("type") and (url.text or "").strip()
    }

    return AboutData(
        app_id=_text(root, "id", APP_ID),
        name=_text(root, "name", FALLBACK_NAME),
        summary=_text(root, "summary", FALLBACK_SUMMARY),
        developer=_text(root, "developer/name", FALLBACK_DEVELOPER),
        license=_text(root, "project_license", FALLBACK_LICENSE),
        contact=_text(root, "update_contact", "") or None,
        urls=urls or dict(FALLBACK_URLS),
    )
