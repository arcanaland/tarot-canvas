"""AppStream metainfo"""

from __future__ import annotations

import html
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

# The markup AppStream allows in a <description>; anything else is flattened to its text
ALLOWED_MARKUP = frozenset({"p", "ul", "ol", "li", "em", "code"})

XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# AppStream's default when a <release> has no type attribute
DEFAULT_RELEASE_TYPE = "stable"


@dataclass(frozen=True)
class Person:
    name: str
    role: str
    email: str | None = None


@dataclass(frozen=True)
class Release:
    version: str
    date: str
    type: str = DEFAULT_RELEASE_TYPE
    description: str = ""


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
    releases: tuple[Release, ...] = ()

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


def _sanitised_children(element: ET.Element) -> str:
    """The content of `element` as HTML, keeping only ALLOWED_MARKUP and no attributes."""
    parts = [html.escape(element.text or "")]
    for child in element:
        # A translation would otherwise render next to the untranslated text
        if child.get(XML_LANG) is None:
            inner = _sanitised_children(child)
            parts.append(
                f"<{child.tag}>{inner}</{child.tag}>" if child.tag in ALLOWED_MARKUP else inner
            )
        parts.append(html.escape(child.tail or ""))
    return "".join(parts)


def _release(element: ET.Element) -> Release:
    description = next((d for d in element.findall("description") if d.get(XML_LANG) is None), None)
    return Release(
        version=element.get("version", ""),
        date=element.get("date", ""),
        type=element.get("type", DEFAULT_RELEASE_TYPE),
        description="" if description is None else _sanitised_children(description).strip(),
    )


def parse_metainfo(raw: str) -> AboutData:
    """AboutData from metainfo XML; raises ET.ParseError if it isn't XML."""
    root = ET.fromstring(raw)

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
        # Document order is newest-first, which appstreamcli validate enforces
        releases=tuple(_release(release) for release in root.findall("releases/release")),
    )


def load_about_data() -> AboutData:
    """Parse the bundled metainfo XML."""
    try:
        raw = (
            files("tarot_canvas.resources").joinpath(METAINFO_RESOURCE).read_text(encoding="utf-8")
        )
        return parse_metainfo(raw)
    except Exception as exc:
        logger.warning(f"Could not read {METAINFO_RESOURCE}, using fallback metadata: {exc}")
        return AboutData()
