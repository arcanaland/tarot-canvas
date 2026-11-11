import html

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFormLayout, QLabel


def pane_text(text=""):
    """A details pane's label"""
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return label


def pane_form():
    """A details pane's form."""
    form = QFormLayout()
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    return form


def is_link(value):
    return value.startswith("http://") or value.startswith("https://")


def display_address(url):
    """`url` as shown to a reader: no scheme, no trailing slash."""
    return url.split("://", 1)[-1].rstrip("/")


def link_html(text, urls):
    """`text`, if any, then one link per URL, a line each."""
    lines = [html.escape(text)] if text else []
    lines += [
        f'<a href="{html.escape(url)}">{html.escape(display_address(url))}</a>' for url in urls
    ]
    return "<br>".join(lines)
