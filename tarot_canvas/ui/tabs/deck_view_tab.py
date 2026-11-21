import logging
import os

from PyQt6.QtCore import QItemSelectionModel, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMenu,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models import library_curation
from tarot_canvas.models.deck_library import deck_library
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
from tarot_canvas.ui.deck_view.card_model import CardFilter, CardModel, CardRole, is_slot
from tarot_canvas.ui.deck_view.deck_editor import DeckEditor
from tarot_canvas.ui.deck_view.exporter import DeckExporter
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.deck_view.selection_snapshot import SelectionSnapshot
from tarot_canvas.ui.deck_view.tableau_model import TableauModel
from tarot_canvas.ui.deck_view.tableau_view import TableauView
from tarot_canvas.ui.icons import deck_icon
from tarot_canvas.ui.library.decks import header as deck_header
from tarot_canvas.ui.library.decks.handmade_header import HandmadeDeckHeader
from tarot_canvas.ui.library.decks.header import DeckHeader
from tarot_canvas.ui.strings import DECK_VIEW
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets.inline_message import InlineMessage
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
    message = pyqtSignal(str)  # for a toast
    install_requested = pyqtSignal(str)  # the .tarotdeck a temporary deck came from
    open_deck_requested = pyqtSignal(str)  # a deck root

    def __init__(self, deck_path, parent=None, origin=None):
        super().__init__(parent)
        self.deck_path = deck_path
        # The .tarotdeck this deck was unpacked from, when it is outside the Library
        self.origin = origin
        self.banner = None
        self.mode = None
        self.editor = None  # a DeckEditor, for a handmade deck
        self.exporter = None
        self.settings = get_settings()
        self._build(deck_library.load(deck_path))

    @property
    def deck(self):
        return self.model.deck

    def _build(self, deck):
        self.editable = library_curation.is_handmade(deck.root_path)

        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        # Pinned above the page, as the Library's is
        self.layout.addWidget(self._build_header())
        if self.origin is not None:
            self.layout.addLayout(self._build_banner(deck))

        # Main content widget with vertical layout
        content = QWidget()
        main_layout = QVBoxLayout(content)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Deck-level header at the top of the page
        header_class = HandmadeDeckHeader if self.editable else DeckHeader
        self.header = header_class(deck, parent=content)
        main_layout.addWidget(self.header)

        # The grid's own spacing makes up the rest of the margin, so headings line up
        # with the header's text
        grid_row = QVBoxLayout()
        self.grid = self._build_grid(deck)
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

        self.scroll = scroll = QScrollArea()
        if self.editable:
            self.editor = DeckEditor(
                deck, self.delegate, [self.grid, self.tableau], scroll, self.current_view, self
            )
            self.editor.progress.connect(self.on_write_progress)
            self.editor.written.connect(self.on_written)
            self.editor.edit_state_changed.connect(self.edit_state_changed)
            unsorted_row = QHBoxLayout()
            unsorted_row.setContentsMargins(self.grid.spacing(), 0, self.grid.spacing(), 0)
            unsorted_row.addWidget(self.editor.unsorted)
            grid_row.addLayout(unsorted_row)
            self.header.fields_edited.connect(self.on_fields_edited)
            self.header.add_images_requested.connect(self.editor.add_images)
            self.header.cards_chosen.connect(self.on_cards_chosen)
            self.header.put_back_requested.connect(self.editor.queue.include_all)
            self.exporter = DeckExporter(self.editor.queue, lambda: self.deck, self)
            self.exporter.message.connect(self.message)
            self.exporter.running_changed.connect(self.update_export_button)
            self.editor.queue.busy_changed.connect(self.update_export_button)
            self.header.export_requested.connect(self.exporter.start)
            self.update_export_button()
        main_layout.addLayout(grid_row)
        main_layout.addStretch()

        # Add the content to a scroll area
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

    def _build_banner(self, deck):
        """Says the deck is outside the Library, with no close: it holds the only way in"""
        row = QVBoxLayout()
        row.setContentsMargins(SECTION_MARGIN, 0, SECTION_MARGIN, units.LARGE_SPACING)
        self.banner = InlineMessage(parent=self, closable=False)
        row.addWidget(self.banner)

        file = os.path.basename(os.fspath(self.origin))
        identifier = deck.metadata.identifier
        installed = deck_library.find_by_identifier(identifier) if identifier else ()
        if installed:
            self.banner_action = QAction(
                QIcon.fromTheme("document-open"), DECK_VIEW["open_library_copy"], self
            )
            root = os.fspath(installed[0].root_path)
            self.banner_action.triggered.connect(lambda: self.open_deck_requested.emit(root))
            text = DECK_VIEW["temporary_installed"].format(file=file)
        else:
            self.banner_action = QAction(
                QIcon.fromTheme("list-add"), DECK_VIEW["add_to_library"], self
            )
            self.banner_action.triggered.connect(self.request_install)
            text = DECK_VIEW["temporary"].format(file=file)
        self.banner.show_message(text, [self.banner_action])
        return row

    def request_install(self):
        self.banner_action.setEnabled(False)
        self.install_requested.emit(os.fspath(self.origin))

    def install_finished(self):
        """The install failed; the deck can be offered again"""
        self.banner_action.setEnabled(True)

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

    def _build_grid(self, deck):
        self.model = CardModel(deck, self, editable=self.editable)
        # The grid shows what Find leaves of the deck
        self.found = CardFilter(self)
        self.found.setSourceModel(self.model)
        grid = SectionsView()
        grid.setModel(self.found)
        self.delegate = CardDelegate(grid, density=self.zoom_slider.key(), editable=self.editable)
        if self.editable:
            self.delegate.set_slot_shape(deck)
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
        SelectionSnapshot.take(old).restore(new)
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
        if self.editor is not None and self.editor.click(index):
            return
        card = index.data(CardRole)
        if card and card.default_image():
            self.card_clicked.emit(card.default_image())

    def on_card_activated(self, index):
        if self.editor is not None and self.editor.activate(index):
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

    def menu_for(self, index):
        """The context menu for the card or slot at index"""
        if self.editor is not None:
            return self.editor.slot_menu(index, self.card_menu)
        return self.card_menu(index)

    def on_context_menu(self, pos):
        view = self.current_view()
        index = view.indexAt(pos)
        if not is_slot(index):
            return
        if self.editor is None and index.data(CardRole) is None:
            return
        selection = view.selectionModel()
        if not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        menu = self.menu_for(index)
        menu.exec(view.viewport().mapToGlobal(pos))
        menu.deleteLater()

    # -- a handmade deck's writes --------------------------------------------

    def on_write_progress(self, done, total):
        if total <= 0:
            return
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_bar.show()

    def on_written(self):
        if not self.editor.is_busy():
            self.progress_bar.hide()
        try:
            deck = deck_library.reload(self.deck_path)
        except Exception:
            log.exception("Could not reload %s", self.deck_path)
            return
        self.set_deck(deck)

    def set_deck(self, deck):
        """Show deck, as reloaded, keeping the current card, the selection and the scroll"""
        view = self.current_view()
        snapshot = SelectionSnapshot.take(view)
        scrolled = self.scroll.verticalScrollBar().value()

        self.model.set_deck(deck)

        if self.editable:
            self.delegate.set_slot_shape(deck)
            # Rebuilt, it would take the focus from an editor being typed in
            self.header.update_from(deck)
        else:
            page = self.header.parentWidget()
            header = DeckHeader(deck, parent=page)
            page.layout().replaceWidget(self.header, header)
            self.header.deleteLater()
            self.header = header

        snapshot.restore(view)
        if self.editor is not None:
            self.editor.set_deck(deck)
        self.tab_label_changed.emit()
        self.edit_state_changed()
        self._scrolled = scrolled
        self._restore_scroll()
        # Once the page is laid out again
        QTimer.singleShot(0, self._restore_scroll)

    def _restore_scroll(self):
        self.scroll.verticalScrollBar().setValue(self._scrolled)

    def on_fields_edited(self, fields):
        self.editor.queue.set_fields(**fields)

    def update_export_button(self, *_):
        self.header.export_button.setEnabled(
            not self.editor.is_busy() and not self.exporter.running
        )

    def on_cards_chosen(self, whole):
        if whole:
            self.editor.queue.include_minors()
        else:
            self.editor.queue.exclude_minors()

    def new_canvas_from_selection(self):
        cards = self.selected_cards()
        if cards:
            self.new_canvas_requested.emit(cards, self.deck)

    def on_density_changed(self, density):
        self.settings.setValue(DECK_VIEW_DENSITY_KEY, density)
        if self.delegate.set_density(density):
            self.grid.doItemsLayout()
            self.tableau.update_sections()
            if self.editor is not None:
                self.editor.set_cover_size(self.delegate.cover_size())
        self.zoom_state_changed()

    # -- find ---------------------------------------------------------------

    def can_find(self):
        return True

    def find(self):
        self.search_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_field.selectAll()

    def on_search_changed(self, text):
        self.found.set_find(text)
        self.tableau_model.set_find(text)
        self.edit_state_changed()

    # -- zoom ---------------------------------------------------------------

    def can_zoom(self, how):
        return self.zoom_slider.can_zoom(how)

    def zoom(self, how):
        self.zoom_slider.zoom(how)

    # -- edit ---------------------------------------------------------------

    def can_copy_card(self):
        return bool(self.selected_cards())

    def can_delete(self):
        return self.editor is not None and self.editor.can_delete()

    def delete(self):
        if self.editor is not None:
            self.editor.delete()

    def about_to_close(self):
        # Its Undo goes with the tab
        if self.editor is not None:
            self.editor.commit_pending_delete()

    def copy_card(self):
        cards = self.selected_cards()
        if cards:
            copy_cards_to_clipboard(cards, self.deck)

    def tab_title(self):
        return self.deck.metadata.name

    def tab_icon(self):
        return deck_icon()
