"""Export's dialogs: the fields it asks for, and what blocked it"""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
from tarot_canvas.models.deck_validation import Level
from tarot_canvas.ui import units
from tarot_canvas.ui.strings import DECK_VIEW

EMPTY_LIST_ROWS = 6
UrlRole = Qt.ItemDataRole.UserRole + 1
LevelRole = Qt.ItemDataRole.UserRole + 2


class ExportFieldsDialog(QDialog):
    """Version, artist and description, and the empty cards Export will leave out"""

    def __init__(self, deck, empty_cards, parent=None):
        super().__init__(parent)
        self.setWindowTitle(DECK_VIEW["export_title"])
        metadata = deck.metadata
        self._saved = {
            "version": metadata.version or "",
            "artist": metadata.artist or "",
            "description": metadata.description or "",
        }
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.version_edit = QLineEdit(self._saved["version"])
        self.artist_edit = QLineEdit(self._saved["artist"])
        self.description_edit = QPlainTextEdit(self._saved["description"])
        form.addRow(DECK_VIEW["field.version"], self.version_edit)
        form.addRow(DECK_VIEW["field.artist"], self.artist_edit)
        form.addRow(DECK_VIEW["field.description"], self.description_edit)
        layout.addLayout(form)

        self.empty_list = None
        if empty_cards:
            layout.addLayout(self._empty_section(empty_cards))

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        self.export_button = self.buttons.addButton(
            DECK_VIEW["export_confirm"], QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.export_button.setDefault(True)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.version_edit.textChanged.connect(self._update_export)
        self._update_export()

    def _empty_section(self, empty_cards):
        row = QHBoxLayout()
        icon = QLabel()
        size = self.style().pixelMetric(QStyle.PixelMetric.PM_SmallIconSize)
        icon.setPixmap(QIcon.fromTheme("dialog-warning").pixmap(size, size))
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        column = QVBoxLayout()
        self.empty_label = QLabel(DECK_VIEW["export_empty"].format(count=len(empty_cards)))
        self.empty_label.setWordWrap(True)
        column.addWidget(self.empty_label)
        self.empty_list = QListWidget()
        self.empty_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.empty_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.empty_list.addItems([card.display_name for card in empty_cards])
        rows = min(EMPTY_LIST_ROWS, len(empty_cards))
        frame = 2 * self.empty_list.frameWidth()
        self.empty_list.setMaximumHeight(self.empty_list.sizeHintForRow(0) * rows + frame)
        column.addWidget(self.empty_list)
        row.addLayout(column, 1)
        return row

    def _update_export(self):
        self.export_button.setEnabled(bool(self.version_edit.text().strip()))

    def changed_fields(self):
        """The fields edited, stripped; "" to remove one"""
        typed = {
            "version": self.version_edit.text().strip(),
            "artist": self.artist_edit.text().strip(),
            "description": self.description_edit.toPlainText().strip(),
        }
        return {key: text for key, text in typed.items() if text != self._saved[key]}


class FindingsDialog(QDialog):
    """Why Export wrote nothing: the load error, or the findings card by card"""

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
    """The deck-level findings first, then the cards in canonical order"""
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
