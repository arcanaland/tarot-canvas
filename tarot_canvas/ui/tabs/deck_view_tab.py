import logging
from pathlib import Path

from PyQt6.QtCore import (
    QEvent,
    QItemSelection,
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import deck_writer, library_curation
from tarot_canvas.models.deck_library import deck_library
from tarot_canvas.models.deck_writer import DeckWriteError
from tarot_canvas.settings import (
    DECK_VIEW_DENSITY_DEFAULT,
    DECK_VIEW_DENSITY_KEY,
    DECK_VIEW_MODE_DEFAULT,
    DECK_VIEW_MODE_KEY,
    DECK_VIEW_MODE_SECTIONS,
    DECK_VIEW_MODE_TABLEAU,
    DECK_VIEW_MODES,
    get_settings,
)
from tarot_canvas.ui import units
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.card_transfer import copy_cards_to_clipboard
from tarot_canvas.ui.deck_view.card_delegate import CardDelegate
from tarot_canvas.ui.deck_view.card_model import (
    KIND_BACK,
    KIND_CARD,
    BackPathRole,
    CardFilter,
    CardModel,
    CardRole,
    KindRole,
)
from tarot_canvas.ui.deck_view.deck_editor import DeckEditor
from tarot_canvas.ui.deck_view.minors_offer import MinorsOffer
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.deck_view.tableau_model import TableauModel
from tarot_canvas.ui.deck_view.tableau_view import TableauView
from tarot_canvas.ui.deck_view.unsorted_strip import UnsortedStrip
from tarot_canvas.ui.dropped_files import dropped_files, offered_files
from tarot_canvas.ui.icons import deck_icon
from tarot_canvas.ui.library.decks import header as deck_header
from tarot_canvas.ui.library.decks.header import DeckHeader
from tarot_canvas.ui.library.decks.model import is_majors_only
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets.search_field import search_field
from tarot_canvas.ui.widgets.zoom_slider import ZoomSlider

log = logging.getLogger(__name__)

SECTION_MARGIN = deck_header.EDGE_MARGIN

VIEW_ICONS = {
    DECK_VIEW_MODE_SECTIONS: "view-list-icons",
    DECK_VIEW_MODE_TABLEAU: "table",
}


class DeckViewTab(BaseTab):
    card_clicked = pyqtSignal(str)  # Signal when a card is clicked
    card_action_requested = pyqtSignal(str, object, object)  # action, card, deck
    new_canvas_requested = pyqtSignal(list, object)  # cards, deck

    def __init__(self, deck_path, parent=None):
        super().__init__(parent)
        self.deck_path = deck_path
        self.deck = None
        self.mode = None
        self.editable = False
        self.editor = None
        self.unsorted = None
        self.minors_offer = None
        self.settings = get_settings()
        self.setup_ui()

    def setup_ui(self):
        self.load_deck(self.deck_path)

    def load_deck(self, deck_path):
        self.deck = deck_library.load(deck_path)
        self.editable = library_curation.was_created_here(self.deck.root_path)

        self.tab_label_changed.emit()

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Pinned above the page, as the Library's is
        self.layout.addWidget(self._build_header())

        # Main content widget with vertical layout
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Deck-level header at the top of the page
        self.content_layout = main_layout
        self.header = DeckHeader(self.deck, parent=content, created=self.editable)
        main_layout.addWidget(self.header)

        # The grid's own spacing makes up the rest of the margin, so headings line up
        # with the header's text
        grid_row = QVBoxLayout()
        self.grid = self._build_grid()
        self.tableau = self._build_tableau()
        self._views = {DECK_VIEW_MODE_SECTIONS: self.grid, DECK_VIEW_MODE_TABLEAU: self.tableau}
        self.views = QStackedWidget()
        self._pages = {
            DECK_VIEW_MODE_SECTIONS: self._page(self.grid),
            DECK_VIEW_MODE_TABLEAU: self._page(self.tableau, centred=True),
        }
        for page in self._pages.values():
            self.views.addWidget(page)
        inset = SECTION_MARGIN - self.grid.spacing()
        grid_row.setContentsMargins(inset, 0, inset, SECTION_MARGIN)
        grid_row.addWidget(self.views)
        if self.editable:
            self.minors_offer = MinorsOffer()
            self.minors_offer.accepted.connect(self.include_minors)
            self.minors_offer.setVisible(is_majors_only(self.deck))
            offer_row = QHBoxLayout()
            offer_row.setContentsMargins(self.grid.spacing(), 0, self.grid.spacing(), 0)
            offer_row.addWidget(self.minors_offer)
            grid_row.addLayout(offer_row)
            self.unsorted = UnsortedStrip(self.deck.root_path, self.delegate.cover_size())
            self.unsorted.files_dropped.connect(self.send_to_unsorted)
            self.unsorted.discard_requested.connect(self.discard_unsorted)
            self.unsorted.view.selectionModel().currentChanged.connect(self.edit_state_changed)
            unsorted_row = QHBoxLayout()
            unsorted_row.setContentsMargins(self.grid.spacing(), 0, self.grid.spacing(), 0)
            unsorted_row.addWidget(self.unsorted)
            grid_row.addLayout(unsorted_row)
        main_layout.addLayout(grid_row)
        main_layout.addStretch()

        # Add the content to a scroll area
        self.scroll = scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        # Anywhere on the page, where a wheel over the grid ends up too
        self.zoom_slider.zoom_on_ctrl_wheel(scroll.viewport())

        # The frame would put a line between the banner and the tab bar.
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self.layout.addWidget(scroll)

        self.set_view_mode(
            self.settings.value(DECK_VIEW_MODE_KEY, DECK_VIEW_MODE_DEFAULT, type=str)
        )

        if self.editable:
            self.editor = DeckEditor(self.deck.root_path, self)
            self.editor.progress.connect(self.on_write_progress)
            self.editor.finished.connect(self.on_write_done)
            self.editor.failed.connect(self.on_write_failed)
            # Converges whatever an interrupted write left
            self.editor.refresh()

    def _build_header(self):
        header = QWidget()
        row = QHBoxLayout(header)
        # Level with the banner's text and the headings
        row.setContentsMargins(
            SECTION_MARGIN, units.LARGE_SPACING, SECTION_MARGIN, units.LARGE_SPACING
        )
        row.setSpacing(units.LARGE_SPACING)

        self.search_field = search_field(DECK_VIEW["find_card"])
        self.search_field.textChanged.connect(self.on_search_changed)
        row.addWidget(self.search_field, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        row.addWidget(self.progress_bar)

        self.zoom_slider = ZoomSlider(
            units.DENSITIES, DECK_VIEW["cover_size"], DECK_VIEW_DENSITY_DEFAULT
        )
        density = self.settings.value(DECK_VIEW_DENSITY_KEY, DECK_VIEW_DENSITY_DEFAULT, type=str)
        self.zoom_slider.set_key(
            density if density in units.DENSITIES else DECK_VIEW_DENSITY_DEFAULT
        )
        self.zoom_slider.key_changed.connect(self.on_density_changed)
        row.addWidget(self.zoom_slider)

        row.addWidget(self._build_view_bar())
        return header

    def _build_view_bar(self):
        bar = QWidget()
        bar.setAccessibleName(DECK_VIEW["view_bar_name"])
        buttons = QHBoxLayout(bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(0)

        self.view_group = QButtonGroup(bar)
        self.view_group.setExclusive(True)
        self.view_buttons = {}
        names = {
            DECK_VIEW_MODE_SECTIONS: (DECK_VIEW["sections_name"], DECK_VIEW["sections_tooltip"]),
            DECK_VIEW_MODE_TABLEAU: (DECK_VIEW["tableau_name"], DECK_VIEW["tableau_tooltip"]),
        }
        for mode in DECK_VIEW_MODES:
            name, tooltip = names[mode]
            button = QToolButton()
            button.setIcon(QIcon.fromTheme(VIEW_ICONS[mode]))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setCheckable(True)
            button.setAutoRaise(True)
            button.setToolTip(tooltip)
            button.setAccessibleName(name)
            button.clicked.connect(lambda _checked, mode=mode: self.on_view_chosen(mode))
            self.view_group.addButton(button)
            self.view_buttons[mode] = button
            buttons.addWidget(button)
        return bar

    def _build_grid(self):
        self.model = CardModel(self.deck, self, editable=self.editable)
        # The grid shows what Find leaves of the deck
        self.found = CardFilter(self)
        self.found.setSourceModel(self.model)
        grid = SectionsView()
        grid.setModel(self.found)
        self.delegate = CardDelegate(grid, density=self.zoom_slider.key(), editable=self.editable)
        grid.setItemDelegate(self.delegate)
        self._connect_view(grid)
        return grid

    def _build_tableau(self):
        self.tableau_model = TableauModel(self.model, self)
        tableau = TableauView()
        tableau.setItemDelegate(self.delegate)
        tableau.setModel(self.tableau_model)
        self._connect_view(tableau)
        return tableau

    def _connect_view(self, view):
        view.activated.connect(self.on_card_activated)
        activate_on_return(view)
        view.clicked.connect(self.on_card_clicked)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self.on_context_menu)
        view.selectionModel().currentChanged.connect(self.on_current_changed)
        view.selectionModel().selectionChanged.connect(self.edit_state_changed)
        if self.editable:
            view.setAcceptDrops(True)
            view.viewport().setAcceptDrops(True)
            view.viewport().installEventFilter(_SlotDrops(view, self))

    @staticmethod
    def _page(view, centred=False):
        page = QWidget()
        row = QHBoxLayout(page)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        if centred:
            row.addStretch()
        row.addWidget(view, 0 if centred else 1, Qt.AlignmentFlag.AlignTop)
        if centred:
            row.addStretch()
        return page

    # -- views --------------------------------------------------------------

    def current_view(self):
        return self._views[self.mode]

    def on_view_chosen(self, mode):
        self.settings.setValue(DECK_VIEW_MODE_KEY, mode)
        self.set_view_mode(mode)

    def set_view_mode(self, mode):
        if mode not in DECK_VIEW_MODES:
            mode = DECK_VIEW_MODE_DEFAULT
        old = self._views.get(self.mode)
        self.mode = mode
        self.view_buttons[mode].setChecked(True)

        for each, page in self._pages.items():
            policy = QSizePolicy.Policy.Preferred if each == mode else QSizePolicy.Policy.Ignored
            page.setSizePolicy(policy, policy)

        self.views.setCurrentWidget(self._pages[mode])

        new = self.current_view()
        if old is not None and old is not new:
            self._carry_selection(old, new)
        self.edit_state_changed()

    def _carry_selection(self, old, new):
        """The same cards, and the same current card, in the view switched to"""
        had_focus = old.hasFocus()
        current = old.model().mapToSource(old.currentIndex())
        selection = QItemSelection()
        for row in self.selected_source_rows(old):
            index = new.model().mapFromSource(self.model.index(row, 0))
            if index.isValid():
                selection.select(index, index)

        target = new.model().mapFromSource(current) if current.isValid() else QModelIndex()
        selection_model = new.selectionModel()
        selection_model.setCurrentIndex(target, QItemSelectionModel.SelectionFlag.NoUpdate)
        selection_model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        if had_focus:
            new.setFocus(Qt.FocusReason.OtherFocusReason)
        # Once the page it's on is laid out
        QTimer.singleShot(0, lambda: self.on_current_changed(new.currentIndex(), None))

    # -- cards ------------------------------------------------------------

    def selected_source_rows(self, view=None):
        """Rows of the card model selected in a view (the current one by default)"""
        view = view or self.current_view()
        model = view.model()
        rows = {model.mapToSource(index).row() for index in view.selectionModel().selectedIndexes()}
        rows.discard(-1)
        return sorted(rows)

    def selected_cards(self):
        """The selected cards, in deck order; not the back"""
        cards = (self.model.index(row, 0).data(CardRole) for row in self.selected_source_rows())
        return [card for card in cards if card is not None]

    def on_card_clicked(self, index):
        if (
            self.is_empty_slot(index)
            and QApplication.keyboardModifiers() == Qt.KeyboardModifier.NoModifier
        ):
            self.choose_image(index)
            return
        card = index.data(CardRole)
        if card and card.default_image():
            self.card_clicked.emit(card.default_image())

    def on_card_activated(self, index):
        if self.is_empty_slot(index):
            self.choose_image(index)
            return
        card = index.data(CardRole)
        if card:
            self.card_action_requested.emit("double_click", card, self.deck)

    def open_selection(self, index):
        """A tab for each selected card, or for the card at index if none is"""
        cards = self.selected_cards() or [index.data(CardRole)]
        for card in cards:
            if card:
                self.card_action_requested.emit("double_click", card, self.deck)

    def on_current_changed(self, current, _previous):
        """Keep the keyboard's card on screen; the page scrolls, not the grid"""
        view = self.current_view()
        if not current.isValid() or current.model() is not view.model():
            return
        rect = view.visualRect(current)
        centre = view.viewport().mapTo(self.scroll.widget(), rect.center())
        margin = units.LARGE_SPACING
        self.scroll.ensureVisible(
            centre.x(), centre.y(), rect.width() // 2 + margin, rect.height() // 2 + margin
        )

    def card_menu(self, index):
        """Open + copy"""
        menu = QMenu(self)
        several = len(self.selected_source_rows()) > 1
        open_action = menu.addAction(
            QIcon.fromTheme("document-open"),
            DECK_VIEW["open_cards"] if several else DECK_VIEW["open_card"],
        )
        open_action.triggered.connect(lambda: self.open_selection(index))
        copy_action = menu.addAction(
            QIcon.fromTheme("edit-copy"),
            DECK_VIEW["copy_cards"] if several else DECK_VIEW["copy_card"],
        )
        copy_action.triggered.connect(self.copy_card)
        canvas_action = menu.addAction(
            QIcon.fromTheme("draw-rectangle"), DECK_VIEW["new_canvas_from_selection"]
        )
        canvas_action.triggered.connect(self.new_canvas_from_selection)
        return menu

    def slot_menu(self, index):
        """Choose Image… on an empty slot; Replace… and Remove, then the card's, on a filled one"""
        if self.is_empty_slot(index):
            menu = QMenu(self)
            choose = menu.addAction(QIcon.fromTheme("list-add"), DECK_VIEW["choose_image"])
            choose.triggered.connect(lambda: self.choose_image(index))
            return menu
        slot = self.slot_id(index)
        menu = self.card_menu(index) if index.data(CardRole) is not None else QMenu(self)
        first = menu.actions()[0] if menu.actions() else None
        replace = QAction(QIcon.fromTheme("document-open"), DECK_VIEW["replace_image"], menu)
        replace.triggered.connect(lambda: self.choose_image(index))
        remove = QAction(QIcon.fromTheme("edit-delete"), DECK_VIEW["remove_card"], menu)
        remove.triggered.connect(lambda: self.editor.unplace(slot))
        menu.insertActions(first, [replace, remove])
        if first is not None:
            menu.insertSeparator(first)
        return menu

    def on_context_menu(self, pos):
        view = self.current_view()
        index = view.indexAt(pos)
        if not self.is_slot(index):
            return
        if not self.editable and index.data(CardRole) is None:
            return
        selection = view.selectionModel()
        if not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        menu = self.slot_menu(index) if self.editable else self.card_menu(index)
        menu.exec(view.viewport().mapToGlobal(pos))
        menu.deleteLater()

    # -- filling a created deck -------------------------------------------

    @staticmethod
    def is_slot(index):
        return index.isValid() and index.data(KindRole) in (KIND_CARD, KIND_BACK)

    def is_empty_slot(self, index):
        if not self.editable or not self.is_slot(index):
            return False
        if index.data(KindRole) == KIND_BACK:
            return not index.data(BackPathRole)
        return not index.data(CardRole).default_image()

    @staticmethod
    def slot_id(index):
        if index.data(KindRole) == KIND_BACK:
            return deck_writer.BACK
        return index.data(CardRole).canonical_id

    def choose_image(self, index):
        slot = self.slot_id(index)
        suffixes = " ".join(f"*{suffix}" for suffix in sorted(deck_writer.image_suffixes()))
        path, _filter = QFileDialog.getOpenFileName(
            self, DECK_VIEW["chooser_title"], "", f"{DECK_VIEW['image_filter']} ({suffixes})"
        )
        if path:
            self.editor.place(slot, path)

    def drop_on_slot(self, index, files):
        """One file fills the slot; more go to Unsorted"""
        if len(files) == 1:
            self.editor.place(self.slot_id(index), files[0])
        else:
            self.send_to_unsorted(files)

    def unsorted_folder(self):
        return (Path(self.deck.root_path) / deck_writer.UNSORTED).resolve()

    def send_to_unsorted(self, files):
        for path in files:
            if Path(path).resolve().parent != self.unsorted_folder():
                self.editor.place_unsorted(path)

    def discard_unsorted(self, name):
        answer = QMessageBox.question(
            self,
            DECK_VIEW["delete_unsorted_title"],
            DECK_VIEW["delete_unsorted_text"].format(name=name),
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.editor.discard_unsorted(name)

    def filled_selected_slots(self):
        view = self.current_view()
        indexes = [
            view.model().mapToSource(index) for index in view.selectionModel().selectedIndexes()
        ]
        return [
            self.slot_id(index)
            for index in indexes
            if self.is_slot(index) and not self.is_empty_slot(index)
        ]

    def unsorted_has_focus(self):
        return self.unsorted is not None and self.unsorted.view.hasFocus()

    def include_minors(self):
        self.minors_offer.button.setEnabled(False)
        self.editor.include_minors()

    def on_write_progress(self, done, total):
        if total <= 0:
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_bar.show()

    def on_write_done(self):
        if not self.editor.is_busy():
            self.progress_bar.hide()
        try:
            deck = deck_library.reload(self.deck_path)
        except Exception:
            log.exception("Could not reload %s", self.deck_path)
            return
        self.set_deck(deck)

    def on_write_failed(self, error):
        log.warning("Could not change %s: %s", self.deck_path, error)
        if isinstance(error, DeckWriteError):
            text = DECK_VIEW[f"write_failed.{error.reason.name.lower()}"].format(
                detail=error.detail
            )
        else:
            text = DECK_VIEW["write_failed_os"].format(error=error)
        self.on_write_done()
        QMessageBox.warning(self, DECK_VIEW["write_failed_title"], text)

    def set_deck(self, deck):
        """Show deck, as reloaded, keeping the current card, the selection and the scroll"""
        view = self.current_view()
        current = view.model().mapToSource(view.currentIndex())
        current_id = self.slot_id(current) if self.is_slot(current) else None
        selected = {
            self.slot_id(self.model.index(row, 0))
            for row in self.selected_source_rows(view)
            if self.is_slot(self.model.index(row, 0))
        }
        scrolled = self.scroll.verticalScrollBar().value()

        self.deck = deck
        self.model.set_deck(deck)

        header = DeckHeader(deck, parent=self.header.parentWidget(), created=self.editable)
        self.content_layout.replaceWidget(self.header, header)
        self.header.deleteLater()
        self.header = header

        rows = {
            self.slot_id(self.model.index(row, 0)): row
            for row in range(self.model.rowCount())
            if self.is_slot(self.model.index(row, 0))
        }
        selection = QItemSelection()
        for slot in selected:
            if slot in rows:
                index = view.model().mapFromSource(self.model.index(rows[slot], 0))
                selection.select(index, index)
        selection_model = view.selectionModel()
        if current_id in rows:
            target = view.model().mapFromSource(self.model.index(rows[current_id], 0))
            selection_model.setCurrentIndex(target, QItemSelectionModel.SelectionFlag.NoUpdate)
        selection_model.select(selection, QItemSelectionModel.SelectionFlag.ClearAndSelect)

        if self.minors_offer is not None:
            self.minors_offer.setVisible(is_majors_only(deck))
            self.minors_offer.button.setEnabled(True)
        if self.unsorted is not None:
            self.unsorted.reload()
        self.tab_label_changed.emit()
        self.edit_state_changed()
        self._scrolled = scrolled
        self._restore_scroll()
        # Once the page is laid out again
        QTimer.singleShot(0, self._restore_scroll)

    def _restore_scroll(self):
        self.scroll.verticalScrollBar().setValue(self._scrolled)

    def new_canvas_from_selection(self):
        cards = self.selected_cards()
        if cards:
            self.new_canvas_requested.emit(cards, self.deck)

    def on_density_changed(self, density):
        self.settings.setValue(DECK_VIEW_DENSITY_KEY, density)
        if self.delegate.set_density(density):
            self.grid.doItemsLayout()
            self.tableau.update_sections()
            if self.unsorted is not None:
                self.unsorted.set_cover_size(self.delegate.cover_size())
        self.zoom_state_changed()

    # -- find ---------------------------------------------------------------

    def can_find(self):
        return self.deck is not None

    def find(self):
        self.search_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_field.selectAll()

    def on_search_changed(self, text):
        self.found.set_find(text)
        self.tableau_model.set_find(text)
        self.edit_state_changed()

    # -- zoom ---------------------------------------------------------------

    def can_zoom(self, how):
        return self.deck is not None and self.zoom_slider.can_zoom(how)

    def zoom(self, how):
        self.zoom_slider.zoom(how)

    # -- edit ---------------------------------------------------------------

    def can_copy_card(self):
        return self.deck is not None and bool(self.selected_cards())

    def can_delete(self):
        if not self.editable:
            return False
        if self.unsorted_has_focus():
            return self.unsorted.current_name() is not None
        return bool(self.filled_selected_slots())

    def delete(self):
        """The selected cards go to Unsorted; with Unsorted focused, its image is deleted"""
        if not self.can_delete():
            return
        if self.unsorted_has_focus():
            self.discard_unsorted(self.unsorted.current_name())
            return
        for slot in self.filled_selected_slots():
            self.editor.unplace(slot)

    def copy_card(self):
        cards = self.selected_cards()
        if cards:
            copy_cards_to_clipboard(cards, self.deck)

    def tab_title(self):
        return self.deck.metadata.name

    def tab_icon(self):
        return deck_icon()


class _SlotDrops(QObject):
    """Local files dropped on a view of a created deck: onto a slot, or anywhere else to Unsorted"""

    def __init__(self, view, tab):
        super().__init__(view)
        self._view = view
        self._tab = tab

    def _target(self, event):
        """(accepted, the slot's index or None)"""
        if not offered_files(event.mimeData()):
            return False, None
        index = self._view.indexAt(event.position().toPoint())
        if self._tab.is_slot(index):
            return True, index
        if index.isValid() and index.data(KindRole) is not None:
            # A heading, label, note or ghost
            return False, None
        return bool(self._tab.unsorted.arriving(event.mimeData())), None

    def _highlight(self, index):
        delegate = self._tab.delegate
        target = QPersistentModelIndex(index) if index is not None else None
        if delegate.drop_target != target:
            delegate.drop_target = target
            self._view.viewport().update()

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            accepted, index = self._target(event)
            self._highlight(index)
            if accepted:
                event.acceptProposedAction()
            else:
                event.ignore()
            return True
        if kind == QEvent.Type.DragLeave:
            self._highlight(None)
            return True
        if kind == QEvent.Type.Drop:
            accepted, index = self._target(event)
            self._highlight(None)
            if not accepted:
                event.ignore()
                return True
            event.acceptProposedAction()
            files = dropped_files(event.mimeData())
            if index is not None:
                self._tab.drop_on_slot(index, files)
            else:
                self._tab.send_to_unsorted(files)
            return True
        return False
