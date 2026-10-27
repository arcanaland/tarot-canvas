from PyQt6.QtCore import QItemSelection, QItemSelectionModel, QModelIndex, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck import TarotDeck
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
from tarot_canvas.ui.activate_on_return import activate_on_return
from tarot_canvas.ui.card_transfer import copy_cards_to_clipboard
from tarot_canvas.ui.deck_view import view_text
from tarot_canvas.ui.deck_view.card_delegate import CardDelegate
from tarot_canvas.ui.deck_view.card_model import CardFilter, CardModel, CardRole
from tarot_canvas.ui.deck_view.sections_view import SectionsView
from tarot_canvas.ui.deck_view.tableau_model import TableauModel
from tarot_canvas.ui.deck_view.tableau_view import TableauView
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets import deck_header
from tarot_canvas.ui.widgets.deck_header import DeckHeader
from tarot_canvas.ui.widgets.search_field import search_field
from tarot_canvas.ui.widgets.zoom_slider import ZoomSlider

SECTION_MARGIN = deck_header.EDGE_MARGIN
FIND_CARD_PLACEHOLDER = "Find card…"
NEW_CANVAS_FROM_SELECTION = "Create New Canvas From Selection"

VIEW_ICONS = {
    DECK_VIEW_MODE_SECTIONS: "view-list-icons",
    DECK_VIEW_MODE_TABLEAU: "table",
}


class DeckViewTab(BaseTab):
    card_clicked = pyqtSignal(str)  # Signal when a card is clicked
    card_action_requested = pyqtSignal(
        str, dict, object
    )  # Signal for card actions (action, card, deck)
    title_changed = pyqtSignal(str)  # Signal to update the tab title
    new_canvas_requested = pyqtSignal(list, object)  # cards, deck

    def __init__(self, deck_path=None, parent=None):
        super().__init__(parent)
        self.deck_path = deck_path
        self.deck = None
        self.mode = None
        self.settings = get_settings()
        self.setup_ui()

        # Set the tab icon after a short delay to ensure the tab is added
        QTimer.singleShot(100, self.update_tab_icon)

    def setup_ui(self):
        if self.deck_path:
            # Load deck from deck_path
            self.load_deck(self.deck_path)
        else:
            self.set_placeholder("Open a deck to view its cards")

    def load_deck(self, deck_path):
        self.clear_layout()

        # Load the deck
        self.deck = TarotDeck(deck_path)

        # Get the parent tab widget to update its title directly
        parent_tab_widget = None
        parent = self.parent()
        while parent:
            if isinstance(parent, QTabWidget):
                parent_tab_widget = parent
                break
            parent = parent.parent()

        # Directly update the tab title if we can find the parent tab widget
        if parent_tab_widget:
            tab_index = parent_tab_widget.indexOf(self)
            if tab_index != -1:
                parent_tab_widget.setTabText(tab_index, self.deck.get_name())
                print(f"Direct title update: {self.deck.get_name()}")

        # Also emit the signal as a backup mechanism
        self.title_changed.emit(self.deck.get_name())

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
        self.header = DeckHeader(self.deck, parent=content)
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

    def _build_header(self):
        header = QWidget()
        row = QHBoxLayout(header)
        # Level with the banner's text and the headings
        row.setContentsMargins(
            SECTION_MARGIN, units.LARGE_SPACING, SECTION_MARGIN, units.LARGE_SPACING
        )
        row.setSpacing(units.LARGE_SPACING)

        self.search_field = search_field(FIND_CARD_PLACEHOLDER)
        self.search_field.textChanged.connect(self.on_search_changed)
        row.addWidget(self.search_field, 1)

        self.zoom_slider = ZoomSlider(units.DENSITIES, "Cover size", DECK_VIEW_DENSITY_DEFAULT)
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
        bar.setAccessibleName(view_text.VIEW_BAR_NAME)
        buttons = QHBoxLayout(bar)
        buttons.setContentsMargins(0, 0, 0, 0)
        buttons.setSpacing(0)

        self.view_group = QButtonGroup(bar)
        self.view_group.setExclusive(True)
        self.view_buttons = {}
        names = {
            DECK_VIEW_MODE_SECTIONS: (view_text.SECTIONS_NAME, view_text.SECTIONS_TOOLTIP),
            DECK_VIEW_MODE_TABLEAU: (view_text.TABLEAU_NAME, view_text.TABLEAU_TOOLTIP),
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
        self.model = CardModel(self.deck, self)
        # The grid shows what Find leaves of the deck
        self.found = CardFilter(self)
        self.found.setSourceModel(self.model)
        grid = SectionsView()
        grid.setModel(self.found)
        self.delegate = CardDelegate(grid, density=self.zoom_slider.key())
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
        """The selected cards, in deck order"""
        return [self.model.index(row, 0).data(CardRole) for row in self.selected_source_rows()]

    def on_card_clicked(self, index):
        card = index.data(CardRole)
        if card and card.get("image"):
            self.card_clicked.emit(card.get("image"))

    def on_card_activated(self, index):
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
            QIcon.fromTheme("document-open"), "&Open Cards" if several else "&Open Card"
        )
        open_action.triggered.connect(lambda: self.open_selection(index))
        copy_action = menu.addAction(
            QIcon.fromTheme("edit-copy"), "&Copy Cards" if several else "&Copy Card"
        )
        copy_action.triggered.connect(self.copy_card)
        canvas_action = menu.addAction(QIcon.fromTheme("draw-rectangle"), NEW_CANVAS_FROM_SELECTION)
        canvas_action.triggered.connect(self.new_canvas_from_selection)
        return menu

    def on_context_menu(self, pos):
        view = self.current_view()
        index = view.indexAt(pos)
        if not index.isValid() or index.data(CardRole) is None:
            return
        selection = view.selectionModel()
        if not selection.isSelected(index):
            selection.setCurrentIndex(index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        menu = self.card_menu(index)
        menu.exec(view.viewport().mapToGlobal(pos))
        menu.deleteLater()

    def new_canvas_from_selection(self):
        cards = self.selected_cards()
        if cards:
            self.new_canvas_requested.emit(cards, self.deck)

    def on_density_changed(self, density):
        self.settings.setValue(DECK_VIEW_DENSITY_KEY, density)
        if self.delegate.set_density(density):
            self.grid.doItemsLayout()
            self.tableau.update_sections()
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
        return self.deck is not None and self.current_view().selectionModel().hasSelection()

    def copy_card(self):
        cards = self.selected_cards()
        if cards:
            copy_cards_to_clipboard(cards, self.deck)

    def clear_layout(self):
        """Clear the current layout"""
        while self.layout.count():
            item = self.layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def update_tab_icon(self):
        """Update the tab with a deck icon"""
        parent = self.parent()
        if parent:
            # Find the tab widget that contains this widget
            tab_widget = None
            parent_widget = parent

            # Try to find a parent that has setTabIcon method
            while parent_widget and not tab_widget:
                if hasattr(parent_widget, "setTabIcon"):
                    tab_widget = parent_widget
                    break
                parent_widget = parent_widget.parent()

            # If we found a tab widget, update the tab icon
            if tab_widget:
                index = tab_widget.indexOf(self)
                if index >= 0:
                    tab_widget.setTabIcon(index, QIcon.fromTheme("view-grid"))
