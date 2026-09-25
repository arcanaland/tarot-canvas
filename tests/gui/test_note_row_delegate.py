from types import SimpleNamespace

from PyQt6.QtCore import QRect, Qt
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

from tarot_canvas.ui.library import units
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


def make_option(qapp, delegate, width=ROW_WIDTH):
    option = QStyleOptionViewItem()
    option.font = qapp.font()
    option.palette = qapp.palette()
    option.state = QStyle.StateFlag.State_Enabled
    option.rect = QRect(0, 0, width, delegate.sizeHint(option, None).height())
    return option


def test_the_library_row_has_a_well_and_no_menu_button(qapp):
    delegate = NoteRowDelegate()
    layout = delegate._layout(make_option(qapp, delegate))

    assert layout.well.width() > 0
    assert layout.title.left() > layout.well.right()
    assert layout.menu.isNull()
    assert layout.title.right() == ROW_WIDTH - 1 - units.LARGE_SPACING


def test_without_a_thumbnail_the_title_starts_at_the_margin(qapp):
    delegate = NoteRowDelegate(thumbnail=False)
    layout = delegate._layout(make_option(qapp, delegate))

    assert layout.title.left() == units.LARGE_SPACING
    assert layout.well.width() == 0


def test_the_menu_button_sits_centred_at_the_right_and_the_text_stops_short(qapp):
    delegate = NoteRowDelegate(thumbnail=False, menu_button=True)
    option = make_option(qapp, delegate)
    layout = delegate._layout(option)

    assert layout.menu.right() == ROW_WIDTH - 1 - units.LARGE_SPACING
    assert abs(layout.menu.center().y() - option.rect.center().y()) <= 1
    for rect in (layout.title, layout.subtitle, layout.preview):
        assert rect.right() < layout.menu.left()


def mouse(kind, pos, button=Qt.MouseButton.LeftButton):
    from PyQt6.QtCore import QPointF
    from PyQt6.QtGui import QMouseEvent

    return QMouseEvent(
        kind, QPointF(pos), QPointF(pos), button, button, Qt.KeyboardModifier.NoModifier
    )


def test_a_release_elsewhere_on_the_row_is_left_to_the_view(qapp, tmp_path):
    from PyQt6.QtCore import QEvent

    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "Written")]}, None)
    delegate = NoteRowDelegate(thumbnail=False, menu_button=True)
    option = make_option(qapp, delegate)
    asked = []
    delegate.menuRequested.connect(lambda *args: asked.append(args))

    consumed = delegate.editorEvent(
        mouse(QEvent.Type.MouseButtonRelease, delegate._layout(option).title.center()),
        model,
        option,
        model.index(0, 0),
    )

    assert not consumed
    assert asked == []


def test_the_rename_editor_covers_the_title(qtbot, qapp, tmp_path):
    from PyQt6.QtWidgets import QWidget

    model = NotesListModel({FOOL: [note(tmp_path, FOOL, "Written")]}, None, editable=True)
    delegate = NoteRowDelegate(thumbnail=False, menu_button=True)
    parent = QWidget()
    qtbot.addWidget(parent)
    option = make_option(qapp, delegate)
    index = model.index(0, 0)

    editor = delegate.createEditor(parent, option, index)
    delegate.setEditorData(editor, index)
    delegate.updateEditorGeometry(editor, option, index)

    title = delegate._layout(option).title
    assert editor.text() == "Written"
    assert editor.geometry().left() == title.left()
    assert editor.geometry().width() == title.width()
    assert editor.geometry().contains(title.center())
