import contextlib
import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget

from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.card_transfer import deck_path_key
from tarot_canvas.ui.library import units
from tarot_canvas.ui.tabs.card_view.headings import SECTION_SCALE, TITLE_SCALE, apply_heading
from tarot_canvas.ui.tabs.card_view.notes_section import NotesSection


def _disconnect_on_destroy(connection):
    """A callable that drops `connection`, holding the connection and nothing else.

    It must not close over the widget: a closure keeping the receiver alive is the leak
    this exists to prevent.
    """

    def disconnect(_object=None):
        with contextlib.suppress(RuntimeError, TypeError):
            note_events().notes_changed.disconnect(connection)

    return disconnect


class OverviewTab(QWidget):
    """Tab displaying overview information about a tarot card"""

    def __init__(self, card=None, deck=None, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.card = card
        self.deck = deck

        # Create properties for both minor arcana and major arcana to avoid
        # having to recreate UI when switching between card types
        self.name_label = None
        self.id_label = None
        self.type_value = None
        self.deck_value = None
        self.info_frame = None
        self.info_grid = None

        # Minor arcana specific
        self.suit_label = None
        self.suit_value = None
        self.rank_label = None
        self.rank_value = None

        # Major arcana specific
        self.number_label = None
        self.number_value = None

        # Description
        self.description_header = None
        self.description_label = None

        # Notes
        self.notes_section = None

        self.setup_ui()

    def setup_ui(self):
        """Set up the overview tab UI"""
        layout = QVBoxLayout(self)
        # The HIG's spacing table: 0 between a title and its subtitle, smallSpacing from
        # a heading to the content under it, largeSpacing between groups. Set here rather
        # than left to the style's default, which is one gap for all three cases.
        layout.setSpacing(0)

        if not self.card:
            layout.addWidget(QLabel("No card information available"))
            return

        # Card name at the top
        self.name_label = QLabel(self.card["name"])
        apply_heading(self.name_label, TITLE_SCALE)
        self.name_label.setObjectName("name_label")
        layout.addWidget(self.name_label)

        # Card ID below name
        self.id_label = QLabel(f"ID: {self.card['id']}")
        self.id_label.setStyleSheet("color: gray;")
        self.id_label.setObjectName("id_label")
        layout.addWidget(self.id_label)

        # Create a grid for structured information
        self.info_grid = QGridLayout()
        self.info_grid.setVerticalSpacing(8)
        self.info_grid.setHorizontalSpacing(12)
        self.info_grid.setColumnStretch(1, 1)  # Make value column expandable

        # Add a frame around the structured info
        self.info_frame = QFrame()
        self.info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.info_frame.setFrameShadow(QFrame.Shadow.Sunken)
        self.info_frame.setStyleSheet("background-color: rgba(0, 0, 0, 0.03);")
        self.info_frame.setLayout(self.info_grid)

        # Add card type (always present)
        type_label = QLabel("Type:")
        type_label.setStyleSheet("font-weight: bold;")
        type_label.setObjectName("type_label")
        self.type_value = QLabel(self.card["type"].replace("_", " ").title())
        self.type_value.setObjectName("type_value")
        self.info_grid.addWidget(type_label, 0, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.type_value, 0, 1, Qt.AlignmentFlag.AlignTop)

        # Create all possible fields for both card types, hide the ones we don't need

        # Create suit and rank fields (for minor arcana)
        self.suit_label = QLabel("Suit:")
        self.suit_label.setStyleSheet("font-weight: bold;")
        self.suit_label.setObjectName("suit_label")
        self.suit_value = QLabel()
        self.suit_value.setObjectName("suit_value")
        self.info_grid.addWidget(self.suit_label, 1, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.suit_value, 1, 1, Qt.AlignmentFlag.AlignTop)

        self.rank_label = QLabel("Rank:")
        self.rank_label.setStyleSheet("font-weight: bold;")
        self.rank_label.setObjectName("rank_label")
        self.rank_value = QLabel()
        self.rank_value.setObjectName("rank_value")
        self.info_grid.addWidget(self.rank_label, 2, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.rank_value, 2, 1, Qt.AlignmentFlag.AlignTop)

        # Create number field (for major arcana)
        self.number_label = QLabel("Number:")
        self.number_label.setStyleSheet("font-weight: bold;")
        self.number_label.setObjectName("number_label")
        self.number_value = QLabel()
        self.number_value.setObjectName("number_value")
        self.info_grid.addWidget(self.number_label, 3, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.number_value, 3, 1, Qt.AlignmentFlag.AlignTop)

        # Add deck (always present)
        deck_label = QLabel("Deck:")
        deck_label.setStyleSheet("font-weight: bold;")
        deck_label.setObjectName("deck_label")
        self.deck_value = QLabel()
        self.deck_value.setObjectName("deck_value")
        self.update_deck_link()  # Set the deck link
        self.deck_value.setTextFormat(Qt.TextFormat.RichText)
        self.deck_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.deck_value.setOpenExternalLinks(False)
        self.deck_value.linkActivated.connect(self.on_deck_link_clicked)
        self.info_grid.addWidget(deck_label, 4, 0, Qt.AlignmentFlag.AlignTop)
        self.info_grid.addWidget(self.deck_value, 4, 1, Qt.AlignmentFlag.AlignTop)

        # Add the frame to the layout with some spacing
        layout.addSpacing(units.LARGE_SPACING)
        layout.addWidget(self.info_frame)
        layout.addSpacing(units.LARGE_SPACING)

        # A heading over a block of prose, not a label in front of a control: the HIG
        # gives the trailing colon to the latter, which is what the Type/Suit/Deck rows
        # in the frame above are. Title case, no colon, and a heading's size.
        self.description_header = QLabel("Description")
        apply_heading(self.description_header, SECTION_SCALE)
        self.description_header.setObjectName("description_header")
        layout.addWidget(self.description_header)
        layout.addSpacing(units.SMALL_SPACING)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description_label.setObjectName("description_label")
        layout.addWidget(self.description_label)

        # The notes section sits under the description and above the stretch, so it is
        # the last thing on the card and doesn't displace what was already here.
        layout.addSpacing(units.LARGE_SPACING)
        self.notes_section = NotesSection(self)
        self.notes_section.noteActivated.connect(self.on_note_activated)
        self.notes_section.createRequested.connect(self.on_create_note)
        layout.addWidget(self.notes_section)

        # Writes announce themselves; nothing here polls and nothing re-reads disk. The
        # connection is wired explicitly rather than assumed, and is severed when this
        # widget dies — a card view is closed often, and a slot left on an app-wide
        # singleton is a crash waiting for the next save.
        connection = note_events().notes_changed.connect(self.refresh_notes)
        self.destroyed.connect(_disconnect_on_destroy(connection))

        # Add stretch to push everything to the top
        layout.addStretch()

        # Now show/hide and update the appropriate fields based on the current card
        self.update_card_info(self.card, self.deck)

    def update_deck_link(self):
        """Update the deck link in the overview tab"""
        if self.deck and self.deck_value:
            self.deck_value.setText(
                f"<a href='deck:{self.deck.deck_path}'>{self.deck.get_name()}</a>"
            )

    def on_deck_link_clicked(self, link):
        """Handle clicks on the deck link"""
        if self.parent_tab and link.startswith("deck:"):
            deck_path = link[5:]  # Remove 'deck:' prefix

            # Check if deck path is valid; if it's the reference deck with an
            # invalid path, use a different method to resolve it
            reference_deck = self.parent_tab.deck_manager.get_reference_deck()
            if (
                not deck_path or deck_path == "None" or not os.path.exists(deck_path)
            ) and self._is_same_deck(reference_deck):
                self.parent_tab.navigation_requested.emit(
                    "open_deck_view",
                    {
                        "deck_path": reference_deck.deck_path,
                        "source_tab_id": self.parent_tab.id,
                    },
                )
                return

            # Emit signal to open the deck view
            self.parent_tab.navigation_requested.emit(
                "open_deck_view", {"deck_path": deck_path, "source_tab_id": self.parent_tab.id}
            )

    def _is_same_deck(self, other):
        """By path, not identity: installing a deck rebuilds every deck object"""
        if self.deck is None or other is None:
            return False
        return deck_path_key(self.deck.deck_path) == deck_path_key(other.deck_path)

    def update_card_info(self, card, deck):
        """Update the overview tab with new card and deck information"""
        if not card:
            return

        self.card = card
        self.deck = deck

        # Update basic info - directly update the labels
        if self.name_label:
            self.name_label.setText(card["name"])

        if self.id_label:
            self.id_label.setText(f"ID: {card['id']}")

        if self.type_value:
            self.type_value.setText(card["type"].replace("_", " ").title())

        # Show/hide the per-type rows. Only the individual label/value widgets are
        # toggled: every one of them is parented to info_frame, so touching
        # parentWidget() here would hide the whole information block.
        is_minor = card["type"] == "minor_arcana"
        is_major = card["type"] == "major_arcana"

        if is_minor:
            self.suit_value.setText(card.get("display_suit", card["suit"].capitalize()))
            self.rank_value.setText(card.get("display_rank", card["rank"].capitalize()))
        elif is_major:
            self.number_value.setText(str(card["number"]))

        for widget in (self.suit_label, self.suit_value, self.rank_label, self.rank_value):
            widget.setVisible(is_minor)
        for widget in (self.number_label, self.number_value):
            widget.setVisible(is_major)

        # Update deck link
        self.update_deck_link()

        # Update description
        has_description = "alt_text" in card and card["alt_text"]

        if has_description and self.description_label and self.description_header:
            self.description_label.setText(card["alt_text"])
            self.description_header.setVisible(True)
            self.description_label.setVisible(True)
        elif self.description_label and self.description_header:
            self.description_header.setVisible(False)
            self.description_label.setVisible(False)

        self.refresh_notes()

    def refresh_notes(self):
        """Re-read this card's notes from the Notes tab's index.

        The sibling tab already scans on every card load, and it owns the files a live
        editor is autosaving. The section reads what it has; it opens no second reader.
        """
        if not self.notes_section:
            return

        notes_tab = getattr(self.parent_tab, "notes_tab", None)
        card_id = self.card.get("id") if self.card else None
        if not notes_tab or not card_id:
            self.notes_section.set_notes([])
            return

        self.notes_section.set_notes(notes_tab.notes_index.get(card_id, []))

    def on_note_activated(self, file_path):
        """Open a listed note where notes are edited, which is the Notes tab."""
        notes_tab = getattr(self.parent_tab, "notes_tab", None)
        if not notes_tab:
            return

        self.parent_tab.show_notes_tab()
        notes_tab.open_note_path(file_path)

    def on_create_note(self):
        """The section never writes: the [+] and the ghost both route through the tab."""
        notes_tab = getattr(self.parent_tab, "notes_tab", None)
        if not notes_tab:
            return

        self.parent_tab.show_notes_tab()
        notes_tab.create_new_note()
