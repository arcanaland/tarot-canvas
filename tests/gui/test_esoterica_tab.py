import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, Qt
from PyQt6.QtGui import QIcon, QPalette, QPixmap
from PyQt6.QtWidgets import (
    QFormLayout,
    QLabel,
    QProxyStyle,
    QStyle,
    QStyleFactory,
    QToolButton,
)

from tarot_canvas.models.esoterica import Entry, GroupReading, SourceReading
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.esoterica_registry import (
    CORRESPONDENCES,
    PASSAGES,
    SYMBOLS,
    Role,
    role_of,
)
from tarot_canvas.settings import set_esoterica_expanded
from tarot_canvas.ui import esoterica_text
from tarot_canvas.ui.palette import muted_text
from tarot_canvas.ui.tabs.card_view import esoterica_tab
from tarot_canvas.ui.tabs.card_view.esoterica_tab import (
    PASSAGES_PAGE,
    PLACEHOLDER_PAGE,
    EsotericaTab,
    PassageWidget,
)
from tarot_canvas.ui.tabs.card_view.passage_metrics import (
    HEADER_TO_ROWS,
    PADDING,
    TITLE_TO_AUTHOR,
    column_width,
)

CARD = {"name": "The Star", "id": "major_arcana.17", "type": "major_arcana", "number": 17}


# Formats rather than labels; they keep their shipped values
FORMATS = ("joiner", "count")


@pytest.fixture(autouse=True)
def blank_labels(monkeypatch):
    """Every test starts with every label empty and fills the ones it needs, so none depends
    on what the edition ships"""
    for key in esoterica_text.ESOTERICA_TEXT:
        if key not in FORMATS:
            monkeypatch.setitem(esoterica_text.ESOTERICA_TEXT, key, "")


@pytest.fixture
def stub_manager(monkeypatch):
    """Nothing in this file may touch the user's esoterica directory."""

    def _apply(readings, has_sources=True, families=frozenset()):
        # A dict gives each card id its own readings
        by_card = readings if isinstance(readings, dict) else None
        manager = SimpleNamespace(
            read_card=lambda card_id: by_card.get(card_id, []) if by_card else readings,
            has_sources=lambda: has_sources,
            families_present=lambda: frozenset(families),
        )
        monkeypatch.setattr(esoterica_tab, "get_esoterica_manager", lambda: manager)

    return _apply


def essay(name, author, text):
    """A source that has only prose for the card, as most hand-written notes do"""
    return SourceReading(name, author, (Entry(PASSAGES, "text", Role.PRINCIPAL, text),), ())


def labels(widget):
    """Every label's text, and every fold header's, in creation order"""
    return [child.text() for child in widget.findChildren((QLabel, QToolButton)) if child.text()]


def text_colour(label):
    return label.palette().color(label.foregroundRole())


def make_widget(qtbot, reading, card=None):
    widget = PassageWidget(reading, card)
    qtbot.addWidget(widget)
    return widget


def make_tab(qtbot):
    tab = EsotericaTab(CARD)
    qtbot.addWidget(tab)
    return tab


def test_markup_in_a_passage_is_shown_rather_than_rendered(qtbot):
    widget = make_widget(qtbot, essay("Notes", None, '<img src="http://evil/x.png">'))

    assert "&lt;img" in labels(widget)[-1]


def test_paragraph_breaks_still_become_markup(qtbot):
    widget = make_widget(qtbot, essay("Notes", None, "First.\n\nSecond.\nSame paragraph."))

    body = labels(widget)[-1]
    assert body.count("<p ") == 2
    assert ">First.</p>" in body
    assert ">Second.<br>Same paragraph.</p>" in body


def test_a_source_with_no_author_is_credited_by_name_alone(qtbot):
    widget = make_widget(qtbot, essay("my-notes", None, "Body."))

    assert labels(widget)[:-1] == ["my-notes"]


def test_a_declared_author_shares_the_source_line(qtbot):
    widget = make_widget(qtbot, essay("Example", "Jane Done", "Body."))

    assert labels(widget)[:-1] == ["Example · Jane Done"]


def test_the_source_line_is_quiet_and_follows_the_palette(qtbot, theme_palette):
    widget = make_widget(qtbot, essay("Example", "Jane Done", "Body."))

    widget.setPalette(theme_palette)

    assert not widget.source.font().bold()
    assert widget.source.font().pointSizeF() < QLabel().font().pointSizeF()
    assert text_colour(widget.source) == muted_text(theme_palette)
    assert widget.styleSheet() == ""


def test_two_sources_render_as_two_widgets_rather_than_merging(qtbot, stub_manager):
    stub_manager([essay("A", None, "One."), essay("B", None, "Two.")])

    tab = make_tab(qtbot)

    assert [w.source.text() for w in tab.passage_widgets] == ["A", "B"]


def test_a_card_with_nothing_written_about_it_says_so(qtbot, stub_manager):
    """Sources are loaded, just none for this card"""
    stub_manager([])

    tab = make_tab(qtbot)

    assert tab.stack.currentIndex() == PASSAGES_PAGE
    assert tab.passage_widgets == []
    assert not tab.no_content.isHidden()
    assert tab.no_content.heading.text() == esoterica_tab.NO_CONTENT_TEXT


def test_with_no_sources_at_all_the_placeholder_shows(qtbot, stub_manager):
    stub_manager([], has_sources=False)

    tab = make_tab(qtbot)

    assert tab.stack.currentIndex() == PLACEHOLDER_PAGE
    assert tab.passage_widgets == []
    assert not tab.header_label.isVisibleTo(tab)


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


def test_the_header_names_the_tab_as_the_empty_page_does(qtbot, stub_manager):
    stub_manager([essay("A", None, "One.")])

    tab = make_tab(qtbot)

    assert tab.header_label.text() == esoterica_tab.PLACEHOLDER_HEADING


@pytest.fixture
def opaque_header_icon(monkeypatch, tmp_path):
    """The header's icon file is an opaque square"""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.black)
    path = tmp_path / "opaque.png"
    pixmap.save(str(path))
    monkeypatch.setattr(esoterica_tab, "HEADER_ICON", path)


def test_the_header_icon_takes_the_header_text_colour(
    qtbot, stub_manager, opaque_header_icon, theme_palette
):
    stub_manager([essay("A", None, "One.")])
    tab = make_tab(qtbot)

    tab.setPalette(theme_palette)

    image = tab.header_icon.grab().toImage()
    text = theme_palette.color(QPalette.ColorRole.WindowText).rgb()
    assert tab.header_icon.width() == esoterica_tab.HEADER_ICON_SIZE
    assert image.pixelColor(image.rect().center()).rgb() == text


def test_with_no_header_icon_the_header_is_text_alone(qtbot, stub_manager, monkeypatch):
    monkeypatch.setattr(esoterica_tab, "HEADER_ICON", None)
    stub_manager([essay("A", None, "One.")])

    tab = make_tab(qtbot)

    assert tab.header_icon is None


def test_nothing_for_this_card_shows_the_tabs_icon(qtbot, stub_manager):
    stub_manager([])

    tab = make_tab(qtbot)

    assert tab.no_content.icon_slot is not None


LONG_TEXT = "word " * 400


def show(qtbot, widget, width, height=800):
    widget.resize(width, height)
    widget.show()
    qtbot.waitExposed(widget)


def test_source_and_lead_group_apart_from_the_body(qtbot):
    reading = essay("Example", "Jane Done", "Body.")
    reading = SourceReading(
        reading.name, reading.author, (entry("x_subtitle", "Lead"), *reading.entries), ()
    )
    widget = make_widget(qtbot, reading)
    show(qtbot, widget, 400, 300)

    source, lead, body = widget.source, widget.lead, widget.body
    assert source.x() == widget.frameWidth() + PADDING
    assert lead.y() - source.geometry().bottom() - 1 == TITLE_TO_AUTHOR
    assert body.y() - lead.geometry().bottom() - 1 == HEADER_TO_ROWS


def test_body_lines_are_spaced_wider_than_the_font_sets_them(qtbot):
    widget = make_widget(qtbot, essay("Example", None, LONG_TEXT))
    plain = QLabel(LONG_TEXT)
    plain.setWordWrap(True)
    qtbot.addWidget(plain)

    assert widget.body.heightForWidth(300) > 1.2 * plain.heightForWidth(300)


def test_a_wide_view_centres_a_capped_reading_column(qtbot, stub_manager):
    stub_manager([essay("A", "B", LONG_TEXT)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 1600)

    column, viewport = tab.content_widget, tab.content_widget.parentWidget()
    assert column.width() == column_width(column.font()) < viewport.width()
    assert abs(column.x() - (viewport.width() - column.width()) / 2) <= 1


def test_a_narrow_view_gives_the_column_all_its_width(qtbot, stub_manager):
    stub_manager([essay("A", "B", LONG_TEXT)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 400)

    column, viewport = tab.content_widget, tab.content_widget.parentWidget()
    assert column.width() == viewport.width()


def test_the_header_lines_up_with_the_passages(qtbot, stub_manager):
    stub_manager([essay("A", "B", LONG_TEXT)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 1600)

    first_in_header = tab.header_icon or tab.header_label
    assert first_in_header.x() == tab.passage_widgets[0].x()


# A source with more than prose: rows, families and groups


QUEEN = {"name": "Queen of Cups", "id": "minor_arcana.cups.queen", "display_suit": "Chalices"}


def entry(key, value, slot=PASSAGES):
    return Entry(slot, key, role_of(slot, key), value)


def correspondence(key, value):
    return entry(key, value, CORRESPONDENCES)


def symbol(name, text, label=None):
    return Entry(SYMBOLS, name, Role.SYMBOLS, text, label)


def many_rows(name="The Queen's Book", entries=(), groups=()):
    """Shaped like a book that writes many short sections per card, in registry order"""
    return SourceReading(
        name,
        "A. Writer",
        (
            *entries,
            entry("keywords", ("intuition", "care")),
            entry("light", "Light prose."),
            entry("shadow", "Shadow prose."),
            entry("personality", "Personality prose."),
            entry("questions", ("Who <listens>?", "Why?")),
            entry("affirmation", "I listen."),
            entry("advice.relationships", "Relationship advice."),
            entry("advice.work", "Work advice."),
            symbol("the_cup", "The cup prose.", "The Cup"),
            symbol("the_sea", "The sea prose."),
            entry("advice.timing", "Timing prose."),
            correspondence("element", "water"),
            correspondence("astrology", "saturn in libra"),
            correspondence("hebrew_letter_value", 20),
            correspondence("x_hebrew_letter_alt", "kaph"),
            entry("x_unknown_thing", "Unknown prose."),
        ),
        groups,
    )


@pytest.fixture
def label(monkeypatch):
    """Fill one label for the test, as the edition one day will"""

    def _apply(key, text):
        monkeypatch.setitem(esoterica_text.ESOTERICA_TEXT, key, text)

    return _apply


@pytest.fixture
def every_label(label):
    for key in esoterica_text.ESOTERICA_TEXT:
        if key not in FORMATS:
            label(key, f"[{key}]")


def all_text(widget):
    return "\n".join(labels(widget))


def test_a_prose_only_source_looks_as_it_always_has(qtbot):
    widget = make_widget(qtbot, essay("Example", "Jane Done", "Body."))

    assert labels(widget) == ["Example · Jane Done", esoterica_tab._body_html("Body.")]
    assert widget.body.text() == esoterica_tab._body_html("Body.")
    assert widget.lead is None


def test_with_every_label_empty_only_the_keywords_show_and_they_lead(qtbot, stub_manager):
    stub_manager([many_rows()])

    tab = make_tab(qtbot)

    (frame,) = tab.passage_widgets
    assert labels(frame) == ["The Queen's Book · A. Writer", "intuition · care"]
    assert frame.lead.text() == "intuition · care"
    assert frame.lead.font().bold()
    assert frame.headings == []


def test_a_frame_with_every_row_hidden_is_still_drawn(qtbot, stub_manager):
    stub_manager([SourceReading("Terse", None, (entry("light", "Light prose."),), ())])

    tab = make_tab(qtbot)

    (frame,) = tab.passage_widgets
    assert labels(frame) == ["Terse"]
    assert tab.no_content.isHidden()


def test_a_filled_label_shows_its_row_under_it(qtbot, label):
    label("light", "On the light side")

    widget = make_widget(qtbot, many_rows())

    texts = labels(widget)
    heading = texts.index("On the light side")
    assert "Light prose." in texts[heading + 1]
    assert "Shadow prose." not in all_text(widget)


def test_the_epithet_leads_and_the_keywords_follow_as_body_text(qtbot, theme_palette):
    reading = many_rows(entries=(entry("x_subtitle", "The Dreamer"),))
    widget = make_widget(qtbot, reading)
    widget.setPalette(theme_palette)

    assert labels(widget)[:3] == ["The Queen's Book · A. Writer", "The Dreamer", "intuition · care"]
    assert widget.lead.text() == "The Dreamer"
    assert widget.lead.font().bold()
    assert text_colour(widget.lead) != muted_text(theme_palette)
    (keywords,) = (
        label for label in widget.findChildren(QLabel) if label.text() == "intuition · care"
    )
    assert not keywords.font().bold()


def test_the_lead_is_the_frames_only_bold_text(qtbot):
    reading = many_rows(entries=(entry("x_subtitle", "The Dreamer"),))
    widget = make_widget(qtbot, reading)

    assert [label.text() for label in widget.findChildren(QLabel) if label.font().bold()] == [
        "The Dreamer"
    ]


def test_a_label_is_muted_and_follows_the_palette(qtbot, label, theme_palette):
    label("light", "On the light side")
    widget = make_widget(qtbot, many_rows())
    (heading,) = widget.headings
    plain_size = QLabel().font().pointSizeF()

    widget.setPalette(theme_palette)

    assert heading.font().bold()
    assert heading.font().pointSizeF() < plain_size
    assert text_colour(heading) == muted_text(theme_palette)


def form_rows(widget):
    (form,) = widget.findChildren(QFormLayout)
    role = QFormLayout.ItemRole
    return [
        (
            form.itemAt(row, role.LabelRole).widget().text(),
            form.itemAt(row, role.FieldRole).widget().text(),
        )
        for row in range(form.rowCount())
    ]


def test_correspondences_are_verbatim_and_in_registry_order(qtbot, every_label):
    widget = make_widget(qtbot, many_rows())

    assert form_rows(widget) == [
        ("[element]", "water"),
        ("[astrology]", "saturn in libra"),
        ("[hebrew_letter_value]", "20"),
        ("[x_hebrew_letter_alt]", "kaph"),
    ]


def test_a_correspondence_without_a_label_is_not_drawn(qtbot, label):
    label("family.correspondences", "Correspondences")
    label("astrology", "Astrology")

    widget = make_widget(qtbot, many_rows())

    assert form_rows(widget) == [("Astrology", "saturn in libra")]


class FieldsStayAtSizeHint(QProxyStyle):
    """Lays out forms as Breeze and macOS do"""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_FormLayoutFieldGrowthPolicy:
            return QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint.value
        return super().styleHint(hint, option, widget, returnData)


@pytest.fixture
def size_hint_forms(qapp):
    original = qapp.style().name()
    qapp.setStyle(FieldsStayAtSizeHint(QStyleFactory.create(original)))
    yield
    qapp.setStyle(QStyleFactory.create(original))


def test_a_wrapping_correspondence_is_never_cut_to_one_line(qtbot, label, size_hint_forms):
    label("family.correspondences", "Correspondences")
    label("numerology", "Numerology")
    reading = SourceReading(
        "A", None, (correspondence("numerology", "9 (fullness, readiness, ripeness)"),), ()
    )
    widget = make_widget(qtbot, reading)
    widget.folds["correspondences"][0].header.click()
    show(qtbot, widget, 700, 300)

    (form,) = widget.findChildren(QFormLayout)
    value = form.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()
    assert value.height() >= value.heightForWidth(value.width())
    assert value.heightForWidth(value.width()) == value.fontMetrics().height()


def test_questions_are_spaced_apart_like_the_prose(qtbot):
    questions = ("What would happen?", "How can I?", "Who has walked this path?")
    spaced = esoterica_tab.list_row(questions)
    tight = QLabel("<ul>" + "".join(f"<li>{q}</li>" for q in questions) + "</ul>")
    tight.setWordWrap(True)
    qtbot.addWidget(spaced)
    qtbot.addWidget(tight)

    gaps = 2 * esoterica_tab.LIST_ITEM_GAP
    assert spaced.heightForWidth(600) > tight.heightForWidth(600) + gaps


def test_correspondence_values_are_spelled_as_toml_spells_them():
    assert esoterica_tab._spelled(True) == "true"
    assert esoterica_tab._spelled(20) == "20"
    assert esoterica_tab._spelled(("fire", 3)) == "fire · 3"


def test_divination_is_its_own_block_after_the_symbols(qtbot, every_label):
    widget = make_widget(qtbot, many_rows())

    text = all_text(widget)
    advice, symbols = text.index("[family.advice]"), text.index("[family.symbols]")
    divinatory = text.index("[family.divinatory]")
    assert advice < text.index("Work advice.") < symbols < divinatory < text.index("Timing prose.")


def test_a_symbol_has_no_heading_of_its_own(qtbot, every_label):
    widget = make_widget(qtbot, many_rows())

    assert "The cup prose." in all_text(widget)
    assert "the_cup" not in all_text(widget)
    assert "the_sea" not in all_text(widget)


def symbols_fold(widget):
    (fold,) = widget.folds["symbols"]
    return fold


def label_with(widget, text):
    (found,) = (label for label in widget.findChildren(QLabel) if text in label.text())
    return found


def test_a_printed_heading_sits_above_its_symbol_in_the_paragraphs_face(
    qtbot, theme_palette, label
):
    label("family.symbols", "Symbols")
    widget = make_widget(qtbot, many_rows())
    widget.setPalette(theme_palette)
    symbols_fold(widget).header.click()
    show(qtbot, widget, 600)

    heading, paragraph = label_with(widget, "The Cup"), label_with(widget, "The cup prose.")
    assert heading.text() == "The Cup"
    above = heading.mapTo(widget, heading.rect().bottomLeft()).y()
    assert above <= paragraph.mapTo(widget, paragraph.rect().topLeft()).y()
    assert heading.font().family() == paragraph.font().family()
    assert heading.font().pointSizeF() == paragraph.font().pointSizeF()
    assert heading.font().bold()
    assert not paragraph.font().bold()
    # The source's words, not the edition's
    assert heading not in widget.headings
    assert text_colour(heading) == text_colour(paragraph)


def test_a_symbol_without_a_printed_heading_is_its_paragraph_alone(qtbot, label):
    label("family.symbols", "Symbols")
    widget = make_widget(qtbot, many_rows())

    texts = [found.text() for found in symbols_fold(widget).content.findChildren(QLabel)]
    assert texts == [
        "The Cup",
        esoterica_tab._body_html("The cup prose."),
        esoterica_tab._body_html("The sea prose."),
    ]
    assert symbols_fold(widget).header.text() == "Symbols 2"


def marseille_reading():
    """Symbols, then the image, in registry order as the manager gives them"""
    return SourceReading(
        "A Guide",
        None,
        (
            symbol("the_sun", "The sun prose.", "The Sun"),
            symbol("the_moon", "The moon prose."),
            entry("x_marseille_image", "Two batons."),
            entry("advice.timing", "Timing prose."),
        ),
        (),
    )


def test_the_marseille_image_is_hidden_while_its_label_is_empty(qtbot, label):
    label("family.symbols", "Symbols")
    widget = make_widget(qtbot, marseille_reading())

    assert "Two batons." not in all_text(widget)
    assert symbols_fold(widget).header.text() == "Symbols 2"


def test_a_labelled_marseille_image_is_the_last_row_in_the_symbols_fold(qtbot, label):
    label("family.symbols", "Symbols")
    label("x_marseille_image", "The Marseille card")
    widget = make_widget(qtbot, marseille_reading())

    fold = symbols_fold(widget)
    texts = [found.text() for found in fold.content.findChildren(QLabel)]
    assert texts[:2] == ["The Sun", esoterica_tab._body_html("The sun prose.")]
    assert texts[-2] == "The Marseille card"
    assert texts[-1] == esoterica_tab._body_html("Two batons.")
    assert fold.header.text() == "Symbols 3"


def test_questions_are_a_list_of_escaped_strings(qtbot, label):
    label("questions", "Ask yourself")

    widget = make_widget(qtbot, many_rows())

    (questions,) = (text for text in labels(widget) if "<ul>" in text)
    assert questions.count("<li ") == 2
    assert "Who &lt;listens&gt;?" in questions


def test_an_unknown_key_is_never_drawn(qtbot, every_label):
    widget = make_widget(qtbot, many_rows())

    assert "Unknown prose." not in all_text(widget)


def test_sources_keep_their_order_and_never_share_a_frame(qtbot, stub_manager, every_label):
    stub_manager([many_rows("A"), essay("B", None, "Two.")])
    tab = make_tab(qtbot)

    for card in (CARD, QUEEN):
        tab.update_card_info(card)

        assert [frame.source.text() for frame in tab.passage_widgets] == ["A · A. Writer", "B"]
        for frame in tab.passage_widgets:
            for text in frame.findChildren(QLabel):
                frames, parent = 0, text
                while parent is not None:
                    frames += isinstance(parent, PassageWidget)
                    parent = parent.parentWidget()
                assert frames == 1


def suit_group(text="Water and feeling."):
    return GroupReading("suits.cups", "suits", (entry("text", text),))


def test_the_suit_group_names_the_suit_in_the_decks_own_word(qtbot, label):
    label("family.groups", "Groups")
    label("group.suits", "On {suit}")

    widget = make_widget(qtbot, many_rows(groups=(suit_group(),)), QUEEN)

    texts = labels(widget)
    assert "Water and feeling." in texts[texts.index("On Chalices 1") + 1]


def test_a_group_without_a_label_is_not_drawn(qtbot):
    widget = make_widget(qtbot, SourceReading("A", None, (), (suit_group(),)), QUEEN)

    assert labels(widget) == ["A"]


def test_a_groups_prose_is_not_the_cards_body(qtbot, label):
    label("family.groups", "Groups")
    label("group.suits", "On {suit}")

    widget = make_widget(qtbot, SourceReading("A", None, (), (suit_group(),)), QUEEN)

    assert "group.suits" in widget.folds
    assert widget.body is None


def court_groups():
    rank = GroupReading("ranks.queen", "ranks", (entry("text", "Queens."),))
    court = GroupReading("classes.court", "classes", (entry("text", "Courts."),))
    return (suit_group(), rank, court)


def test_every_group_folds_inside_one_groups_fold(qtbot, every_label):
    widget = make_widget(qtbot, many_rows(groups=court_groups()), QUEEN)

    (outer,) = widget.folds["groups"]
    assert outer.header.text() == "[family.groups] 3"
    assert not outer.is_expanded()
    inner = [widget.folds[key][0] for key in ("group.suits", "group.ranks", "group.classes")]
    assert all(outer.content.isAncestorOf(fold) for fold in inner)


def test_the_groups_fold_is_the_frames_last_row(qtbot, every_label):
    widget = make_widget(qtbot, many_rows(groups=court_groups()), QUEEN)

    rows = [widget.layout().itemAt(i).widget() for i in range(widget.layout().count())]
    assert [row for row in rows if row is not None][-1] is widget.folds["groups"][0]


def test_without_a_groups_label_no_group_is_drawn(qtbot, every_label, label):
    label("family.groups", "")

    widget = make_widget(qtbot, many_rows(groups=court_groups()), QUEEN)

    assert not any(key.startswith("group") for key in widget.folds)
    assert "Queens." not in all_text(widget)


# Folds and the show menu


SWORDS = {"name": "Queen of Swords", "id": "minor_arcana.swords.queen", "display_suit": "Swords"}

COURT_FAMILIES = {"advice", "symbols", "divinatory", "correspondences", "groups"}


def first_fold(tab, fold_id, frame=0):
    return tab.passage_widgets[frame].folds[fold_id][0]


def is_open(tab, fold_id):
    folds = [fold for frame in tab.passage_widgets for fold in frame.folds.get(fold_id, [])]
    assert folds
    return all(fold.is_expanded() and not fold.content.isHidden() for fold in folds)


def test_every_fold_starts_closed_and_says_how_many_rows_it_holds(qtbot, stub_manager, every_label):
    stub_manager([many_rows()])
    tab = make_tab(qtbot)

    (frame,) = tab.passage_widgets
    assert set(frame.folds) == {"advice", "symbols", "divinatory", "correspondences"}
    assert not any(fold.is_expanded() for folds in frame.folds.values() for fold in folds)
    assert first_fold(tab, "advice").header.text() == "[family.advice] 2"
    assert first_fold(tab, "correspondences").header.text() == "[family.correspondences] 4"


def test_the_rows_outside_any_family_are_never_folded(qtbot, stub_manager, every_label):
    stub_manager([many_rows()])
    tab = make_tab(qtbot)

    folded = {
        label
        for folds in tab.passage_widgets[0].folds.values()
        for fold in folds
        for label in fold.content.findChildren(QLabel)
    }
    light = next(label for label in frame_labels(tab) if "Light prose." in label.text())
    assert light not in folded
    assert not light.isHidden()


def test_an_open_fold_stays_open_on_the_next_card(qtbot, stub_manager, every_label):
    stub_manager([many_rows()])
    tab = make_tab(qtbot)

    first_fold(tab, "advice").header.click()
    tab.update_card_info(QUEEN)

    assert is_open(tab, "advice")
    assert not is_open(tab, "symbols")


def test_opening_a_fold_in_one_card_tab_opens_it_in_another(qtbot, stub_manager, every_label):
    stub_manager([many_rows()])
    here, there = make_tab(qtbot), make_tab(qtbot)

    first_fold(here, "symbols").header.click()

    assert is_open(there, "symbols")
    first_fold(there, "symbols").header.click()
    assert not is_open(here, "symbols")


def test_a_suits_fold_opened_on_cups_is_open_on_swords(qtbot, stub_manager, every_label):
    swords = GroupReading("suits.swords", "suits", (entry("text", "Air and thought."),))
    stub_manager(
        {
            QUEEN["id"]: [many_rows(groups=(suit_group(),))],
            SWORDS["id"]: [many_rows(groups=(swords,))],
        }
    )
    tab = EsotericaTab(QUEEN)
    qtbot.addWidget(tab)

    first_fold(tab, "group.suits").header.click()
    tab.update_card_info(SWORDS)

    assert is_open(tab, "group.suits")
    assert "Air and thought." in all_text(first_fold(tab, "group.suits"))


@pytest.fixture
def menu_icon(monkeypatch):
    """The theme has an icon for the show menu"""
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.black)
    monkeypatch.setattr(esoterica_tab, "_show_menu_icon", lambda: QIcon(pixmap))


def menu_entries(tab):
    return [action.text() for action in tab.show_menu.actions()]


def frame_labels(tab):
    """The current frames' labels; frames a re-render replaced may not be deleted yet"""
    return [label for frame in tab.passage_widgets for label in frame.findChildren(QLabel)]


def divinatory_text(tab):
    return [label for label in frame_labels(tab) if "Timing prose." in label.text()]


def test_hiding_a_family_removes_it_from_every_frame_in_every_tab(
    qtbot, stub_manager, every_label, menu_icon
):
    stub_manager([many_rows("A"), many_rows("B")], families=COURT_FAMILIES)
    here, there = make_tab(qtbot), make_tab(qtbot)
    first_fold(here, "divinatory").header.click()

    here.show_actions["divinatory"].setChecked(False)

    for tab in (here, there):
        assert [frame.folds.get("divinatory") for frame in tab.passage_widgets] == [None, None]
        assert divinatory_text(tab) == []
        assert not tab.show_actions["divinatory"].isChecked()
        assert any("Work advice." in label.text() for label in frame_labels(tab))

    there.show_actions["divinatory"].setChecked(True)

    for tab in (here, there):
        assert is_open(tab, "divinatory")
        assert len(divinatory_text(tab)) == 2


def test_hiding_groups_hides_every_group_fold(qtbot, stub_manager, every_label, menu_icon):
    stub_manager([many_rows(groups=(suit_group(),))], families=COURT_FAMILIES)
    tab = EsotericaTab(QUEEN)
    qtbot.addWidget(tab)

    tab.show_actions["groups"].setChecked(False)

    (frame,) = tab.passage_widgets
    assert "group.suits" not in frame.folds
    assert not any("Water and feeling." in label.text() for label in frame_labels(tab))


def test_a_frame_left_empty_by_hiding_is_still_drawn(qtbot, stub_manager, every_label, menu_icon):
    only_advice = SourceReading("Terse", None, (entry("advice.work", "Work advice."),), ())
    stub_manager([only_advice], families={"advice"})
    tab = make_tab(qtbot)

    tab.show_actions["advice"].setChecked(False)

    (frame,) = tab.passage_widgets
    assert labels(frame) == ["Terse"]


def test_with_only_essays_there_is_no_show_menu(qtbot, stub_manager, every_label, menu_icon):
    stub_manager([essay("A", None, "One.")])
    tab = make_tab(qtbot)

    assert tab.show_actions == {}
    assert tab.show_button.isHidden()


def test_the_menu_offers_only_the_families_sources_have_in_order(
    qtbot, stub_manager, every_label, menu_icon
):
    stub_manager([many_rows()], families={"groups", "divinatory", "advice"})
    tab = make_tab(qtbot)

    assert menu_entries(tab) == ["[family.advice]", "[family.divinatory]", "[family.groups]"]
    assert all(action.isChecked() for action in tab.show_menu.actions())
    assert not tab.show_button.isHidden()


def test_a_family_with_no_label_has_no_menu_entry(
    qtbot, stub_manager, every_label, label, menu_icon
):
    label("family.symbols", "")
    stub_manager([many_rows()], families=COURT_FAMILIES)
    tab = make_tab(qtbot)

    assert "symbols" not in tab.show_actions
    assert len(menu_entries(tab)) == 4


def test_without_a_theme_icon_the_menu_shows_its_label_or_nothing(
    qtbot, stub_manager, label, monkeypatch
):
    monkeypatch.setattr(esoterica_tab, "_show_menu_icon", lambda: QIcon())
    label("family.advice", "Advice")
    stub_manager([many_rows()], families={"advice"})
    assert make_tab(qtbot).show_button.isHidden()

    label("show_menu", "Show")
    label("show_menu_tooltip", "Which families to show")
    tab = make_tab(qtbot)

    assert not tab.show_button.isHidden()
    assert tab.show_button.text() == "Show"
    assert tab.show_button.toolTip() == "Which families to show"


def test_a_deleted_tab_no_longer_hears_display_changes(qtbot, stub_manager, every_label):
    stub_manager([many_rows()])
    events = esoterica_events()
    before = events.receivers(events.display_changed)
    tab = EsotericaTab(CARD)
    assert events.receivers(events.display_changed) == before + 1

    tab.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)

    assert events.receivers(events.display_changed) == before
    set_esoterica_expanded(["advice"])


def test_the_tab_that_opened_a_fold_keeps_its_scroll_position(qtbot, stub_manager, every_label):
    stub_manager([many_rows(str(i)) for i in range(6)])
    tab = make_tab(qtbot)
    show(qtbot, tab, 600, 400)
    bar = tab.scroll_area.verticalScrollBar()
    assert bar.maximum() > 300
    bar.setValue(300)

    first_fold(tab, "advice", frame=3).header.click()
    # The new frames are laid out and the old ones deleted
    qtbot.wait(50)

    assert bar.value() == 300
