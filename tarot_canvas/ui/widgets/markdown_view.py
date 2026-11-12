"""Markdown shown read-only, as tall as its text, for a pane whose one scroll area holds it"""

import math

from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtGui import (
    QDesktopServices,
    QFont,
    QPalette,
    QTextBlockFormat,
    QTextCursor,
    QTextFormat,
)
from PyQt6.QtWidgets import QFrame, QSizePolicy, QTextBrowser

from tarot_canvas.ui import typography
from tarot_canvas.ui.passage_metrics import BODY_LINE_HEIGHT
from tarot_canvas.ui.widgets.pane_text import is_link


class MarkdownView(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._markdown = ""
        self._base = None
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # The pane shows through
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.transparent)
        self.setPalette(palette)
        self.viewport().setAutoFillBackground(False)
        self.document().setDocumentMargin(0)
        self.setOpenLinks(False)
        self.anchorClicked.connect(self._open)
        self.document().documentLayout().documentSizeChanged.connect(self._fit_height)

    def set_markdown(self, text, base=None):
        """text as rendered Markdown; base is the folder its relative images resolve against"""
        self._markdown = text
        self._base = base
        self._render()

    def _render(self):
        document = self.document()
        document.setDefaultFont(self.font())
        if self._base is not None:
            base = QUrl.fromLocalFile(str(self._base) + "/")
            document.setBaseUrl(base)
            self.setSearchPaths([str(self._base)])
        else:
            document.setBaseUrl(QUrl())
            self.setSearchPaths([])
        self.setMarkdown(self._markdown)
        # setMarkdown leaves the base alone, but say it again in case a Qt version doesn't
        if self._base is not None:
            document.setBaseUrl(base)
        self._drop_opening_heading()
        self._style_blocks()
        self._fit_height()

    def _drop_opening_heading(self):
        """As a note's label already says it"""
        document = self.document()
        first = document.firstBlock()
        if first.blockFormat().headingLevel() <= 0:
            return
        cursor = QTextCursor(first)
        second = first.next()
        if not second.isValid():
            cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.setBlockFormat(QTextBlockFormat())
            return
        block_format, char_format = second.blockFormat(), second.charFormat()
        cursor.setPosition(second.position(), QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        # What is left at the start is the second block's text in the first block's place
        cursor.setBlockFormat(block_format)
        cursor.setBlockCharFormat(char_format)

    def _style_blocks(self):
        body = self.font()
        heading = typography.font(typography.Role.HEADING_4)
        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        block = self.document().firstBlock()
        while block.isValid():
            spacing = QTextBlockFormat()
            spacing.setLineHeight(
                BODY_LINE_HEIGHT * 100, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
            )
            cursor.setPosition(block.position())
            cursor.mergeBlockFormat(spacing)
            level = block.blockFormat().headingLevel()
            if level > 0:
                font = heading if level == 1 else body
                weight = heading.weight() if level == 1 else QFont.Weight.DemiBold
                self._restyle_heading(cursor, block, font, weight)
            block = block.next()
        cursor.endEditBlock()

    @staticmethod
    def _restyle_heading(cursor, block, font, weight):
        """The importer sizes a heading per fragment, so each fragment is reset in turn"""
        fragments = []
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid():
                fragments.append((fragment.position(), fragment.length(), fragment.charFormat()))
            iterator += 1
        for position, length, char_format in fragments:
            char_format.clearProperty(QTextFormat.Property.FontSizeAdjustment)
            char_format.setFontPointSize(font.pointSizeF())
            char_format.setFontWeight(weight)
            cursor.setPosition(position)
            cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
            cursor.setCharFormat(char_format)

    def _fit_height(self, *_):
        document = self.document()
        document.setTextWidth(self.viewport().width())
        height = math.ceil(document.size().height()) + 2 * self.frameWidth()
        if height != self.height() or self.minimumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self._fit_height()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and self._markdown:
            self._render()

    def _open(self, url):
        if is_link(url.toString()):
            QDesktopServices.openUrl(url)
