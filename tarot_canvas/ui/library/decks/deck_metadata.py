"""A deck's [deck] fields as the rows and links the header shows"""

from tarot_canvas.ui.dates import format_date
from tarot_canvas.ui.strings import DECK_VIEW, license_name
from tarot_canvas.ui.widgets.pane_text import display_address

# a row per 2.0 link rel; `publisher` links join the Publisher row instead
LINK_PREFIX = "links."

DETAIL_FIELDS = (
    ("description", DECK_VIEW["field.description"]),
    ("license", DECK_VIEW["field.license"]),
    ("copyright", DECK_VIEW["field.copyright"]),
    ("attribution", DECK_VIEW["field.attribution"]),
    ("publisher", DECK_VIEW["field.publisher"]),
    ("website", DECK_VIEW["field.website"]),
    ("links.homepage", DECK_VIEW["field.links.homepage"]),
    ("links.artist", DECK_VIEW["field.links.artist"]),
    ("links.buy", DECK_VIEW["field.links.buy"]),
    ("links.source", DECK_VIEW["field.links.source"]),
    ("created_date", DECK_VIEW["field.created_date"]),
    ("updated_date", DECK_VIEW["field.updated_date"]),
    ("published_date", DECK_VIEW["field.published_date"]),
    ("tags", DECK_VIEW["field.tags"]),
    ("version", DECK_VIEW["field.version"]),
    ("schema_version", DECK_VIEW["field.schema_version"]),
)

DATE_KEYS = ("created_date", "updated_date", "published_date")


def format_value(value):
    if value is None or isinstance(value, bool):
        return None if value is None else (DECK_VIEW["yes"] if value else DECK_VIEW["no"])

    if isinstance(value, list | tuple):
        parts = [format_value(item) for item in value]
        parts = [part for part in parts if part]
        return ", ".join(parts) if parts else None

    # skip sub-tables
    if isinstance(value, dict):
        return None

    text = str(value).strip()
    return text or None


def field_value(metadata, key):
    return None if key.startswith(LINK_PREFIX) else getattr(metadata, key)


def detail_rows(metadata):
    """Rows for the DeckMetadata fields we have a label for, in DETAIL_FIELDS order."""
    rows = []
    for key, label in DETAIL_FIELDS:
        addresses = [display_address(url) for url in links_for(key, metadata)]
        text = "\n".join(filter(None, [format_value(field_value(metadata, key)), *addresses]))
        if not text:
            continue
        if key in DATE_KEYS:
            text = format_date(text)
        elif key == "license":
            text = license_name(text)
        rows.append((label, text, key))
    return rows


def links_for(key, metadata):
    """URLs the detail row `key` presents."""
    if key.startswith(LINK_PREFIX):
        rel = key.removeprefix(LINK_PREFIX)
    elif key == "publisher":
        rel = "publisher"
    else:
        return []
    return [link.url for link in metadata.links if link.rel == rel]


def buy_link(metadata):
    """The first `buy` link as (url, title), or None."""
    for link in metadata.links:
        if link.rel == "buy":
            return link.url, link.title
    return None
