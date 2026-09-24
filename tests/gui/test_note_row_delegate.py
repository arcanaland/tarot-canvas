from types import SimpleNamespace

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

from tarot_canvas.ui.library.note_row_delegate import NoteRowDelegate
from tarot_canvas.ui.library.notes_model import NotesListModel
from tests.gui.test_library_delegate import write_card
from tests.unit.test_notes_model import note

FOOL = "major_arcana.00"
ROW_WIDTH = 480


def test_the_art_is_drawn_in_the_well(qapp, tmp_path):
    art = write_card(tmp_path, 600, 1050, "red")
    deck = SimpleNamespace(
        get_card_by_id=lambda card_id: {"id": card_id, "name": card_id, "image": art}
    )
    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "Written", body="a leap\n")]}, deck)
    delegate = NoteRowDelegate()

    option = QStyleOptionViewItem()
    option.font = qapp.font()
    option.palette = qapp.palette()
    option.state = QStyle.StateFlag.State_Enabled
    option.rect = QRect(0, 0, ROW_WIDTH, delegate.sizeHint(option, None).height())

    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    delegate.paint(painter, option, model.index(0, 0))
    painter.end()

    assert image.pixelColor(delegate._layout(option).well.center()) == QColor("red")
