"""The dialogs for exporting decks"""

from PyQt6.QtCore import QEvent, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QPalette
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QStyle,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck_validation import Level
from tarot_canvas.ui import typography, units
from tarot_canvas.ui.library.decks.deck_cover import DeckCover
from tarot_canvas.ui.library.decks.model import deck_author
from tarot_canvas.ui.strings import DECK_VIEW

EMPTY_LIST_ROWS = 6
SUMMARY_WIDTH_UNITS = 18  # the text beside the cover
VERSION_WIDTH_UNITS = 6
_HEADING = typography.Role.HEADING_2
UrlRole = Qt.ItemDataRole.UserRole + 1
LevelRole = Qt.ItemDataRole.UserRole + 2


class ClampedLabel(QLabel):
    """Text wrapped to a fixed box and cut with an ellipsis"""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self._full = text
        self.setToolTip(text)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def full_text(self):
        return self._full

    def line_height(self):
        return self.fontMetrics().lineSpacing()

    def fit(self, width, height):
        self.setFixedSize(width, height)
        self._refit()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self._refit()

    def _refit(self):
        lines = max(1, self.height() // max(1, self.line_height()))
        shown = typography.wrapped_lines(self._full, self.font(), self.width(), lines)
        self.setText("\n".join(shown))


class ExportFieldsDialog(QDialog):
    """What will ship"""

    def __init__(self, deck, empty_cards, parent=None, cover_cache=None):
        super().__init__(parent)
        self.setWindowTitle(DECK_VIEW["export_title"])
        self._saved_version = deck.metadata.version or ""
        layout = QVBoxLayout(self)
        layout.setSpacing(units.LARGE_SPACING)
        layout.addLayout(self._summary(deck, cover_cache))

        self.empty_list = None
        self.empty_label = None
        if empty_cards:
            layout.addLayout(self._empty_section(empty_cards))

        layout.addLayout(self._version_row())
        self.version_edit.textChanged.connect(self._update_export)
        self._update_export()
        self.setSizeGripEnabled(False)
        layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetFixedSize)

    def _summary(self, deck, cover_cache):
        """The cover beside name, artist and description"""
        row = QHBoxLayout()
        row.setSpacing(units.LARGE_SPACING)
        self.cover = DeckCover(cover_cache)
        self.cover.set_deck(deck)
        self.cover.set_expanded(True)
        row.addWidget(self.cover, 0, Qt.AlignmentFlag.AlignTop)

        metadata = deck.metadata
        width = SUMMARY_WIDTH_UNITS * units.GRID_UNIT
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(units.SMALL_SPACING)
        self.name_label = ClampedLabel(metadata.name or "")
        typography.apply(self.name_label, _HEADING, primary=True)
        self.name_label.fit(width, self.name_label.line_height())
        text.addWidget(self.name_label)
        self.artist_label = ClampedLabel(deck_author(deck))
        typography.apply(self.artist_label, typography.Role.SMALL)
        self.artist_label.fit(width, self.artist_label.line_height())
        if not metadata.artist:
            palette = self.artist_label.palette()
            placeholder = palette.color(QPalette.ColorRole.PlaceholderText)
            palette.setColor(QPalette.ColorRole.WindowText, placeholder)
            self.artist_label.setPalette(palette)
        text.addWidget(self.artist_label)
        text.addSpacing(units.SMALL_SPACING)
        self.description_label = ClampedLabel(metadata.description or "")
        used = self.name_label.height() + self.artist_label.height() + 3 * units.SMALL_SPACING
        self.description_label.fit(width, max(0, self.cover.height() - used))
        self.description_label.setVisible(bool(metadata.description))
        text.addWidget(self.description_label)
        text.addStretch(1)
        row.addLayout(text, 1)
        return row

    def _empty_section(self, empty_cards):
        """A warning with the count"""
        section = QVBoxLayout()
        section.setSpacing(units.SMALL_SPACING)
        row = QHBoxLayout()
        icon = QLabel()
        size = self.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize)
        icon.setPixmap(QIcon.fromTheme("dialog-warning").pixmap(size, size))
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        self.empty_label = QLabel(DECK_VIEW["export_empty"].format(count=len(empty_cards)))
        self.empty_label.setWordWrap(True)
        row.addWidget(self.empty_label, 1)
        self.empty_toggle = QToolButton()
        self.empty_toggle.setText(DECK_VIEW["export_empty_show"])
        self.empty_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.empty_toggle.setAutoRaise(True)
        self.empty_toggle.setCheckable(True)
        self.empty_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.empty_toggle.toggled.connect(self._show_empty)
        row.addWidget(self.empty_toggle, 0, Qt.AlignmentFlag.AlignVCenter)
        section.addLayout(row)

        self.empty_list = QListWidget()
        self.empty_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.empty_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.empty_list.addItems([card.display_name for card in empty_cards])
        rows = min(EMPTY_LIST_ROWS, len(empty_cards))
        frame = 2 * self.empty_list.frameWidth()
        self.empty_list.setFixedHeight(self.empty_list.sizeHintForRow(0) * rows + frame)
        self.empty_list.setVisible(False)
        section.addWidget(self.empty_list)
        return section

    def _show_empty(self, shown):
        self.empty_toggle.setArrowType(Qt.ArrowType.DownArrow if shown else Qt.ArrowType.RightArrow)
        self.empty_list.setVisible(shown)

    def _version_row(self):
        """The main field for the user to see"""
        row = QHBoxLayout()
        label = QLabel(DECK_VIEW["field.version"])
        self.version_edit = QLineEdit(self._saved_version)
        self.version_edit.setFixedWidth(VERSION_WIDTH_UNITS * units.GRID_UNIT)
        label.setBuddy(self.version_edit)
        row.addWidget(label)
        row.addWidget(self.version_edit)
        row.addStretch(1)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.export_button = self.buttons.addButton(
            DECK_VIEW["export_confirm"], QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.export_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        row.addWidget(self.buttons)
        return row

    def showEvent(self, event):
        super().showEvent(event)
        # Export is the question; the version rarely needs a change
        self.export_button.setFocus()

    def _update_export(self):
        self.export_button.setEnabled(bool(self.version_edit.text().strip()))

    def changed_fields(self):
        """{"version": text} if it was edited, stripped; else {}"""
        version = self.version_edit.text().strip()
        return {"version": version} if version != self._saved_version else {}


class FindingsDialog(QDialog):
    """Why your deck is busted (chopped and unc)"""

    def __init__(self, verdict, deck, parent=None):
        super().__init__(parent)
        self.setWindowTitle(DECK_VIEW["export_blocked_title"])
        self.resize(units.GRID_UNIT * 48, units.GRID_UNIT * 28)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(DECK_VIEW["export_blocked"]))

        self.tree = None
        self.details_box = None
        if verdict.load_error is not None:
            error = verdict.load_error
            self.load_error_label = QLabel(
                DECK_VIEW["export_load_error"].format(code=error.code, message=error.message)
            )
            self.load_error_label.setWordWrap(True)
            self.load_error_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            layout.addWidget(self.load_error_label)
        else:
            self.tree = self._tree(verdict.findings, deck)
            layout.addWidget(self.tree, 1)
            self.details_box = QCheckBox(DECK_VIEW["export_show_details"])
            self.details_box.toggled.connect(self._show_details)
            layout.addWidget(self.details_box)
            self._show_details(False)

        self.coverage = QLabel(DECK_VIEW["export_unchecked"].format(count=verdict.unchecked_rules))
        self.coverage.setWordWrap(True)
        layout.addWidget(self.coverage)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _tree(self, findings, deck):
        tree = QTreeWidget()
        tree.setColumnCount(2)
        tree.setHeaderHidden(True)
        tree.setRootIsDecorated(True)
        by_card = {}
        for finding in findings:
            by_card.setdefault(finding.card, []).append(finding)
        for card in sorted(by_card, key=_card_order):
            top = QTreeWidgetItem([_card_name(card, deck)])
            tree.addTopLevelItem(top)
            for finding in sorted(by_card[card], key=lambda f: -f.level):
                where = finding.key or finding.path
                row = QTreeWidgetItem(
                    [finding.message, f"{finding.code} · {where}" if where else finding.code]
                )
                row.setData(0, LevelRole, int(finding.level))
                if finding.spec_url:
                    row.setData(0, UrlRole, finding.spec_url)
                    for column in (0, 1):
                        row.setToolTip(column, finding.spec_url)
                top.addChild(row)
            top.setExpanded(True)
        tree.itemActivated.connect(_open_spec)
        tree.resizeColumnToContents(1)
        return tree

    def _show_details(self, shown):
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            visible = 0
            for j in range(top.childCount()):
                row = top.child(j)
                hidden = not shown and row.data(0, LevelRole) < Level.WARNING
                row.setHidden(hidden)
                visible += not hidden
            top.setHidden(not visible)


def _card_order(card):
    """The deck-level findings first then the cards"""
    if card is None:
        return (0, 0, "")
    if card in CANONICAL_CARD_IDS:
        return (1, CANONICAL_CARD_IDS.index(card), card)
    return (2, 0, card)


def _card_name(card, deck):
    if card is None:
        return DECK_VIEW["export_deck_level"]
    found = deck.find_card(card) if deck is not None else None
    return found.display_name if found is not None else card


def _open_spec(item, _column):
    url = item.data(0, UrlRole)
    if url:
        QDesktopServices.openUrl(QUrl(url))
