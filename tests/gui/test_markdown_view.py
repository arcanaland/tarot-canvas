import pytest
from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QColor, QFont, QImage, QTextDocument

from tarot_canvas.ui import typography
from tarot_canvas.ui.widgets import markdown_view
from tarot_canvas.ui.widgets.markdown_view import MarkdownView

NOTE = "# Title\n\nOne.\n\nTwo.\n\n## Sub\n\nThree."


@pytest.fixture
def view(qtbot):
    view = MarkdownView()
    qtbot.addWidget(view)
    view.resize(300, 10)
    view.show()
    qtbot.waitExposed(view)
    return view


def block_with(view, text):
    block = view.document().firstBlock()
    while block.isValid():
        if block.text() == text:
            return block
        block = block.next()
    raise AssertionError(f"no block {text!r}")


def font_of(view, text):
    return block_with(view, text).begin().fragment().charFormat().font()


def test_the_opening_heading_is_dropped_and_the_rest_is_whole(view):
    view.set_markdown(NOTE)
    text = view.toPlainText()
    assert "Title" not in text
    for line in ("One.", "Two.", "Sub", "Three."):
        assert line in text
    assert block_with(view, "One.").blockFormat().headingLevel() == 0


def test_a_lower_heading_is_body_sized_and_demibold(view):
    view.set_markdown(NOTE)
    sub = font_of(view, "Sub")
    assert sub.pointSizeF() == pytest.approx(view.font().pointSizeF())
    assert sub.weight() == QFont.Weight.DemiBold
    assert font_of(view, "Three.").pointSizeF() == pytest.approx(view.font().pointSizeF())


def test_a_later_top_heading_is_heading_4(view):
    view.set_markdown("Intro.\n\n# Later\n\nBody.")
    later = font_of(view, "Later")
    assert later.pointSizeF() == pytest.approx(
        typography.font(typography.Role.HEADING_4).pointSizeF()
    )
    assert "Intro." in view.toPlainText()


def test_a_note_that_is_only_a_heading_shows_nothing(view):
    view.set_markdown("# Only")
    assert view.toPlainText() == ""


def test_relative_images_resolve_against_the_base(view, tmp_path):
    picture = QImage(10, 10, QImage.Format.Format_RGB32)
    picture.fill(QColor("red"))
    assert picture.save(str(tmp_path / "pic.png"))

    view.set_markdown("Before.\n\n![pic](pic.png)", base=tmp_path)

    document = view.document()
    assert document.baseUrl() == QUrl.fromLocalFile(str(tmp_path) + "/")
    resource = document.resource(QTextDocument.ResourceType.ImageResource.value, QUrl("pic.png"))
    assert resource is not None and not resource.isNull()


def test_the_height_follows_the_text(view):
    view.set_markdown("One line.")
    short = view.height()
    view.set_markdown("\n\n".join(f"Paragraph {n}." for n in range(20)))
    assert view.height() > short
    assert view.verticalScrollBar().maximum() == 0


def test_only_web_links_open(view, monkeypatch):
    opened = []
    monkeypatch.setattr(markdown_view.QDesktopServices, "openUrl", opened.append)
    view.anchorClicked.emit(QUrl("https://example.org/"))
    view.anchorClicked.emit(QUrl("other-note.md"))
    view.anchorClicked.emit(QUrl("file:///etc/passwd"))
    assert opened == [QUrl("https://example.org/")]
