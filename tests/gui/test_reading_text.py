"""Reading text in a card view has its own size, which the zoom keys change away from the art"""

from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication

from tarot_canvas.models.esoterica import Entry, SourceReading
from tarot_canvas.models.esoterica_registry import PASSAGES, Role
from tarot_canvas.settings import get_reading_text_scale
from tarot_canvas.ui import esoterica_text, typography
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.tabs.card_view import esoterica_tab, overview_tab
from tarot_canvas.ui.tabs.card_view.passage_metrics import column_width

PROSE = "The source's prose about the card."

READING = SourceReading(
    "A Source",
    "An Author",
    (
        Entry(PASSAGES, "keywords", Role.KEYWORDS, ("hope", "renewal")),
        Entry(PASSAGES, "text", Role.PRINCIPAL, PROSE),
    ),
    (),
)


@pytest.fixture(autouse=True)
def stub_esoterica(monkeypatch):
    """One source with keywords and prose for every card, and nothing read from disk"""
    manager = SimpleNamespace(
        read_card=lambda card_id, deck=None: [READING],
        has_enabled_sources=lambda: True,
        families_present=lambda: frozenset(),
    )
    for module in (esoterica_tab, overview_tab):
        monkeypatch.setattr(module, "get_esoterica_manager", lambda: manager)
    monkeypatch.setitem(esoterica_text.ESOTERICA_TEXT, "joiner", ", ")


def point_size(widget):
    return widget.font().pointSizeF()


def make_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    with qtbot.waitActive(window):
        window.activateWindow()
    return window


def open_card_view(window):
    window.new_card_view_tab()
    return window.tab_widget.currentWidget()


def prose_label(card_view):
    return card_view.esoterica_tab.passage_widgets[0].body


def focus(qtbot, widget):
    widget.setFocus(Qt.FocusReason.MouseFocusReason)
    qtbot.waitUntil(lambda: QApplication.focusWidget() is widget)


def ctrl(qtbot, widget, key):
    qtbot.keyClick(widget, key, Qt.KeyboardModifier.ControlModifier)


# -- what is reading text ----------------------------------------------------


def test_the_passages_scale_and_the_card_name_does_not(qtbot):
    card_view = open_card_view(make_window(qtbot))
    esoterica = card_view.esoterica_tab
    name = card_view.overview_tab.name_label

    def sizes():
        # Drawn again at each size, so looked up afresh
        passage = esoterica.passage_widgets[0]
        return [point_size(passage.body), point_size(passage.lead), point_size(passage.source)]

    before, name_before = sizes(), point_size(name)

    typography.set_reading_scale(150)

    assert sizes() == pytest.approx([1.5 * size for size in before], abs=0.5)
    assert point_size(name) == name_before


def test_the_reading_column_widens_with_the_text(qtbot):
    card_view = open_card_view(make_window(qtbot))
    content = card_view.esoterica_tab.content_widget
    before = content.maximumWidth()
    assert before == column_width(content.font())

    typography.set_reading_scale(150)

    assert content.maximumWidth() > before
    assert content.maximumWidth() == column_width(content.font())


def test_the_overview_headline_and_description_scale_and_its_chrome_does_not(qtbot):
    card_view = open_card_view(make_window(qtbot))
    overview = card_view.overview_tab
    chrome = (overview.name_label, overview.subtitle, overview.deck_value)
    reading = (overview.lead, overview.headline_source, overview.description_label)
    before = {widget: point_size(widget) for widget in chrome + reading}

    typography.set_reading_scale(200)

    for widget in chrome:
        assert point_size(widget) == before[widget]
    assert point_size(overview.headline_source) == pytest.approx(
        2 * before[overview.headline_source], abs=0.5
    )
    assert point_size(overview.description_label) == pytest.approx(
        2 * before[overview.description_label], abs=0.5
    )
    # Made again at the new size
    assert point_size(overview.lead) == pytest.approx(2 * before[reading[0]], abs=0.5)


def test_the_notes_editor_stays_monospace_and_follows_the_size(qtbot):
    card_view = open_card_view(make_window(qtbot))
    editor = card_view.notes_tab.note_editor
    before = point_size(editor)
    family = editor.font().family()

    typography.set_reading_scale(150)

    assert point_size(editor) == pytest.approx(1.5 * before, abs=0.5)
    assert editor.font().family() == family


def test_note_rows_in_a_card_view_scale(qtbot):
    card_view = open_card_view(make_window(qtbot))
    rows = (card_view.notes_tab.list_view, card_view.overview_tab.notes_section.list_view)
    before = {view: point_size(view) for view in rows}

    typography.set_reading_scale(150)

    for view in rows:
        assert point_size(view) == pytest.approx(1.5 * before[view], abs=0.5)


def test_every_open_card_view_follows_one_size(qtbot):
    window = make_window(qtbot)
    first = open_card_view(window)
    second = open_card_view(window)
    before = point_size(first.overview_tab.description_label)

    typography.set_reading_scale(125)

    for card_view in (first, second):
        assert point_size(card_view.overview_tab.description_label) == pytest.approx(
            1.25 * before, abs=0.5
        )


# -- the View menu's actions -------------------------------------------------


def zoom_actions(window):
    return (window.zoom_in_action, window.zoom_out_action, window.reset_zoom_action)


def test_the_zoom_actions_are_in_the_view_menu(qtbot):
    window = make_window(qtbot)
    view_menu = next(
        action.menu()
        for action in window.menuBar().actions()
        if action.menu() and action.text() == "&View"
    )
    for action in zoom_actions(window):
        assert action in view_menu.actions()


def test_in_the_library_the_zoom_actions_size_the_covers(qtbot):
    """Not the reading text: the Library has none, and its zoom is the cover size, which
    opens at its largest"""
    window = make_window(qtbot)
    window.new_library_tab()
    assert [action.isEnabled() for action in zoom_actions(window)] == [False, True, False]


@pytest.mark.parametrize(
    ("scale", "enabled"),
    [
        (100, (True, True, False)),
        (80, (True, False, True)),
        (200, (False, True, True)),
        (150, (True, True, True)),
    ],
)
def test_each_zoom_action_is_on_only_while_it_would_change_something(qtbot, scale, enabled):
    window = make_window(qtbot)
    open_card_view(window)

    typography.set_reading_scale(scale)

    assert tuple(action.isEnabled() for action in zoom_actions(window)) == enabled


def test_the_zoom_actions_change_the_reading_size(qtbot):
    window = make_window(qtbot)
    open_card_view(window)

    window.zoom_in_action.trigger()
    assert get_reading_text_scale() == 110
    window.zoom_out_action.trigger()
    window.zoom_out_action.trigger()
    assert get_reading_text_scale() == 90
    window.reset_zoom_action.trigger()
    assert get_reading_text_scale() == 100


# -- the keys, split by focus ------------------------------------------------


@pytest.mark.parametrize("key", [Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_Minus, Qt.Key.Key_0])
def test_the_zoom_keys_zoom_the_art_while_it_has_focus(qtbot, key):
    window = make_window(qtbot)
    card_view = open_card_view(window)
    view = card_view.image_view
    # The fixture's art is 1x1, which cannot zoom past fit
    art = QPixmap(600, 900)
    art.fill(QColor("steelblue"))
    view.set_pixmap(art)
    view.zoom_to(2 * view.fit_scale())
    focus(qtbot, view)
    scale = view.current_scale()
    typography.set_reading_scale(150)

    ctrl(qtbot, view, key)

    assert view.current_scale() != scale
    assert get_reading_text_scale() == 150


@pytest.mark.parametrize(
    ("key", "expected"),
    [(Qt.Key.Key_Plus, 175), (Qt.Key.Key_Equal, 175), (Qt.Key.Key_Minus, 125), (Qt.Key.Key_0, 100)],
)
def test_the_zoom_keys_zoom_the_text_elsewhere_in_a_card_view(qtbot, key, expected):
    window = make_window(qtbot)
    card_view = open_card_view(window)
    card_view.info_tabs.setCurrentWidget(card_view.esoterica_tab)
    view = card_view.image_view
    scale = view.current_scale()
    typography.set_reading_scale(150)
    prose = prose_label(card_view)
    focus(qtbot, prose)

    ctrl(qtbot, prose, key)

    assert get_reading_text_scale() == expected
    assert view.current_scale() == scale


def test_the_zoom_keys_reach_the_text_from_the_notes_editor(qtbot):
    window = make_window(qtbot)
    card_view = open_card_view(window)
    card_view.notes_tab.stack.setCurrentWidget(card_view.notes_tab.editor_page)
    card_view.show_notes_tab()
    editor = card_view.notes_tab.note_editor
    focus(qtbot, editor)
    before = editor.font().pointSizeF()

    ctrl(qtbot, editor, Qt.Key.Key_Plus)

    assert get_reading_text_scale() == 110
    assert editor.font().pointSizeF() > before
    assert editor.toPlainText() == ""


def test_a_click_in_the_details_takes_the_keys_off_the_art(qtbot):
    window = make_window(qtbot)
    card_view = open_card_view(window)
    focus(qtbot, card_view.image_view)
    overview = card_view.overview_tab
    # Empty space below everything in the Overview
    point = QPoint(overview.width() // 2, overview.height() - 2)

    qtbot.mouseClick(overview, Qt.MouseButton.LeftButton, pos=point)

    assert QApplication.focusWidget() is not card_view.image_view
    ctrl(qtbot, QApplication.focusWidget(), Qt.Key.Key_Plus)
    assert get_reading_text_scale() == 110


def test_the_zoom_keys_zoom_the_canvas_and_not_the_reading_text(qtbot):
    window = make_window(qtbot)
    open_card_view(window)
    window.new_canvas_tab()
    canvas = window.tab_widget.currentWidget()
    assert isinstance(canvas, CanvasTab)
    assert all(action.isEnabled() for action in zoom_actions(window))
    focus(qtbot, canvas.view)
    scale = canvas.view.transform().m11()

    ctrl(qtbot, canvas.view, Qt.Key.Key_Plus)

    assert canvas.view.transform().m11() > scale
    assert get_reading_text_scale() == 100
    # The canvas's timers must not outlive it
    qtbot.wait(1100)


def big_art(view):
    """The fixture's art is 1x1, which cannot zoom past fit"""
    art = QPixmap(600, 900)
    art.fill(QColor("steelblue"))
    view.set_pixmap(art)


def test_the_view_menu_zooms_the_art_while_it_has_focus_as_the_keys_do(qtbot):
    window = make_window(qtbot)
    card_view = open_card_view(window)
    view = card_view.image_view
    big_art(view)
    focus(qtbot, view)
    fit = view.current_scale()

    assert window.zoom_in_action.isEnabled()
    assert not window.reset_zoom_action.isEnabled()  # already at fit
    window.zoom_in_action.trigger()

    assert view.current_scale() > fit
    assert get_reading_text_scale() == 100
    assert window.reset_zoom_action.isEnabled()
    window.reset_zoom_action.trigger()
    assert view.is_at_fit()


def test_the_view_menu_zooms_the_text_once_focus_leaves_the_art(qtbot):
    window = make_window(qtbot)
    card_view = open_card_view(window)
    view = card_view.image_view
    big_art(view)
    focus(qtbot, view)
    assert not window.zoom_out_action.isEnabled()  # the art is at fit

    card_view.info_tabs.setCurrentWidget(card_view.esoterica_tab)
    focus(qtbot, prose_label(card_view))
    assert window.zoom_out_action.isEnabled()
    window.zoom_out_action.trigger()

    assert get_reading_text_scale() == 90
    assert view.is_at_fit()
