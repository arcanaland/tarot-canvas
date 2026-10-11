"""The Esoterica view's details pane"""

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import QEvent, QPointF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics, QPainter, QPalette
from PyQt6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS, SUITS
from tarot_canvas.models.coverage import CellState
from tarot_canvas.models.esoterica import NotReadReason, group_keys
from tarot_canvas.ui import typography
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library import units
from tarot_canvas.ui.library.coverage_strip import (
    grid_cell_rects,
    grid_height,
    grid_label_width,
    paint_coverage_grid,
)
from tarot_canvas.ui.library.deck_details_pane import LICENSE_LABEL, VERSION_LABEL
from tarot_canvas.ui.library.esoterica_list_model import (
    IdentifierRole,
    KindRole,
    NotReadRole,
    RowKind,
    meta_text,
)
from tarot_canvas.ui.library.pane_text import pane_form, pane_text
from tarot_canvas.ui.license_names import license_name
from tarot_canvas.ui.widgets.deck_header import is_link, link_html

# ESOTERICA §4.1.4's registry; any other relation heads the work group as no relation does
RELATIONS = frozenset({"transcribes", "abridges", "annotates"})


@dataclass(frozen=True)
class SourceDetails:
    key: str  # the identifier, or a skipped file's path
    name: str
    path: Path
    author: str | None = None
    source_type: object = None
    version: str | None = None
    license: str | None = None
    copyright: str | None = None
    attribution: str | None = None
    description: str | None = None
    identifier: str | None = None
    shadows: tuple[Path, ...] = ()
    coverage: tuple | None = None
    groups: tuple[str, ...] = ()
    # [meta].related
    pattern: str | None = None
    about: tuple[str, ...] = ()
    relation: str | None = None
    # [meta.work]
    has_work: bool = False
    work_name: str | None = None
    work_author: str | None = None
    work_published: str | None = None
    work_isbn: str | None = None
    work_url: str | None = None
    reason: NotReadReason | None = None


def _related(meta):
    """[meta].related's (rel, target, title) entries"""
    related = meta.get("related")
    if not isinstance(related, list):
        return
    for entry in related:
        if not isinstance(entry, dict):
            continue
        rel, target = entry.get("rel"), entry.get("target")
        if isinstance(rel, str) and isinstance(target, str):
            yield rel, target, meta_text(entry.get("title"))


def _pattern_label(target):
    return label_for(f"pattern.{target}") or None


def source_details(identifier, source, shadows=()):
    meta = source["meta"]
    related = list(_related(meta))
    pattern = next((_pattern_label(t) for rel, t, _ in related if rel == "pattern"), None)
    about = (title or _pattern_label(t) for rel, t, title in related if rel == "about")
    work = meta.get("work")
    work = work if isinstance(work, dict) else None
    coverage = source.get("coverage")
    return SourceDetails(
        key=identifier,
        name=source["name"],
        path=source["path"],
        author=meta_text(meta.get("author")),
        source_type=meta.get("type"),
        version=meta_text(meta.get("version")),
        license=meta_text(meta.get("license")),
        copyright=meta_text(meta.get("copyright")),
        attribution=meta_text(meta.get("attribution")),
        description=meta_text(meta.get("description")),
        identifier=identifier,
        shadows=tuple(shadows),
        coverage=tuple(coverage) if coverage is not None else None,
        groups=tuple(group_keys(source)),
        pattern=pattern,
        about=tuple(label for label in about if label),
        relation=meta_text(meta.get("relation")),
        has_work=work is not None,
        work_name=meta_text((work or {}).get("name")),
        work_author=meta_text((work or {}).get("author")),
        work_published=meta_text((work or {}).get("published_date")),
        work_isbn=meta_text((work or {}).get("isbn")),
        work_url=meta_text((work or {}).get("url")),
    )


def not_read_details(item):
    return SourceDetails(
        key=str(item.path), name=item.path.name, path=item.path, reason=item.reason
    )


def details_for(index, manager):
    """The details of a list row"""
    kind = index.data(KindRole)
    if kind == RowKind.SOURCE:
        identifier = index.data(IdentifierRole)
        # From the manager, not through data(): Qt would hand back a copy, its keys sorted
        source = manager.sources[identifier]
        return source_details(identifier, source, manager.shadowed.get(identifier, ()))
    if kind == RowKind.NOT_READ:
        return not_read_details(index.data(NotReadRole))
    return None


class CoverageGridWidget(QWidget):
    card_activated = pyqtSignal(str)  # the canonical card id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._states = ()
        self._hovered = None

        # The card's name for a cell's tooltip
        self.card_name = lambda card_id: card_id
        self.setMouseTracking(True)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def labels(self):
        major = label_for("library.coverage.major")
        return (major, *(suit.capitalize() for suit in SUITS))

    def _label_font(self):
        return typography.font(typography.Role.SMALL)

    def _label_width(self):
        return grid_label_width(self.labels(), QFontMetrics(self._label_font()))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return grid_height(width, self._label_width())

    def sizeHint(self):
        width = super().sizeHint().width()
        return QSize(width, self.heightForWidth(max(width, self.width())))

    def set_states(self, states):
        self._states = tuple(states or ())
        self._set_hovered(None)
        self.update()

    def cell_at(self, pos):
        """The index of the cell under pos"""
        point = QPointF(pos)
        for index, rect in enumerate(grid_cell_rects(self.rect(), self._label_width())):
            if rect.contains(point):
                return index
        return None

    def link_at(self, pos):
        index = self.cell_at(pos)
        if index is None or index >= len(self._states):
            return None
        return index if self._states[index] == CellState.FILLED else None

    def _set_hovered(self, index):
        if index == self._hovered:
            return
        self._hovered = index
        if index is None:
            self.unsetCursor()
        else:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update()

    def mouseMoveEvent(self, event):
        self._set_hovered(self.link_at(event.position()))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._set_hovered(None)
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        index = self.link_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and index is not None:
            self.card_activated.emit(CANONICAL_CARD_IDS[index])
            return
        super().mouseReleaseEvent(event)

    def event(self, event):
        if event.type() == QEvent.Type.ToolTip:
            index = self.cell_at(event.pos())
            if index is None:
                QToolTip.hideText()
            else:
                QToolTip.showText(
                    event.globalPos(), self.card_name(CANONICAL_CARD_IDS[index]), self
                )
            return True
        return super().event(event)

    def states(self):
        return self._states

    def paintEvent(self, _event):
        painter = QPainter(self)
        paint_coverage_grid(
            painter,
            self.rect(),
            self._states,
            self.palette(),
            self.labels(),
            self._label_font(),
            self._hovered,
        )
        painter.end()


class SourceDetailsPane(QWidget):
    open_card_requested = pyqtSignal(str)  # the canonical card id

    # Below this width the two columns stack, the source above its properties
    TWO_COLUMN_MIN_WIDTH = 36 * units.GRID_UNIT

    def __init__(self, parent=None):
        super().__init__(parent)
        self._details = None

        self.heading_label = typography.apply(pane_text(), typography.Role.HEADING_1, primary=True)
        self.author_label = pane_text()

        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(units.SMALL_SPACING)
        header.addWidget(self.heading_label)
        header.addWidget(self.author_label)

        # What a reader needs
        self.form = pane_form()
        self.pattern_label = self._add_row(self.form, label_for("library.form.pattern"))
        self.about_label = self._add_row(self.form, label_for("library.form.about"))
        self.license_label = self._add_row(self.form, LICENSE_LABEL)
        self.copyright_label = self._add_row(self.form, label_for("library.form.copyright"))
        self.file_label = self._add_row(self.form, label_for("library.form.file"))

        # What a source's author needs, closed until asked for
        self.source_file_button = QToolButton()
        self.source_file_button.setText(label_for("library.source_file_heading"))
        self.source_file_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.source_file_button.setAutoRaise(True)
        self.source_file_button.clicked.connect(
            lambda: self.set_source_file_open(not self._source_file_open)
        )
        self.source_file_group = QWidget()
        self.source_file_form = pane_form()
        self.source_file_group.setLayout(self.source_file_form)
        self.source_file_form.setContentsMargins(0, 0, 0, 0)
        self.identifier_label = self._add_row(
            self.source_file_form, label_for("library.form.identifier")
        )
        self.version_label = self._add_row(self.source_file_form, VERSION_LABEL)
        self.groups_label = self._add_row(self.source_file_form, label_for("library.form.groups"))
        self.shadows_label = self._add_row(self.source_file_form, label_for("library.form.shadows"))

        # Keys and paths
        for label in (
            self.file_label,
            self.identifier_label,
            self.groups_label,
            self.shadows_label,
        ):
            typography.apply(label, typography.Role.BODY, fixed=True)
        self.set_source_file_open(False)

        # description + the credit line as a caption
        self.description_label = pane_text()
        self.attribution_label = typography.apply(pane_text(), typography.Role.SMALL)
        self.attribution_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)

        # coverage
        self.coverage_grid = CoverageGridWidget()
        self.coverage_grid.card_activated.connect(self.open_card_requested)

        # The work
        self.work_group = QWidget()
        self.work_heading = typography.apply(pane_text(), typography.Role.HEADING_4)
        self.work_form = pane_form()
        self.work_form.setContentsMargins(0, 0, 0, 0)
        self.work_name_label = self._add_row(self.work_form, label_for("library.form.work_name"))
        self.work_author_label = self._add_row(
            self.work_form, label_for("library.form.work_author")
        )
        self.work_published_label = self._add_row(
            self.work_form, label_for("library.form.work_published")
        )
        self.work_isbn_label = self._add_row(self.work_form, label_for("library.form.work_isbn"))
        self.work_url_label = self._add_row(self.work_form, label_for("library.form.work_url"))
        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setFrameShadow(QFrame.Shadow.Sunken)
        work_column = QVBoxLayout(self.work_group)
        work_column.setContentsMargins(0, 0, 0, 0)
        work_column.setSpacing(units.LARGE_SPACING)
        work_column.addWidget(rule)
        work_column.addWidget(self.work_heading)
        work_column.addLayout(self.work_form)

        # Left: what the source is. Right: its properties and the work it annotates
        source_column = QVBoxLayout()
        source_column.setContentsMargins(0, 0, 0, 0)
        source_column.setSpacing(units.LARGE_SPACING)
        source_column.addLayout(header)
        source_column.addWidget(self.description_label)
        source_column.addWidget(self.attribution_label)
        source_column.addWidget(self.coverage_grid)
        source_column.addStretch(1)

        properties_column = QVBoxLayout()
        properties_column.setContentsMargins(0, 0, 0, 0)
        properties_column.setSpacing(units.LARGE_SPACING)
        properties_column.addLayout(self.form)
        properties_column.addWidget(self.work_group)
        properties_column.addWidget(self.source_file_button, 0, Qt.AlignmentFlag.AlignLeft)
        properties_column.addWidget(self.source_file_group)
        properties_column.addStretch(1)

        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setContentsMargins(0, 0, 0, 0)
        self.columns.setSpacing(units.GRID_UNIT)
        self.columns.addLayout(source_column, 1)
        self.columns.addLayout(properties_column, 1)

        margin = units.GRID_UNIT
        body = QVBoxLayout()
        body.setContentsMargins(margin, 2 * units.LARGE_SPACING, margin, margin)
        body.setSpacing(units.LARGE_SPACING)
        body.addLayout(self.columns)
        body.addStretch(1)

        content = QWidget()
        content.setLayout(body)

        self.scroll_area = QScrollArea()
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.scroll_area, 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        stacked = event.size().width() < self.TWO_COLUMN_MIN_WIDTH
        self.columns.setDirection(
            QBoxLayout.Direction.TopToBottom if stacked else QBoxLayout.Direction.LeftToRight
        )

    @staticmethod
    def _add_row(form, label):
        name = QLabel(label)
        name.setTextFormat(Qt.TextFormat.PlainText)
        value = pane_text()
        form.addRow(name, value)
        return value

    def set_source_file_open(self, open_):
        """Open or close the source file group"""
        self._source_file_open = open_
        self.source_file_button.setArrowType(
            Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow
        )
        self.source_file_group.setVisible(open_ and not self.source_file_button.isHidden())

    def source_file_open(self):
        return self._source_file_open

    def details(self):
        return self._details

    def show_details(self, details):
        previous, self._details = self._details, details
        if details is None:
            return
        skipped = details.reason is not None

        self._set_text(self.heading_label, details.name)
        if skipped:
            reason = label_for(f"library.reason.{details.reason.value}")
            self._set_text(self.author_label, reason or None)
        else:
            self._set_text(self.author_label, details.author)

        joiner = label_for("joiner")
        self._set_row(self.form, self.pattern_label, details.pattern)
        self._set_row(self.form, self.about_label, joiner.join(details.about) or None)
        self._set_row(self.form, self.license_label, license_name(details.license))
        self._set_row(self.form, self.copyright_label, details.copyright)
        self._set_row(self.form, self.file_label, str(details.path) if skipped else None)

        source_file = self.source_file_form
        self._set_row(source_file, self.identifier_label, details.identifier)
        self._set_row(source_file, self.version_label, details.version)
        self._set_row(source_file, self.groups_label, joiner.join(details.groups) or None)
        shadows = "\n".join(str(path) for path in details.shadows)
        self._set_row(source_file, self.shadows_label, shadows or None)
        # Hidden with nothing in it, and for a skipped file, which has nothing to put in it
        has_rows = any(
            source_file.isRowVisible(label)
            for label in (
                self.identifier_label,
                self.version_label,
                self.groups_label,
                self.shadows_label,
            )
        )
        self.source_file_button.setHidden(
            skipped or not has_rows or not self.source_file_button.text()
        )
        self.set_source_file_open(self._source_file_open)

        self._set_text(self.description_label, details.description)
        self._set_text(self.attribution_label, details.attribution)

        self.coverage_grid.set_states(details.coverage)
        self.coverage_grid.setVisible(details.coverage is not None)

        self.work_group.setVisible(details.has_work)
        if details.relation in RELATIONS:
            work_heading = label_for(f"library.relation.{details.relation}")
        else:
            work_heading = label_for("library.work_heading")
        self._set_text(self.work_heading, work_heading or None)
        self._set_row(self.work_form, self.work_name_label, details.work_name)
        self._set_row(self.work_form, self.work_author_label, details.work_author)
        self._set_row(self.work_form, self.work_published_label, details.work_published)
        self._set_row(self.work_form, self.work_isbn_label, details.work_isbn)
        self._set_link_row(self.work_form, self.work_url_label, details.work_url)

        if previous is None or previous.key != details.key:
            self.scroll_area.verticalScrollBar().setValue(0)

    @staticmethod
    def _set_text(label, text):
        label.setText(text or "")
        label.setVisible(text is not None)

    @classmethod
    def _set_link_row(cls, form, label, url):
        """A URL row"""
        linked = url is not None and is_link(url)
        label.setTextFormat(Qt.TextFormat.RichText if linked else Qt.TextFormat.PlainText)
        label.setOpenExternalLinks(linked)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            if linked
            else Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cls._set_row(form, label, link_html(None, [url]) if linked else url)

    @staticmethod
    def _set_row(form, label, text):
        label.setText(text or "")
        # An empty form label hides its row, as an empty string hides anything it labels
        name = form.labelForField(label)
        named = name is None or bool(name.text())
        form.setRowVisible(label, text is not None and named)
