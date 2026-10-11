from enum import Enum

from PyQt6.QtCore import QAbstractListModel, QModelIndex, Qt

from tarot_canvas.models.coverage import CellState
from tarot_canvas.settings import get_esoterica_disabled, set_esoterica_disabled
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.license_names import license_name

KindRole = Qt.ItemDataRole.UserRole + 31
NotReadRole = Qt.ItemDataRole.UserRole + 33
IdentifierRole = Qt.ItemDataRole.UserRole + 34
CoverageRole = Qt.ItemDataRole.UserRole + 35
CountRole = Qt.ItemDataRole.UserRole + 36
TypeRole = Qt.ItemDataRole.UserRole + 37

SECTION_INSTALLED = "installed"
SECTION_NOT_READ = "not_read"


class RowKind(Enum):
    SECTION = "section"
    SOURCE = "source"
    NOT_READ = "not_read"


def meta_text(value):
    """A [meta] value as the file wrote it, or None for an absent, empty or non-scalar one"""
    if isinstance(value, str):
        return value if value.strip() else None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return None


def byline(source):
    """[meta].author verbatim and [meta].license by name, skipping either one that is empty"""
    meta = source["meta"]
    parts = [meta_text(meta.get("author")), license_name(meta_text(meta.get("license")))]
    return label_for("joiner").join(part for part in parts if part)


def filled_count(states):
    return sum(state == CellState.FILLED for state in states or ())


class EsotericaListModel(QAbstractListModel):
    """Every source the manager read, then every file it skipped, each under a section row"""

    def __init__(self, manager, parent=None):
        super().__init__(parent)
        self._manager = manager
        self._search = ""
        self._disabled = set()
        self._rows = []  # (RowKind, payload)
        self._rebuild()

    def refresh(self):
        """Re-read the manager's sources and which of them are turned off"""
        self.beginResetModel()
        self._rebuild()
        self.endResetModel()

    def set_search(self, search):
        search = (search or "").strip()
        if search == self._search:
            return
        self.beginResetModel()
        self._search = search
        self._rebuild()
        self.endResetModel()

    def search(self):
        return self._search

    def total_rows(self):
        return len(self._manager.sources) + len(self._manager.not_read)

    def _rebuild(self):
        self._disabled = set(get_esoterica_disabled())
        folded = self._search.casefold()

        installed = [
            (identifier, source)
            for identifier, source in self._manager.sources.items()
            if _matches(folded, source["name"], source["author"], identifier)
        ]
        installed.sort(key=lambda pair: pair[1]["name"].casefold())
        not_read = [item for item in self._manager.not_read if _matches(folded, item.path.name)]
        not_read.sort(key=lambda item: str(item.path))

        self._rows = []
        # A section with no rows has no heading
        if installed:
            self._rows.append((RowKind.SECTION, SECTION_INSTALLED))
            self._rows.extend((RowKind.SOURCE, pair) for pair in installed)
        if not_read:
            self._rows.append((RowKind.SECTION, SECTION_NOT_READ))
            self._rows.extend((RowKind.NOT_READ, item) for item in not_read)

    def has_items(self):
        """Whether any row is a source or a skipped file, rather than a heading"""
        return any(kind != RowKind.SECTION for kind, _ in self._rows)

    def index_for_identifier(self, identifier):
        for row, (kind, payload) in enumerate(self._rows):
            if kind == RowKind.SOURCE and payload[0] == identifier:
                return self.index(row, 0)
        return QModelIndex()

    def index_for_path(self, path):
        """A skipped file's row"""
        for row, (kind, payload) in enumerate(self._rows):
            if kind == RowKind.NOT_READ and payload.path == path:
                return self.index(row, 0)
        return QModelIndex()

    def rowCount(self, parent=None):
        if parent is not None and parent.isValid():
            return 0
        return len(self._rows)

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        kind, _ = self._rows[index.row()]
        if kind == RowKind.SECTION:
            # Drawn by the delegate, but never selected, focused or activated
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if kind == RowKind.SOURCE:
            flags |= Qt.ItemFlag.ItemIsUserCheckable
        return flags

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._rows):
            return None
        kind, payload = self._rows[index.row()]

        if role == KindRole:
            return kind
        if kind == RowKind.SECTION:
            if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
                return label_for(f"library.section.{payload}")
            return None
        if kind == RowKind.NOT_READ:
            return self._not_read_data(payload, role)
        return self._source_data(*payload, role)

    def _source_data(self, identifier, source, role):
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return source["name"]
        if role == SubtitleRole:
            return byline(source)
        if role == Qt.ItemDataRole.CheckStateRole:
            off = identifier in self._disabled
            return Qt.CheckState.Unchecked if off else Qt.CheckState.Checked
        if role == IdentifierRole:
            return identifier
        if role == CoverageRole:
            return source.get("coverage")
        if role == CountRole:
            return filled_count(source.get("coverage"))
        if role == TypeRole:
            return source["meta"].get("type")
        return None

    def _not_read_data(self, item, role):
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return item.path.name
        if role == SubtitleRole:
            return label_for(f"library.reason.{item.reason.value}")
        if role == NotReadRole:
            return item
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        """Turning a source on or off"""
        if role != Qt.ItemDataRole.CheckStateRole or not index.isValid():
            return False
        kind, payload = self._rows[index.row()]
        if kind != RowKind.SOURCE:
            return False

        identifier = payload[0]
        on = Qt.CheckState(value) == Qt.CheckState.Checked
        # Identifiers this run didn't read, from another machine or a removed file, are kept
        disabled = [item for item in get_esoterica_disabled() if item != identifier]
        if not on:
            disabled.append(identifier)
        self._disabled = set(disabled)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.CheckStateRole])
        set_esoterica_disabled(disabled)
        return True


def _matches(folded, *haystacks):
    if not folded:
        return True
    return any(folded in (hay or "").casefold() for hay in haystacks)
