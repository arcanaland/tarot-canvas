"""A created deck's view fills it a card at a time; other decks' views are unchanged"""

import os

import pytest
from PyQt6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QKeyEvent
from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox

from tarot_canvas.models import deck_writer as writer
from tarot_canvas.ui.deck_view.card_model import KIND_BACK, CardRole, KindRole
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs import deck_view_tab as module
from tarot_canvas.ui.tabs.deck_view_tab import DeckViewTab
from tarot_canvas.ui.windows import new_deck_dialog
from tests.conftest import MINIMAL_DECK_PATH

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"


@pytest.fixture
def decks_root(tmp_path, curation_file):
    return tmp_path / "decks"


@pytest.fixture
def created(decks_root):
    return writer.create("Created", majors_only=True, decks_root=decks_root)


def picture(tmp_path, name, colour="red"):
    image = QImage(60, 100, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    path = tmp_path / name
    assert image.save(os.fspath(path))
    return path


def settled(qtbot, tab):
    qtbot.waitUntil(lambda: not tab.editor.is_busy())
    return tab


def shown(qtbot, path):
    tab = DeckViewTab(os.fspath(path))
    qtbot.addWidget(tab)
    tab.resize(1000, 700)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


@pytest.fixture
def tab(qtbot, created):
    return settled(qtbot, shown(qtbot, created))


def slot(tab, card_id):
    """The current view's index for card_id, or the back"""
    view = tab.current_view()
    model = view.model()
    for row in range(tab.model.rowCount()):
        index = tab.model.index(row, 0)
        found = index.data(CardRole)
        if (found and found.canonical_id == card_id) or (
            card_id == writer.BACK and index.data(KindRole) == KIND_BACK
        ):
            return model.mapFromSource(index)
    raise KeyError(card_id)


def image_of(tab, card_id):
    return tab.deck.find_card(card_id).default_image()


def unsorted_files(path):
    folder = path / writer.UNSORTED
    return sorted(entry.name for entry in folder.iterdir()) if folder.is_dir() else []


def drop(tab, index, files):
    """A drag entering over index, then the drop; returns (enter, drop)"""
    view = tab.current_view()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(os.fspath(path)) for path in files])
    position = QPointF(view.visualRect(index).center())
    args = (Qt.DropAction.CopyAction, mime, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
    enter = QDragEnterEvent(position.toPoint(), *args)
    QApplication.sendEvent(view.viewport(), enter)
    dropped = QDropEvent(position, *args)
    if enter.isAccepted():
        QApplication.sendEvent(view.viewport(), dropped)
    return enter, dropped


@pytest.fixture
def chosen(monkeypatch):
    """The file the chooser returns next"""
    picked = {}
    monkeypatch.setattr(
        module.QFileDialog, "getOpenFileName", lambda *args: (os.fspath(picked["path"]), "")
    )
    return picked


@pytest.fixture
def warnings(monkeypatch):
    shown_ = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: shown_.append(args[2]))
    return shown_


def test_a_click_on_an_empty_slot_places_the_chosen_file_and_the_view_reloads(
    qtbot, tab, tmp_path, chosen
):
    chosen["path"] = picture(tmp_path, "fool.png")
    view = tab.current_view()

    qtbot.mouseClick(
        view.viewport(), Qt.MouseButton.LeftButton, pos=view.visualRect(slot(tab, FOOL)).center()
    )
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert module.DECK_VIEW["created_count"].format(placed=1, expected=22) in (
        tab.header.subtitle_label.text()
    )
    assert (
        tab.current_view().model().mapToSource(view.currentIndex()).data(CardRole).canonical_id
        == FOOL
    )


def test_activating_an_empty_slot_chooses_rather_than_opening_a_card(qtbot, tab, tmp_path, chosen):
    chosen["path"] = picture(tmp_path, "fool.png")
    opened = []
    tab.card_action_requested.connect(lambda *args: opened.append(args))

    tab.on_card_activated(slot(tab, FOOL))
    settled(qtbot, tab)

    assert opened == []
    assert image_of(tab, FOOL)


def test_a_ctrl_click_on_an_empty_slot_only_selects(qtbot, tab, chosen):
    view = tab.current_view()
    rect = view.visualRect(slot(tab, FOOL))

    qtbot.mouseClick(
        view.viewport(),
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
        rect.center(),
    )

    assert not tab.editor.is_busy()
    assert view.selectionModel().isSelected(slot(tab, FOOL))


def test_remove_leaves_the_card_imageless_and_its_file_in_unsorted(qtbot, tab, tmp_path, created):
    tab.editor.place(FOOL, picture(tmp_path, "fool.png"))
    settled(qtbot, tab)

    menu = tab.slot_menu(slot(tab, FOOL))
    remove = next(a for a in menu.actions() if a.text() == module.DECK_VIEW["remove_card"])
    remove.trigger()
    settled(qtbot, tab)

    assert not image_of(tab, FOOL)
    assert unsorted_files(created) == ["fool.png"]
    assert tab.unsorted.names() == ["fool.png"]


def test_an_empty_slot_offers_only_choose_image(tab):
    menu = tab.slot_menu(slot(tab, FOOL))

    assert [a.text() for a in menu.actions()] == [module.DECK_VIEW["choose_image"]]


def test_a_filled_back_offers_replace_and_remove_and_nothing_for_a_card(qtbot, tab, tmp_path):
    tab.editor.place(writer.BACK, picture(tmp_path, "back.png"))
    settled(qtbot, tab)

    menu = tab.slot_menu(slot(tab, writer.BACK))

    assert [a.text() for a in menu.actions()] == [
        module.DECK_VIEW["replace_image"],
        module.DECK_VIEW["remove_card"],
    ]


def test_edit_delete_removes_every_selected_filled_card(qtbot, tab, tmp_path, created):
    tab.editor.place(FOOL, picture(tmp_path, "fool.png"))
    tab.editor.place(MAGICIAN, picture(tmp_path, "magician.png"))
    settled(qtbot, tab)
    view = tab.current_view()
    for card_id in (FOOL, MAGICIAN, "major_arcana.02"):
        view.selectionModel().select(slot(tab, card_id), view.selectionModel().SelectionFlag.Select)

    assert tab.can_delete()
    tab.delete()
    settled(qtbot, tab)

    assert not image_of(tab, FOOL) and not image_of(tab, MAGICIAN)
    assert unsorted_files(created) == ["fool.png", "magician.png"]


def test_one_file_dropped_on_a_filled_slot_replaces_it(qtbot, tab, tmp_path, created):
    tab.editor.place(FOOL, picture(tmp_path, "fool.png", "red"))
    settled(qtbot, tab)

    _, dropped = drop(tab, slot(tab, FOOL), [picture(tmp_path, "new.png", "blue")])
    settled(qtbot, tab)

    assert dropped.isAccepted()
    image = QImage(image_of(tab, FOOL))
    assert image.pixelColor(5, 5) == QColor("blue")
    assert unsorted_files(created) == ["fool.png"]


def test_in_the_tableau_a_drag_over_the_back_highlights_it_and_the_drop_fills_it(
    qtbot, tab, tmp_path
):
    tab.set_view_mode(module.DECK_VIEW_MODE_TABLEAU)
    back = slot(tab, writer.BACK)

    enter, dropped = drop(tab, back, [picture(tmp_path, "back.png")])

    assert enter.isAccepted() and dropped.isAccepted()
    assert tab.delegate.drop_target is None
    settled(qtbot, tab)
    assert slot(tab, writer.BACK).data(module.BackPathRole)


def test_a_drag_over_a_slot_highlights_it(tab, tmp_path):
    view = tab.current_view()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(os.fspath(picture(tmp_path, "a.png")))])
    enter = QDragEnterEvent(
        view.visualRect(slot(tab, FOOL)).center(),
        Qt.DropAction.CopyAction,
        mime,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )

    QApplication.sendEvent(view.viewport(), enter)

    assert tab.delegate.drop_target == slot(tab, FOOL)


def test_two_files_dropped_on_a_slot_both_go_to_unsorted(qtbot, tab, tmp_path, created):
    files = [picture(tmp_path, "a.png"), picture(tmp_path, "b.png")]

    drop(tab, slot(tab, FOOL), files)
    settled(qtbot, tab)

    assert not image_of(tab, FOOL)
    assert unsorted_files(created) == ["a.png", "b.png"]


def test_a_drop_on_a_heading_is_refused(qtbot, tab, tmp_path, monkeypatch):
    tab.set_view_mode(module.DECK_VIEW_MODE_SECTIONS)
    view = tab.current_view()
    heading = view.model().index(0, 0)

    enter, _ = drop(tab, heading, [picture(tmp_path, "a.png")])

    assert not enter.isAccepted()
    assert not tab.editor.is_busy()


def test_a_failed_write_says_why_and_the_queue_continues(qtbot, tab, tmp_path, warnings):
    text = tmp_path / "notes.txt"
    text.write_text("not an image")

    tab.editor.place(FOOL, text)
    tab.editor.place(MAGICIAN, picture(tmp_path, "magician.png"))
    settled(qtbot, tab)

    assert warnings == [
        module.DECK_VIEW["write_failed.unreadable_image"].format(detail=os.fspath(text))
    ]
    assert image_of(tab, MAGICIAN)


def test_the_header_counts_the_cards_and_not_the_back(qtbot, tab, tmp_path):
    expected = module.DECK_VIEW["created_count"]
    assert expected.format(placed=0, expected=22) in tab.header.subtitle_text()

    tab.editor.place(writer.BACK, picture(tmp_path, "back.png"))
    settled(qtbot, tab)

    assert expected.format(placed=0, expected=22) in tab.header.subtitle_text()


# -- Unsorted ---------------------------------------------------------------


def test_unsorted_lists_the_old_image_after_a_replace(qtbot, tab, tmp_path, chosen):
    tab.editor.place(FOOL, picture(tmp_path, "fool.png"))
    settled(qtbot, tab)
    chosen["path"] = picture(tmp_path, "other.png")

    tab.choose_image(slot(tab, FOOL))
    settled(qtbot, tab)

    assert tab.unsorted.names() == ["fool.png"]
    assert tab.unsorted.view.isVisible()
    assert not tab.unsorted.empty_label.isVisible()


def test_an_unsorted_item_drags_as_its_file_url(qtbot, tab, tmp_path, created):
    tab.editor.place_unsorted(picture(tmp_path, "loose.png"))
    settled(qtbot, tab)
    model = tab.unsorted.model

    mime = model.mimeData([model.index(0, 0)])

    assert mime.urls() == [QUrl.fromLocalFile(os.fspath(created / writer.UNSORTED / "loose.png"))]


def test_an_unsorted_file_dropped_on_a_slot_moves_into_it(qtbot, tab, tmp_path, created):
    tab.editor.place_unsorted(picture(tmp_path, "loose.png"))
    settled(qtbot, tab)

    drop(tab, slot(tab, FOOL), [created / writer.UNSORTED / "loose.png"])
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert unsorted_files(created) == []
    assert tab.unsorted.names() == []


def test_delete_in_unsorted_asks_then_removes_the_file(qtbot, tab, tmp_path, created, monkeypatch):
    tab.editor.place_unsorted(picture(tmp_path, "loose.png"))
    settled(qtbot, tab)
    asked = []
    monkeypatch.setattr(
        module.QMessageBox,
        "question",
        lambda *args: asked.append(args) or QMessageBox.StandardButton.Yes,
    )
    view = tab.unsorted.view
    view.setCurrentIndex(tab.unsorted.model.index(0, 0))
    monkeypatch.setattr(view, "hasFocus", lambda: True)

    assert tab.can_delete()
    tab.delete()
    settled(qtbot, tab)

    assert len(asked) == 1
    assert unsorted_files(created) == []


def test_answering_no_keeps_the_unsorted_file(qtbot, tab, tmp_path, created, monkeypatch):
    tab.editor.place_unsorted(picture(tmp_path, "loose.png"))
    settled(qtbot, tab)
    monkeypatch.setattr(module.QMessageBox, "question", lambda *args: QMessageBox.StandardButton.No)

    tab.unsorted.discard_requested.emit("loose.png")
    settled(qtbot, tab)

    assert unsorted_files(created) == ["loose.png"]


def test_files_dropped_on_the_strip_are_copied_in(qtbot, tab, tmp_path, created):
    tab.unsorted.files_dropped.emit([os.fspath(picture(tmp_path, "a.png"))])
    settled(qtbot, tab)

    assert tab.unsorted.names() == ["a.png"]


# -- placing from Unsorted ----------------------------------------------------


@pytest.fixture
def no_file_dialog(monkeypatch):
    """Fails the test if the file chooser opens; lists the calls otherwise"""
    calls = []
    monkeypatch.setattr(
        module.QFileDialog, "getOpenFileName", lambda *args: calls.append(args) or ("", "")
    )
    return calls


def removed_fool(qtbot, tab, tmp_path):
    tab.editor.place(FOOL, picture(tmp_path, "fool.png"))
    settled(qtbot, tab)
    tab.editor.unplace(FOOL)
    return settled(qtbot, tab)


def item_menu_action(tab, text):
    menu = tab.unsorted.item_menu(tab.unsorted.model.index(0, 0))
    return menu, next(action for action in menu.actions() if action.text() == text)


def test_an_unsorted_image_shows_the_card_its_name_names(qtbot, tab, tmp_path):
    removed_fool(qtbot, tab, tmp_path)
    tab.editor.place_unsorted(picture(tmp_path, "IMG_2041.png"))
    settled(qtbot, tab)

    assert tab.unsorted.names() == ["IMG_2041.png", "fool.png"]
    assert tab.unsorted.card_ids() == [None, FOOL]
    assert tab.unsorted.model.item(0).text() == "IMG_2041.png"
    assert tab.unsorted.model.item(1).text() == "fool.png\nThe Fool"


def test_an_image_taken_out_comes_back_under_its_own_name_not_its_slots(
    qtbot, tab, tmp_path, created
):
    tab.editor.place("major_arcana.02", picture(tmp_path, "03.png"))
    settled(qtbot, tab)
    tab.editor.unplace("major_arcana.02")
    settled(qtbot, tab)

    assert unsorted_files(created) == ["03.png"]
    assert tab.unsorted.card_ids() == ["major_arcana.03"]


def test_place_as_the_classified_card_is_the_default_and_puts_it_back(
    qtbot, tab, tmp_path, created
):
    removed_fool(qtbot, tab, tmp_path)
    text = module.DECK_VIEW["place_as"].format(card="The Fool")

    menu, place = item_menu_action(tab, text)
    assert menu.defaultAction() is place
    place.trigger()
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert unsorted_files(created) == []


def test_an_unclassified_image_offers_only_place_as_other_and_delete(qtbot, tab, tmp_path):
    tab.editor.place_unsorted(picture(tmp_path, "IMG_2041.png"))
    settled(qtbot, tab)

    menu = tab.unsorted.item_menu(tab.unsorted.model.index(0, 0))

    assert [action.text() for action in menu.actions() if not action.isSeparator()] == [
        module.DECK_VIEW["place_as_other"],
        module.DECK_VIEW["delete_unsorted"],
    ]
    assert menu.defaultAction() is None


def test_place_as_other_finds_a_card_by_typing_and_return_places_it(qtbot, tab, tmp_path, created):
    removed_fool(qtbot, tab, tmp_path)

    _menu, other = item_menu_action(tab, module.DECK_VIEW["place_as_other"])
    other.trigger()
    picker = tab.picker
    assert picker.isVisible()
    qtbot.keyClicks(picker.find, "magician")
    assert picker.visible_slots() == [MAGICIAN]
    qtbot.keyClick(picker.find, Qt.Key.Key_Return)
    settled(qtbot, tab)

    assert image_of(tab, MAGICIAN)
    assert not image_of(tab, FOOL)
    assert unsorted_files(created) == []


def test_the_card_picker_lists_the_back_after_the_cards(qtbot, tab, tmp_path):
    removed_fool(qtbot, tab, tmp_path)
    tab.choose_card(tab.unsorted.model.item(0).data(module.PathRole), tab.mapToGlobal(tab.pos()))

    slots = tab.picker.visible_slots()
    assert len(slots) == 23
    assert slots[0] == FOOL
    assert slots[-1] == writer.BACK


def test_a_click_on_an_empty_slot_offers_unsorted_first(
    qtbot, tab, tmp_path, created, no_file_dialog
):
    removed_fool(qtbot, tab, tmp_path)
    view = tab.current_view()

    qtbot.mouseClick(
        view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=view.visualRect(slot(tab, MAGICIAN)).center(),
    )
    picker = tab.picker
    assert picker.isVisible()
    assert no_file_dialog == []
    qtbot.mouseClick(
        picker.view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=picker.view.visualRect(picker.view.model().index(0, 0)).center(),
    )
    settled(qtbot, tab)

    assert image_of(tab, MAGICIAN)
    assert unsorted_files(created) == []


def test_from_file_in_the_slot_picker_opens_the_chooser(qtbot, tab, tmp_path, chosen):
    removed_fool(qtbot, tab, tmp_path)
    chosen["path"] = picture(tmp_path, "magician.png")

    tab.choose_image(slot(tab, MAGICIAN))
    qtbot.mouseClick(tab.picker.from_file, Qt.MouseButton.LeftButton)
    settled(qtbot, tab)

    assert image_of(tab, MAGICIAN)
    assert tab.unsorted.names() == ["fool.png"]


def test_a_drag_near_the_bottom_edge_scrolls_the_page_until_it_leaves(qtbot, tab):
    tab.resize(800, 300)
    qtbot.waitUntil(lambda: tab.scroll.verticalScrollBar().maximum() > 0)
    bar = tab.scroll.verticalScrollBar()
    scroller = tab.drag_scroll

    scroller.follow(tab.scroll.viewport().height() - 1)
    assert scroller.timer.isActive()
    qtbot.waitUntil(lambda: bar.value() > 0)

    scroller.follow(tab.scroll.viewport().height() // 2)
    assert not scroller.timer.isActive()
    scroller.follow(0)
    assert scroller.step < 0
    scroller.follow(None)
    assert not scroller.timer.isActive()


# -- decks not created here ---------------------------------------------------


def test_a_deck_not_created_here_has_no_editing(qtbot):
    tab = shown(qtbot, MINIMAL_DECK_PATH)

    assert not tab.editable
    assert tab.editor is None and tab.unsorted is None
    assert not tab.delegate.editable
    assert tab.model.back_row() is None
    for view in (tab.grid, tab.tableau):
        assert not view.findChildren(module._SlotDrops)
    assert not tab.can_delete()
    assert tab.progress_bar.isHidden()
    assert module.DECK_VIEW["card_count"].format(count=len(tab.deck.cards)) in (
        tab.header.subtitle_text()
    )


# -- File > New Deck… ---------------------------------------------------------


def test_new_deck_creates_a_deck_and_opens_its_view(qtbot, decks_root, monkeypatch):
    monkeypatch.setattr(writer, "get_decks_directory", lambda: [decks_root])
    window = MainWindow()
    qtbot.addWidget(window)
    seen = {}

    def run(dialog):
        seen["blank"] = (dialog.name_field.setText("   "), dialog.create_button.isEnabled())[1]
        dialog.name_field.setText("My Deck")
        seen["named"] = dialog.create_button.isEnabled()
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(new_deck_dialog.NewDeckDialog, "exec", run)

    tab = window.new_deck()

    assert seen == {"blank": False, "named": True}
    assert isinstance(tab, DeckViewTab)
    assert window.tab_widget.currentWidget() is tab
    assert tab.editable
    assert tab.deck.metadata.name == "My Deck"
    assert sum(1 for row in tab.model.card_rows()) == 22
    assert tab.model.back_row() is not None
    assert not tab.minors_offer.isHidden()
    settled(qtbot, tab)


# -- the minors ------------------------------------------------------------------


def test_a_majors_only_deck_offers_the_minors_and_taking_them_lays_out_78(qtbot, tab, created):
    assert tab.minors_offer.isVisible()

    tab.minors_offer.button.click()
    settled(qtbot, tab)

    assert sum(1 for row in tab.model.card_rows()) == 78
    assert not tab.minors_offer.isVisible()
    assert "excluded_cards" not in (created / "deck.toml").read_text(encoding="utf-8")


def test_a_whole_created_deck_offers_nothing(qtbot, decks_root):
    whole = writer.create("Whole", majors_only=False, decks_root=decks_root)
    tab = settled(qtbot, shown(qtbot, whole))

    assert not tab.minors_offer.isVisible()


def test_a_deck_not_created_here_has_no_offer(qtbot):
    tab = shown(qtbot, MINIMAL_DECK_PATH)

    assert tab.minors_offer is None


def unsorted_index(tab, name):
    return tab.unsorted.model.index(tab.unsorted.names().index(name), 0)


def test_return_on_an_unsorted_image_places_it_as_its_card_and_walks_on(
    qtbot, tab, tmp_path, created
):
    for name in ("fool.png", "01.png", "IMG_2041.png"):
        tab.editor.place_unsorted(picture(tmp_path, name))
    settled(qtbot, tab)
    assert tab.unsorted.names() == ["01.png", "IMG_2041.png", "fool.png"]
    view = tab.unsorted.view
    view.setFocus()
    view.setCurrentIndex(unsorted_index(tab, "01.png"))

    qtbot.keyClick(view, Qt.Key.Key_Return)
    settled(qtbot, tab)

    assert image_of(tab, MAGICIAN)
    assert unsorted_files(created) == ["IMG_2041.png", "fool.png"]
    assert tab.unsorted.current_name() == "IMG_2041.png"


def test_the_last_unsorted_image_placed_leaves_the_one_before_it_current(
    qtbot, tab, tmp_path, created
):
    for name in ("01.png", "fool.png"):
        tab.editor.place_unsorted(picture(tmp_path, name))
    settled(qtbot, tab)
    view = tab.unsorted.view
    view.setFocus()
    view.setCurrentIndex(unsorted_index(tab, "fool.png"))

    qtbot.keyClick(view, Qt.Key.Key_Return)
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert tab.unsorted.current_name() == "01.png"


def test_double_clicking_an_unsorted_image_places_it_as_its_card(qtbot, tab, tmp_path, created):
    removed_fool(qtbot, tab, tmp_path)
    view = tab.unsorted.view
    centre = view.visualRect(unsorted_index(tab, "fool.png")).center()

    # A real double-click starts with a press; the view activates only what it was pressed on
    qtbot.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseDClick(view.viewport(), Qt.MouseButton.LeftButton, pos=centre)
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert unsorted_files(created) == []


def test_return_on_an_unclassified_image_asks_which_card_it_is(qtbot, tab, tmp_path, created):
    tab.editor.place_unsorted(picture(tmp_path, "IMG_2041.png"))
    settled(qtbot, tab)
    view = tab.unsorted.view
    view.setFocus()
    view.setCurrentIndex(unsorted_index(tab, "IMG_2041.png"))

    qtbot.keyClick(view, Qt.Key.Key_Return)

    assert isinstance(tab.picker, module.CardPicker)
    assert unsorted_files(created) == ["IMG_2041.png"]
    tab.picker.close()


def test_return_pressed_faster_than_the_writer_places_each_image_once(
    qtbot, tab, tmp_path, created, monkeypatch
):
    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: warnings.append(args))
    for name in ("00.png", "01.png", "02.png"):
        tab.editor.place_unsorted(picture(tmp_path, name))
    settled(qtbot, tab)
    view = tab.unsorted.view
    view.setFocus()
    view.setCurrentIndex(unsorted_index(tab, "00.png"))

    # More presses than images, all before the first placement is written
    for _ in range(6):
        qtbot.keyClick(view, Qt.Key.Key_Return)
    settled(qtbot, tab)

    assert warnings == []
    assert all(image_of(tab, card_id) for card_id in (FOOL, MAGICIAN, "major_arcana.02"))
    assert unsorted_files(created) == []
    assert tab.unsorted.names() == []


def test_an_image_that_fails_to_place_comes_back_to_unsorted(
    qtbot, tab, tmp_path, created, monkeypatch
):
    warnings = []
    monkeypatch.setattr(module.QMessageBox, "warning", lambda *args: warnings.append(args))
    tab.editor.place_unsorted(picture(tmp_path, "fool.png"))
    settled(qtbot, tab)
    # Readable to Qt's header check, but no image
    (created / writer.UNSORTED / "fool.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 64)
    view = tab.unsorted.view
    view.setFocus()
    view.setCurrentIndex(unsorted_index(tab, "fool.png"))

    qtbot.keyClick(view, Qt.Key.Key_Return)
    settled(qtbot, tab)

    assert len(warnings) == 1
    assert tab.unsorted.names() == ["fool.png"]


def test_a_held_return_places_only_the_first_image(qtbot, tab, tmp_path, created):
    for name in ("00.png", "01.png"):
        tab.editor.place_unsorted(picture(tmp_path, name))
    settled(qtbot, tab)
    view = tab.unsorted.view
    view.setFocus()
    view.setCurrentIndex(unsorted_index(tab, "00.png"))

    qtbot.keyClick(view, Qt.Key.Key_Return)
    for _ in range(3):
        repeat = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "\r", True
        )
        QApplication.sendEvent(view, repeat)
    settled(qtbot, tab)

    assert image_of(tab, FOOL)
    assert not image_of(tab, MAGICIAN)
    assert unsorted_files(created) == ["01.png"]
