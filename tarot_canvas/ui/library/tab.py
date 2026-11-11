from functools import partial

from PyQt6.QtCore import QSignalBlocker, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.models.deck_manager import deck_manager
from tarot_canvas.settings import (
    LIBRARY_DENSITY_DEFAULT,
    LIBRARY_DENSITY_KEY,
    LIBRARY_DETAILS_BELOW_SHARE_DEFAULT,
    LIBRARY_DETAILS_BELOW_SHARE_KEY,
    LIBRARY_DETAILS_PANE_DEFAULT,
    LIBRARY_DETAILS_PANE_KEY,
    LIBRARY_VIEW_DECKS,
    LIBRARY_VIEW_DEFAULT,
    LIBRARY_VIEW_ESOTERICA,
    LIBRARY_VIEW_KEY,
    LIBRARY_VIEW_NOTES,
    LIBRARY_VIEW_READINGS,
    LIBRARY_VIEW_SPREADS,
    LIBRARY_VIEWS,
    get_settings,
)
from tarot_canvas.ui import commands, units
from tarot_canvas.ui.commands import Scope, set_tooltip_with_keys
from tarot_canvas.ui.icons import LIBRARY_ICON, library_view_icon
from tarot_canvas.ui.library.decks.page import DecksPage
from tarot_canvas.ui.library.esoterica.page import EsotericaPage
from tarot_canvas.ui.library.notes.page import NotesPage
from tarot_canvas.ui.library.readings.page import ReadingsPage
from tarot_canvas.ui.library.spreads.page import SpreadsPage
from tarot_canvas.ui.spread_menu import spread_menu
from tarot_canvas.ui.strings import LIBRARY, MAIN_WINDOW, READINGS, SPREADS, label_for, notes_text
from tarot_canvas.ui.tabs.base_tab import BaseTab
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.widgets.search_field import search_field, step_into_results
from tarot_canvas.ui.widgets.zoom_slider import ZoomSlider


class LibraryTab(BaseTab):
    DETAILS_PANE_MIN_WIDTH = 16 * units.GRID_UNIT
    DETAILS_PANE_SHARE = 0.3  # of the tab's width, the first time it opens beside
    DETAILS_PANE_MIN_HEIGHT = 8 * units.GRID_UNIT
    # A saved share outside this is a dragged-shut pane or a bad value, not a choice to keep
    DETAILS_PANE_BELOW_SHARES = (0.1, 0.9)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = get_settings()
        # Whether selection opens the details pane: False once the user has closed it
        self._details_wanted = self.settings.value(
            LIBRARY_DETAILS_PANE_KEY, LIBRARY_DETAILS_PANE_DEFAULT, type=bool
        )
        # Beside, a width for the session, as the card view keeps its own. Below, a share of
        # the height, saved, so the reading pane is the size it was left at a window ago
        self._details_width = 0
        # Open when a switch landed on a view with nothing to show, so the pane closed for that
        # alone: the next view with something reopens it
        self._details_held = False
        self._below_share = self._saved_below_share()
        # The splitter's sizes while the pane has the list's room, or None while it hasn't
        self._sizes_before_expand = None
        self.setup_ui()

    def setup_ui(self):
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.decks_page = DecksPage()
        self.decks_page.open_requested.connect(self.on_deck_open_requested)
        self.decks_page.details_requested.connect(self._open_details)
        self.decks_page.row_chosen.connect(self._open_details_for_selection)
        self.decks_page.details_changed.connect(self._sync_details_toggle)

        self.notes_page = NotesPage(deck_manager.get_reference_deck())
        self.notes_page.card_activated.connect(self.on_card_activated)
        self.notes_page.note_activated.connect(self.on_note_activated)
        self.notes_page.details_changed.connect(self._sync_details_toggle)

        self.readings_page = ReadingsPage(
            lambda: deck_manager.get_all_decks(), lambda: deck_manager.get_reference_deck()
        )
        self.readings_page.row_chosen.connect(self._open_details_for_selection)
        self.readings_page.open_requested.connect(self.on_reading_open_requested)
        self.readings_page.delete_requested.connect(self.on_reading_delete_requested)
        self.readings_page.rename_requested.connect(self.on_reading_rename_requested)
        self.readings_page.details_pane.expand_requested.connect(self.set_details_expanded)
        self.readings_page.details_pane.card_requested.connect(self.on_reading_card_requested)
        self.readings_page.details_changed.connect(self._on_list_details_changed)

        self.esoterica_page = EsotericaPage(deck=deck_manager.get_reference_deck())
        self.esoterica_page.card_activated.connect(self.on_esoterica_card_activated)
        self.esoterica_page.details_changed.connect(self._sync_details_toggle)
        self.esoterica_page.details_requested.connect(self._open_details)

        self.spreads_page = SpreadsPage()
        self.spreads_page.details_requested.connect(self._open_details)
        self.spreads_page.row_chosen.connect(self._open_details_for_selection)
        self.spreads_page.edit_requested.connect(self.on_spread_edit_requested)
        self.spreads_page.reading_requested.connect(self.on_spread_reading_requested)
        self.spreads_page.duplicate_requested.connect(self.on_spread_duplicate_requested)
        self.spreads_page.delete_requested.connect(self.on_spread_delete_requested)
        self.spreads_page.details_changed.connect(self._on_list_details_changed)

        self.list_pages = {
            LIBRARY_VIEW_DECKS: self.decks_page,
            LIBRARY_VIEW_NOTES: self.notes_page,
            LIBRARY_VIEW_READINGS: self.readings_page,
            LIBRARY_VIEW_ESOTERICA: self.esoterica_page,
            LIBRARY_VIEW_SPREADS: self.spreads_page,
        }

        # One page per sidebar row, in LIBRARY_VIEWS order
        self.pages = QStackedWidget()
        for view in LIBRARY_VIEWS:
            self.pages.addWidget(self.list_pages[view])

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.pages)
        self.splitter.addWidget(self._build_details())
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        # The grid takes a window's growth; the pane keeps the width it was given
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.splitterMoved.connect(self._keep_details_extent)
        self.details_container.hide()

        # [sidebar | header over (seam | splitter)]. The sidebar and header share the window
        # colour, so the seam starts below the header, as the details pane's does
        below_header = QHBoxLayout()
        below_header.setContentsMargins(0, 0, 0, 0)
        below_header.setSpacing(0)
        seam = QFrame()
        seam.setFrameShape(QFrame.Shape.VLine)
        seam.setFrameShadow(QFrame.Shadow.Sunken)
        below_header.addWidget(seam)
        below_header.addWidget(self.splitter, 1)

        content = QWidget()
        content_column = QVBoxLayout(content)
        content_column.setContentsMargins(0, 0, 0, 0)
        content_column.setSpacing(0)
        self.header = self._build_header()
        content_column.addWidget(self.header)
        self.zoom_slider.zoom_on_ctrl_wheel(self.decks_page.list_view.viewport())
        content_column.addLayout(below_header, 1)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(content, 1)
        self.layout.addLayout(body, 1)

        # The sidebar first, so Tab goes from choosing a view to searching it
        QWidget.setTabOrder(self.sidebar, self.search_field)

        commands.bind(
            self,
            Scope.LIBRARY,
            {
                "library.toggle_details": self.details_toggle.click,
                "library.start_reading": self._start_reading,
                "library.rename": self._rename,
                **{
                    f"library.view_{n}": partial(self.show_view, view)
                    for n, view in enumerate(LIBRARY_VIEWS, 1)
                },
            },
        )

        self._restore_settings()
        self.sidebar.currentRowChanged.connect(self.on_view_changed)
        self._sync_details_toggle()

    def _build_header(self):
        header = QWidget()
        row = QHBoxLayout(header)
        row.setContentsMargins(
            units.LARGE_SPACING, units.LARGE_SPACING, units.LARGE_SPACING, units.LARGE_SPACING
        )
        row.setSpacing(units.LARGE_SPACING)

        self.search_field = search_field(LIBRARY["search_decks"])
        self.search_field.textChanged.connect(self.on_search_changed)
        step_into_results(self.search_field, self.focus_first_result)
        row.addWidget(self.search_field, 1)

        self.sort_combo = QComboBox()  # the current view's sorts, filled by _sync_sort_combo
        self.sort_combo.currentIndexChanged.connect(self.on_sort_changed)
        row.addWidget(self.sort_combo)

        self.zoom_slider = ZoomSlider(
            units.DENSITIES, LIBRARY["cover_size"], LIBRARY_DENSITY_DEFAULT
        )
        self.zoom_slider.key_changed.connect(self.on_density_changed)
        row.addWidget(self.zoom_slider)

        # Opens a deck folder where it is; it installs nothing, so not "Add"
        self.open_deck_button = QToolButton()
        self.open_deck_button.setText(LIBRARY["open_deck"])
        # Not document-open, which the details pane's Open uses on the same screen
        self.open_deck_button.setIcon(QIcon.fromTheme("document-open-folder"))
        self.open_deck_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.open_deck_button.clicked.connect(self.browse_for_deck)
        row.addWidget(self.open_deck_button)

        new_spread = commands.by_id("window.new_spread")
        self.new_spread_button = QToolButton()
        self.new_spread_button.setText(new_spread.text)
        self.new_spread_button.setIcon(commands.command_icon(new_spread))
        self.new_spread_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        set_tooltip_with_keys(self.new_spread_button, new_spread.text, new_spread.id)
        self.new_spread_button.clicked.connect(self.on_new_spread)
        row.addWidget(self.new_spread_button)

        self.new_reading_button = QToolButton()
        self.new_reading_button.setText(MAIN_WINDOW["new_reading_from_spread"])
        self.new_reading_button.setIcon(QIcon.fromTheme("media-playback-start"))
        self.new_reading_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.new_reading_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.new_reading_button.setMenu(
            spread_menu(
                self.new_reading_button,
                self.on_spread_reading_requested,
                partial(self.show_view, LIBRARY_VIEW_SPREADS),
                blank=self.on_new_canvas,
            )
        )
        row.addWidget(self.new_reading_button)

        self.details_toggle = QToolButton()
        self.details_toggle.setCheckable(True)
        self.details_toggle.clicked.connect(self.toggle_details_pane)
        row.addWidget(self.details_toggle)

        return header

    def _view_rows(self):
        """(icon, name, view) per sidebar row, in LIBRARY_VIEWS order"""
        names = {
            LIBRARY_VIEW_DECKS: LIBRARY["decks_view"],
            LIBRARY_VIEW_READINGS: READINGS["library_view_name"],
            LIBRARY_VIEW_NOTES: notes_text("view_name"),
            LIBRARY_VIEW_SPREADS: SPREADS["view_name"],
            LIBRARY_VIEW_ESOTERICA: label_for("library.view_name"),
        }
        return [(library_view_icon(view), names[view], view) for view in LIBRARY_VIEWS]

    def _build_sidebar(self):
        """One row per view"""
        self.sidebar = PlacesSidebar(self._view_rows())
        self.sidebar.center_first_row_on(self.header.sizeHint().height())
        return self.sidebar

    def _build_details(self):
        self.details_container = QWidget()
        # Left to right beside the page, top to bottom below it
        self._details_row = row = QBoxLayout(
            QBoxLayout.Direction.LeftToRight, self.details_container
        )
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        # A line for the splitter handle to sit on, as the card view draws it
        self._details_seam = seam = QFrame()
        seam.setFrameShape(QFrame.Shape.VLine)
        seam.setFrameShadow(QFrame.Shadow.Sunken)
        row.addWidget(seam)

        # One splitter slot, one pane per view, swapped by the switcher
        self.detail_panes = QStackedWidget()
        for view in LIBRARY_VIEWS:
            self.detail_panes.addWidget(self.list_pages[view].details_pane)
        row.addWidget(self.detail_panes, 1)

        self.details_container.setMinimumWidth(self.DETAILS_PANE_MIN_WIDTH)
        return self.details_container

    def current_details_pane(self):
        return self.detail_panes.currentWidget()

    def current_list_page(self):
        return self.list_pages[self.current_view()]

    # -- settings ---------------------------------------------------------

    def _restore_settings(self):
        view = self.settings.value(LIBRARY_VIEW_KEY, LIBRARY_VIEW_DEFAULT, type=str)
        if view not in LIBRARY_VIEWS:
            view = LIBRARY_VIEW_DEFAULT
        # Before the sidebar's signal is connected, so restoring writes nothing back
        self.sidebar.setCurrentRow(LIBRARY_VIEWS.index(view))
        self._apply_view(view)

        density = self.settings.value(LIBRARY_DENSITY_KEY, LIBRARY_DENSITY_DEFAULT, type=str)
        self.zoom_slider.set_key(density if density in units.DENSITIES else units.DENSITY_MEDIUM)

        # set_key only emits when the density actually moves, so apply it explicitly
        self.decks_page.set_density(self.zoom_slider.key())

    # -- the sidebar ------------------------------------------------------

    def current_view(self):
        row = self.sidebar.currentRow()
        return LIBRARY_VIEWS[row] if 0 <= row < len(LIBRARY_VIEWS) else LIBRARY_VIEW_DEFAULT

    def show_view(self, view):
        if view in LIBRARY_VIEWS:
            self.sidebar.setCurrentRow(LIBRARY_VIEWS.index(view))

    def on_view_changed(self, _row):
        view = self.current_view()
        self._apply_view(view)
        self.settings.setValue(LIBRARY_VIEW_KEY, view)

    def _apply_view(self, view):
        # Expanding is for reading one entry; another view gets its list back
        self.set_details_expanded(False)
        page = self.list_pages[view]
        decks = view == LIBRARY_VIEW_DECKS
        was_open = self.details_pane_is_open() or self._details_held
        self.pages.setCurrentIndex(LIBRARY_VIEWS.index(view))
        self.detail_panes.setCurrentIndex(LIBRARY_VIEWS.index(view))
        # One pane slot serves every view, so an open pane must not carry over to a view with
        # nothing selected, where it would open empty
        has_details = self.current_details_pane().details() is not None
        self._details_held = was_open and not has_details
        if not has_details:
            # Before the turn, so the extent kept is the one this pane had in its own view
            self._set_details_open(False)
        self._orient_details(
            Qt.Orientation.Horizontal if page.DETAILS_BESIDE else Qt.Orientation.Vertical
        )
        if was_open and has_details:
            self._set_details_open(True)

        self._sync_sort_combo(page)
        self.zoom_slider.setVisible(decks)
        self.open_deck_button.setVisible(decks)
        self.new_spread_button.setVisible(view == LIBRARY_VIEW_SPREADS)
        self.new_reading_button.setVisible(view == LIBRARY_VIEW_READINGS)
        self.search_field.setPlaceholderText(page.search_placeholder())

        # Each view searches its own content, so the field starts clean on a switch
        self.search_field.clear()
        self._sync_details_toggle()

    def _sync_sort_combo(self, page):
        choices = page.sort_choices()
        tooltip = page.sort_tooltip() if choices else ""
        current = page.sort_key() if choices else None

        # Refilling is no change of sort
        with QSignalBlocker(self.sort_combo):
            self.sort_combo.clear()
            for label, key in choices:
                self.sort_combo.addItem(label, key)
            self.sort_combo.setCurrentIndex(self.sort_combo.findData(current))
        self.sort_combo.setToolTip(tooltip)
        self.sort_combo.setVisible(bool(choices))

    # -- slots ------------------------------------------------------------

    def can_find(self):
        return True

    def find(self):
        self.search_field.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_field.selectAll()

    def focus_first_result(self):
        """From the search field onto the first result, selected"""
        return self.current_list_page().focus_first_row()

    def on_search_changed(self, text):
        # A search is for the list, so the list comes back
        self.set_details_expanded(False)
        self.current_list_page().set_search(text)

    def on_card_activated(self, card_id):
        """Open the card view for a note's card, on its Notes tab."""
        return self._open_card_view(card_id, show_notes=True)

    def on_esoterica_card_activated(self, card_id):
        """Open the card view for a source's covered card, on its Esoterica tab."""
        card_tab = self._open_card_view(card_id)
        if card_tab is not None:
            card_tab.show_esoterica_tab()

    def _open_card_view(self, card_id, show_notes=False):
        deck = deck_manager.get_reference_deck()
        card = deck.get_card_by_id(card_id) if deck else None
        if card is None:
            return None

        main_window = self.window()
        if hasattr(main_window, "open_card_view_tab"):
            return main_window.open_card_view_tab(card, deck, show_notes=show_notes)
        return None

    def on_note_activated(self, card_id, path):
        """Open the card view on one note."""
        card_tab = self.on_card_activated(card_id)
        if card_tab is not None:
            card_tab.open_note(path)

    def on_spread_edit_requested(self, path):
        main_window = self.window()
        if hasattr(main_window, "open_spread"):
            main_window.open_spread(path)

    def on_spread_reading_requested(self, path):
        main_window = self.window()
        if hasattr(main_window, "open_reading"):
            main_window.open_reading(path)

    def on_spread_duplicate_requested(self, path):
        main_window = self.window()
        if hasattr(main_window, "duplicate_spread"):
            main_window.duplicate_spread(path)

    def on_new_spread(self):
        main_window = self.window()
        if hasattr(main_window, "new_spread_tab"):
            main_window.new_spread_tab()

    def on_new_canvas(self):
        main_window = self.window()
        if hasattr(main_window, "new_canvas_tab"):
            main_window.new_canvas_tab()

    def on_spread_delete_requested(self, path):
        """Delete a spread once any tab holding it has closed, which may ask the user"""
        main_window = self.window()
        if hasattr(main_window, "close_spread"):
            if not main_window.close_spread(path):
                return
            # Where the Undo is
            main_window.tab_widget.setCurrentWidget(self)
        self.spreads_page.delete(path)

    def on_reading_open_requested(self, path):
        main_window = self.window()
        if hasattr(main_window, "open_saved_reading"):
            main_window.open_saved_reading(path)

    def on_reading_card_requested(self, card, deck):
        """A card the reading names, in the deck the reading opens it in"""
        main_window = self.window()
        if hasattr(main_window, "open_card_view_tab"):
            main_window.open_card_view_tab(card, deck)

    def on_reading_rename_requested(self, path, question):
        main_window = self.window()
        if hasattr(main_window, "rename_saved_reading"):
            main_window.rename_saved_reading(path, question)

    def on_reading_delete_requested(self, path):
        """Delete a reading once any tab holding it has closed and written itself"""
        main_window = self.window()
        if hasattr(main_window, "close_saved_reading"):
            if not main_window.close_saved_reading(path):
                return
            # Where the Undo is
            main_window.tab_widget.setCurrentWidget(self)
        self.readings_page.delete(path)

    def _on_list_details_changed(self):
        if self.current_details_pane().details() is None:
            self._set_details_open(False)
        self._sync_details_toggle()

    def about_to_close(self):
        # Its Undo goes with the tab
        self.spreads_page.commit_pending_delete()
        self.readings_page.commit_pending_delete()

    def on_sort_changed(self):
        self.current_list_page().set_sort_key(self.sort_combo.currentData())

    def on_density_changed(self, density):
        self.decks_page.set_density(density)
        self.settings.setValue(LIBRARY_DENSITY_KEY, density)
        self.zoom_state_changed()

    # -- zoom ---------------------------------------------------------------

    def can_zoom(self, how):
        return self.zoom_slider.isVisibleTo(self) and self.zoom_slider.can_zoom(how)

    def zoom(self, how):
        self.zoom_slider.zoom(how)

    def _open_details(self):
        """Open the pane even if the user closed it: they asked for this row's details"""
        self._set_details_open(True)

    # -- the details pane -------------------------------------------------

    def _start_reading(self):
        if self.pages.currentWidget() is self.spreads_page:
            self.spreads_page.start_reading()

    def _rename(self):
        if self.pages.currentWidget() is self.readings_page:
            self.readings_page.rename_selected()

    def can_delete(self):
        return (
            self.pages.currentWidget() is self.readings_page
            and self.readings_page.can_delete_selected()
        )

    def delete(self):
        if self.can_delete():
            self.readings_page.delete_selected()

    def details_pane_is_open(self):
        return not self.details_container.isHidden()

    def toggle_details_pane(self):
        """The one control that closes the pane, so a close here is remembered"""
        want = not self.details_pane_is_open()
        if want and self.current_details_pane().details() is None:
            return
        self._details_wanted = want
        self._details_held = False
        self.settings.setValue(LIBRARY_DETAILS_PANE_KEY, want)
        self._set_details_open(want)

    def _open_details_for_selection(self):
        if self._details_wanted:
            self._set_details_open(True)

    def details_pane_is_expanded(self):
        return self._sizes_before_expand is not None

    def set_details_expanded(self, want):
        """Give the open pane the list's room, or give it back where the divider was"""
        pane = self.current_details_pane()
        want = want and self.details_pane_is_open() and hasattr(pane, "set_expanded")
        if want == self.details_pane_is_expanded():
            return
        if want:
            # The list can't collapse to nothing, so it goes, and its divider is kept
            self._sizes_before_expand = self.splitter.sizes()
            self.pages.hide()
        else:
            sizes, self._sizes_before_expand = self._sizes_before_expand, None
            self.pages.show()
            self.splitter.setSizes(sizes)
        for each in self.list_pages.values():
            if hasattr(each.details_pane, "set_expanded"):
                each.details_pane.set_expanded(want and each.details_pane is pane)

    def _set_details_open(self, want):
        if not want:
            # Before its extent is kept, so the extent is the one beside the list
            self.set_details_expanded(False)
        if want != self.details_pane_is_open():
            if want:
                self.details_container.show()
                self._size_details()
            else:
                self._keep_details_extent()
                self.details_container.hide()
        self._sync_details_toggle()

    def details_pane_is_below(self):
        return self.splitter.orientation() == Qt.Orientation.Vertical

    def _orient_details(self, orientation):
        """Put the pane beside the page or below it, each at the size it last had"""
        if orientation == self.splitter.orientation():
            return
        is_open = self.details_pane_is_open()
        if is_open:
            self._keep_details_extent()
        self.splitter.setOrientation(orientation)
        below = self.details_pane_is_below()
        self._details_row.setDirection(
            QBoxLayout.Direction.TopToBottom if below else QBoxLayout.Direction.LeftToRight
        )
        self._details_seam.setFrameShape(QFrame.Shape.HLine if below else QFrame.Shape.VLine)
        # Below, the list and the pane share a window's growth; beside, the grid takes it all
        self.splitter.setStretchFactor(1, 1 if below else 0)
        if below:
            self.details_container.setMinimumSize(0, self.DETAILS_PANE_MIN_HEIGHT)
        else:
            self.details_container.setMinimumSize(self.DETAILS_PANE_MIN_WIDTH, 0)
        if is_open:
            self._size_details()

    def _keep_details_extent(self, *_moved):
        """Remember the open pane's size: its width beside, its share of the height below"""
        if not self.details_pane_is_open():
            return
        page, pane = self.splitter.sizes()
        if not pane:
            return
        if not self.details_pane_is_below():
            self._details_width = pane
            return
        share = pane / (page + pane)
        low, high = self.DETAILS_PANE_BELOW_SHARES
        if low <= share <= high and share != self._below_share:
            self._below_share = share
            self.settings.setValue(LIBRARY_DETAILS_BELOW_SHARE_KEY, share)

    def _saved_below_share(self):
        try:
            share = self.settings.value(
                LIBRARY_DETAILS_BELOW_SHARE_KEY, LIBRARY_DETAILS_BELOW_SHARE_DEFAULT, type=float
            )
        except TypeError:  # a value that isn't a number at all
            return LIBRARY_DETAILS_BELOW_SHARE_DEFAULT
        low, high = self.DETAILS_PANE_BELOW_SHARES
        return share if low <= share <= high else LIBRARY_DETAILS_BELOW_SHARE_DEFAULT

    def _size_details(self):
        """Give the open pane its remembered size, or its share of the tab the first time"""
        below = self.details_pane_is_below()
        total = (self.splitter.height() if below else self.splitter.width()) - (
            self.splitter.handleWidth()
        )
        if below:
            extent = round(total * self._below_share)
        else:
            extent = self._details_width or round(total * self.DETAILS_PANE_SHARE)
        self.splitter.setSizes([max(0, total - extent), extent])

    def _sync_details_toggle(self):
        """Keep the toggle saying what the next press will do"""
        is_open = self.details_pane_is_open()
        # Disabled until there's something to show, so the pane never opens empty
        self.details_toggle.setEnabled(self.current_details_pane().details() is not None)
        self.details_toggle.setChecked(is_open)
        if self.details_pane_is_below():
            # Breeze has no bottom-panel pair, so the checked state says whether it's open
            icon = "view-split-top-bottom"
        else:
            icon = "sidebar-collapse-right" if is_open else "sidebar-expand-right"
        self.details_toggle.setIcon(QIcon.fromTheme(icon))
        tooltip = self.current_list_page().details_toggle_tooltip(is_open)
        set_tooltip_with_keys(self.details_toggle, tooltip, "library.toggle_details")

    def on_deck_open_requested(self, deck):
        """Open the deck in a new tab."""
        main_window = self.window()
        if hasattr(main_window, "new_deck_view_tab"):
            main_window.new_deck_view_tab(deck_path=deck.deck_path)

    def browse_for_deck(self):
        """Open file dialog to browse for additional decks"""
        main_window = self.window()
        if hasattr(main_window, "open_deck"):
            main_window.open_deck()

    def tab_title(self):
        return LIBRARY["tab_title"]

    def tab_icon(self):
        return QIcon.fromTheme(LIBRARY_ICON)
