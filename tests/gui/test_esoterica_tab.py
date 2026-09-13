import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPalette, QPixmap
from PyQt6.QtWidgets import QLabel

from tarot_canvas.models.esoterica import Passage
from tarot_canvas.ui.palette import muted_text
from tarot_canvas.ui.tabs.card_view import esoterica_tab
from tarot_canvas.ui.tabs.card_view.esoterica_tab import (
    PASSAGES_PAGE,
    PLACEHOLDER_PAGE,
    EsotericaTab,
    PassageWidget,
)
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    HEADING_TO_BODY,
    PADDING,
    TITLE_TO_AUTHOR,
    column_width,
)

CARD = {"name": "The Star", "id": "major_arcana.17", "type": "major_arcana", "number": 17}


@pytest.fixture
def stub_manager(monkeypatch):
    """Nothing in this file may touch the user's esoterica directory."""

    def _apply(passages, has_sources=True):
        manager = SimpleNamespace(
            get_passages_for_card=lambda _card_id: passages, has_sources=lambda: has_sources
        )
        monkeypatch.setattr(esoterica_tab, "get_esoterica_manager", lambda: manager)

    return _apply


def labels(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


def text_colour(label):
    return label.palette().color(label.foregroundRole())


def make_widget(qtbot, passage):
    widget = PassageWidget(passage)
    qtbot.addWidget(widget)
    return widget


def make_tab(qtbot):
    tab = EsotericaTab(CARD)
    qtbot.addWidget(tab)
    return tab


def test_markup_in_a_passage_is_shown_rather_than_rendered(qtbot):
    widget = make_widget(qtbot, Passage("Notes", None, '<img src="http://evil/x.png">'))

    assert "&lt;img" in labels(widget)[-1]


def test_paragraph_breaks_still_become_markup(qtbot):
    widget = make_widget(qtbot, Passage("Notes", None, "First.\n\nSecond.\nSame paragraph."))

    body = labels(widget)[-1]
    assert body.count("<p ") == 2
    assert ">First.</p>" in body
    assert ">Second.<br>Same paragraph.</p>" in body


def test_a_source_with_no_author_gets_no_author_line(qtbot):
    widget = make_widget(qtbot, Passage("my-notes", None, "Body."))

    assert labels(widget)[:-1] == ["my-notes"]
    assert widget.author is None


def test_a_declared_author_is_credited(qtbot):
    widget = make_widget(qtbot, Passage("Example", "Jane Done", "Body."))

    assert labels(widget)[:-1] == ["Example", "by Jane Done"]


def test_the_author_line_follows_the_palette(qtbot, theme_palette):
    widget = make_widget(qtbot, Passage("Example", "Jane Done", "Body."))

    widget.setPalette(theme_palette)

    assert widget.author.font().italic()
    assert text_colour(widget.author) == muted_text(theme_palette)
    assert widget.styleSheet() == ""


def test_two_sources_render_as_two_widgets_rather_than_merging(qtbot, stub_manager):
    stub_manager([Passage("A", None, "One."), Passage("B", None, "Two.")])

    tab = make_tab(qtbot)

    assert [w.findChildren(QLabel)[0].text() for w in tab.passage_widgets] == ["A", "B"]


def test_a_card_with_nothing_written_about_it_says_so(qtbot, stub_manager):
    """Sources are loaded, just none for this card"""
    stub_manager([])

    tab = make_tab(qtbot)

    assert tab.stack.currentIndex() == PASSAGES_PAGE
    assert tab.passage_widgets == []
    assert not tab.no_content_label.isHidden()


def test_with_no_sources_at_all_the_placeholder_shows(qtbot, stub_manager):
    stub_manager([], has_sources=False)

    tab = make_tab(qtbot)

    assert tab.stack.currentIndex() == PLACEHOLDER_PAGE
    assert tab.passage_widgets == []
    assert not tab.header_label.isVisibleTo(tab)


def test_the_placeholder_copy_is_still_unwritten():
    """No machine-written sentence may reach a user (AI-POLICY.md).

    Adam deletes this test when he writes the copy.
    """
    assert esoterica_tab.PLACEHOLDER_HEADING == ""
    assert esoterica_tab.PLACEHOLDER_EXPLANATION == ""
    assert esoterica_tab.PLACEHOLDER_FOOTNOTE == ""


def test_the_faq_token_becomes_a_link_to_the_esoterica_section(qtbot, stub_manager, monkeypatch):
    stub_manager([], has_sources=False)
    monkeypatch.setattr(esoterica_tab, "PLACEHOLDER_EXPLANATION", '<a href="{faq}">x</a>')
    monkeypatch.setattr(esoterica_tab, "PLACEHOLDER_FOOTNOTE", '<a href="{faq}">y</a>')

    tab = make_tab(qtbot)

    url = esoterica_tab.esoterica_faq_url()
    assert url.endswith("/docs/FAQs.md#" + esoterica_tab.ESOTERICA_FAQ_ANCHOR)
    assert f'href="{url}"' in tab.placeholder.explanation.text()
    assert f'href="{url}"' in tab.placeholder.footnote.text()


def github_slug(heading):
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def test_the_faq_anchor_names_a_heading_in_the_faq():
    """Renumbering or renaming the FAQ's esoterica section breaks the link"""
    faq = Path(__file__).parents[2] / "docs" / "FAQs.md"
    slugs, fenced = set(), False
    for line in faq.read_text(encoding="utf-8").splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and (heading := re.match(r"#{1,6} (.*)", line)):
            slugs.add(github_slug(heading[1]))

    assert esoterica_tab.ESOTERICA_FAQ_ANCHOR in slugs


@pytest.fixture
def theme_has_icon(monkeypatch):
    """Any icon name resolves to an opaque square"""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.black)
    monkeypatch.setattr(QIcon, "hasThemeIcon", staticmethod(lambda _: True))
    monkeypatch.setattr(QIcon, "fromTheme", staticmethod(lambda _: QIcon(pixmap)))


def test_the_header_names_the_tab_as_the_empty_page_does(qtbot, stub_manager):
    stub_manager([Passage("A", None, "One.")])

    tab = make_tab(qtbot)

    assert tab.header_label.text() == esoterica_tab.PLACEHOLDER_HEADING


def test_the_header_icon_takes_the_header_text_colour(
    qtbot, stub_manager, theme_has_icon, theme_palette
):
    stub_manager([Passage("A", None, "One.")])
    tab = make_tab(qtbot)

    tab.setPalette(theme_palette)

    image = tab.header_icon.grab().toImage()
    text = theme_palette.color(QPalette.ColorRole.WindowText).rgb()
    assert tab.header_icon.width() == esoterica_tab.HEADER_ICON_SIZE
    assert image.pixelColor(image.rect().center()).rgb() == text


def test_with_no_header_icon_the_header_is_text_alone(
    qtbot, stub_manager, theme_has_icon, monkeypatch
):
    monkeypatch.setattr(esoterica_tab, "HEADER_ICON", None)
    stub_manager([Passage("A", None, "One.")])

    tab = make_tab(qtbot)

    assert tab.header_icon is None


def test_the_nothing_here_line_follows_the_palette(qtbot, stub_manager, theme_palette):
    stub_manager([])
    tab = make_tab(qtbot)

    tab.setPalette(theme_palette)

    assert tab.no_content_label.font().italic()
    assert text_colour(tab.no_content_label) == muted_text(theme_palette)


LONG_TEXT = "word " * 400


def show(qtbot, widget, width, height=800):
    widget.resize(width, height)
    widget.show()
    qtbot.waitExposed(widget)


def test_title_and_author_group_apart_from_the_body(qtbot):
    widget = make_widget(qtbot, Passage("Example", "Jane Done", "Body."))
    show(qtbot, widget, 400, 300)

    title, author, body = widget.title, widget.author, widget.body
    assert title.x() == widget.frameWidth() + PADDING
    assert author.y() - title.geometry().bottom() - 1 == TITLE_TO_AUTHOR
    assert body.y() - author.geometry().bottom() - 1 == HEADING_TO_BODY


def test_body_lines_are_spaced_wider_than_the_font_sets_them(qtbot):
    widget = make_widget(qtbot, Passage("Example", None, LONG_TEXT))
    plain = QLabel(LONG_TEXT)
    plain.setWordWrap(True)
    qtbot.addWidget(plain)

    assert widget.body.heightForWidth(300) > 1.2 * plain.heightForWidth(300)


def test_a_wide_view_centres_a_capped_reading_column(qtbot, stub_manager):
    stub_manager([Passage("A", "B", LONG_TEXT)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 1600)

    column, viewport = tab.content_widget, tab.content_widget.parentWidget()
    assert column.width() == column_width(column.font()) < viewport.width()
    assert abs(column.x() - (viewport.width() - column.width()) / 2) <= 1


def test_a_narrow_view_gives_the_column_all_its_width(qtbot, stub_manager):
    stub_manager([Passage("A", "B", LONG_TEXT)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 400)

    column, viewport = tab.content_widget, tab.content_widget.parentWidget()
    assert column.width() == viewport.width()


def test_the_header_lines_up_with_the_passages(qtbot, stub_manager):
    stub_manager([Passage("A", "B", LONG_TEXT)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 1600)

    first_in_header = tab.header_icon or tab.header_label
    assert first_in_header.x() == tab.passage_widgets[0].x()
