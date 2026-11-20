"""A created deck's view fills it a card at a time; other decks' views are unchanged"""

import os

import pytest
from PyQt6.QtCore import QMimeData, QPointF, Qt, QUrl
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage
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
    assert unsorted_files(created) == ["00.png"]
    assert tab.unsorted.names() == ["00.png"]


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
    assert unsorted_files(created) == ["00.png", "01.png"]


def test_one_file_dropped_on_a_filled_slot_replaces_it(qtbot, tab, tmp_path, created):
    tab.editor.place(FOOL, picture(tmp_path, "fool.png", "red"))
    settled(qtbot, tab)

    _, dropped = drop(tab, slot(tab, FOOL), [picture(tmp_path, "new.png", "blue")])
    settled(qtbot, tab)

    assert dropped.isAccepted()
    image = QImage(image_of(tab, FOOL))
    assert image.pixelColor(5, 5) == QColor("blue")
    assert unsorted_files(created) == ["00.png"]


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

    assert tab.unsorted.names() == ["00.png"]
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
        dialog.majors.setChecked(True)
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
    settled(qtbot, tab)
