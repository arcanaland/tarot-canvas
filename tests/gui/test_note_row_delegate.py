from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter, QPalette
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

from tarot_canvas.models import notes as notes_model
from tarot_canvas.ui.library import note_row_delegate, units
from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_model import NotesListModel, PreviewRole
from tests.gui.test_library_delegate import write_card
from tests.unit.test_notes_model import note

FOOL = "major_arcana.00"
MAGICIAN = "major_arcana.01"
ROW_WIDTH = 480


def deck_with_art(images):
    def get_card_by_id(card_id):
        if card_id not in images:
            return None
        return {"id": card_id, "name": card_id, "image": images[card_id]}

    return SimpleNamespace(get_card_by_id=get_card_by_id)


def option_for(delegate, qapp, palette=None, state=QStyle.StateFlag.State_Enabled):
    option = QStyleOptionViewItem()
    option.font = qapp.font()
    option.palette = palette or qapp.palette()
    option.state = state
    height = delegate.sizeHint(option, None).height()
    option.rect = QRect(0, 0, ROW_WIDTH, height)
    return option


def render(delegate, qapp, index, palette=None, state=QStyle.StateFlag.State_Enabled):
    option = option_for(delegate, qapp, palette, state)
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()
    return image


@pytest.fixture
def model(tmp_path):
    art = write_card(tmp_path, 600, 1050, "red")
    index = {
        FOOL: [note(tmp_path, FOOL, "Written", body="a leap into thin air\n")],
        MAGICIAN: [note(tmp_path, MAGICIAN, "Stub", modified=1_600_000_000.0)],
    }
    return NotesListModel(index, deck_with_art({FOOL: art}))


def light_and_dark(qapp):
    light = QPalette(qapp.palette())
    light.setColor(QPalette.ColorRole.Text, QColor("#000000"))
    light.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    dark = QPalette(qapp.palette())
    dark.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    dark.setColor(QPalette.ColorRole.Base, QColor("#1b1b1b"))
    return light, dark


# -- geometry ------------------------------------------------------------


def test_the_thumbnail_is_as_tall_as_the_text_and_the_text_starts_beside_it(qapp):
    delegate = NoteRowDelegate()
    layout = delegate._layout(option_for(delegate, qapp))

    assert layout.well.top() == layout.title.top()
    assert layout.well.bottom() == layout.preview.bottom()
    assert layout.title.left() == layout.well.right() + 1 + units.LARGE_SPACING
    assert layout.title.bottom() < layout.subtitle.top()
    assert layout.subtitle.bottom() < layout.preview.top()
    assert layout.well.width() < layout.well.height()


def test_a_stub_row_is_as_tall_as_a_written_one(qapp, model):
    delegate = NoteRowDelegate()
    option = option_for(delegate, qapp)

    written, stub = model.index(0, 0), model.index(1, 0)
    assert stub.data(PreviewRole) == ""
    assert delegate.sizeHint(option, written) == delegate.sizeHint(option, stub)


# -- painting ------------------------------------------------------------


def test_a_row_with_art_paints_differently_from_one_without(qapp, model, monkeypatch):
    wells = []
    real = note_row_delegate.paint_placeholder_well
    monkeypatch.setattr(
        note_row_delegate,
        "paint_placeholder_well",
        lambda painter, well, palette: (wells.append(QRect(well)), real(painter, well, palette)),
    )
    delegate = NoteRowDelegate()

    with_art = render(delegate, qapp, model.index(0, 0))
    assert wells == []

    without_art = render(delegate, qapp, model.index(1, 0))
    assert wells == [delegate._layout(option_for(delegate, qapp)).well]

    assert with_art != without_art


def test_the_art_is_drawn_in_the_well(qapp, model):
    delegate = NoteRowDelegate()
    well = delegate._layout(option_for(delegate, qapp)).well

    image = render(delegate, qapp, model.index(0, 0))

    assert image.pixelColor(well.center()) == QColor("red")


@pytest.mark.parametrize("row", [0, 1])
def test_the_row_follows_the_colour_scheme(qapp, model, row):
    delegate = NoteRowDelegate()
    light, dark = light_and_dark(qapp)

    assert render(delegate, qapp, model.index(row, 0), light) != render(
        delegate, qapp, model.index(row, 0), dark
    )


def test_painting_never_reads_a_note(qapp, model, monkeypatch):
    def refuse(*_args):
        raise AssertionError("paint read a note from disk")

    monkeypatch.setattr(notes_model, "first_body_line", refuse)
    monkeypatch.setattr(notes_model, "matching_line", refuse)
    monkeypatch.setattr(notes_model, "_body_lines", refuse)
    delegate = NoteRowDelegate()

    for row in range(model.rowCount()):
        render(delegate, qapp, model.index(row, 0))
        render(delegate, qapp, model.index(row, 0), state=QStyle.StateFlag.State_Selected)
