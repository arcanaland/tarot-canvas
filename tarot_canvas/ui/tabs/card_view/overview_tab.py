import html
import os

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

from tarot_canvas.models.esoterica import get_esoterica_manager
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.models.esoterica_registry import Role
from tarot_canvas.models.note_events import note_events
from tarot_canvas.ui.card_transfer import deck_path_key
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library import units
from tarot_canvas.ui.palette import muted_text, with_text_colour
from tarot_canvas.ui.tabs.card_view.esoterica_tab import (
    Byline,
    byline_row,
    draw_reseated_icon,
    lead_of,
    lead_row,
    reseated_note,
)
from tarot_canvas.ui.tabs.card_view.headings import (
    SUBTITLE_SCALE,
    TITLE_SCALE,
    apply_heading,
)
from tarot_canvas.ui.tabs.card_view.notes_section import NotesSection
from tarot_canvas.ui.tabs.card_view.passage_metrics import TITLE_TO_AUTHOR

# Whose words head the Overview, in order of preference
HEADLINE_ROLES = (Role.KEYWORDS, Role.EPITHET)


def headline_of(readings):
    """The headline's source and entries, or None. A source about this deck leads with
    whatever it has, before any other source's keywords."""
    for reading in readings:
        if not reading.about_deck:
            continue
        for role in HEADLINE_ROLES:
            if (lead := lead_of(reading, (role,))) is not None:
                return reading, lead[1]
    for role in HEADLINE_ROLES:
        for reading in readings:
            if (lead := lead_of(reading, (role,))) is not None:
                return reading, lead[1]
    return None


class OverviewTab(QWidget):
    """Tab displaying overview information about a tarot card"""

    def __init__(self, card=None, deck=None, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        self.card = card
        self.deck = deck

        self.name_label = None
        # The type and the number, or suit and rank; then the deck as a link
        self.subtitle = None
        self.deck_value = None

        # The first source's keywords, and its author (or else its name) under them
        self.headline = None
        self.lead = None
        self.headline_source = None
        self.headline_source_name = None
        # Beside the byline when the headline's text was written for another card
        self.headline_reseated = None

        # The deck's description of the art
        self.description_label = None

        # Notes
        self.notes_section = None

        self.setup_ui()

    def setup_ui(self):
        """Set up the overview tab UI"""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)

        if not self.card:
            layout.addWidget(QLabel("No card information available"))
            return

        # Card name at the top
        self.name_label = QLabel(self.card["name"])
        apply_heading(self.name_label, TITLE_SCALE)
        self.name_label.setObjectName("name_label")
        layout.addWidget(self.name_label)

        # Two subtitle lines directly under the name: what the card is, then where it is from
        self.subtitle = QLabel()
        self.subtitle.setObjectName("subtitle")
        self.subtitle.setWordWrap(True)
        self.subtitle.setTextFormat(Qt.TextFormat.PlainText)
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.subtitle)

        self.deck_value = QLabel()
        self.deck_value.setObjectName("deck_value")
        self.deck_value.setWordWrap(True)
        self.deck_value.setTextFormat(Qt.TextFormat.RichText)
        self.deck_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.deck_value.setOpenExternalLinks(False)
        self.deck_value.linkActivated.connect(self.on_deck_link_clicked)
        layout.addWidget(self.deck_value)

        # Its top margin goes with it when there is no headline
        self.headline = QWidget()
        self.headline.setObjectName("headline")
        headline_layout = QVBoxLayout(self.headline)
        headline_layout.setContentsMargins(0, units.LARGE_SPACING, 0, 0)
        headline_layout.setSpacing(TITLE_TO_AUTHOR)
        self.headline_source = Byline()
        self.headline_source.setObjectName("headline_source")
        self.headline_source.setWordWrap(True)
        self.headline_source.setTextFormat(Qt.TextFormat.RichText)
        self.headline_source.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse
            | Qt.TextInteractionFlag.LinksAccessibleByKeyboard
        )
        self.headline_source.setOpenExternalLinks(False)
        self.headline_source.setFont(units.scaled_font(self.headline_source.font(), SUBTITLE_SCALE))
        self.headline_source.linkActivated.connect(self.on_headline_source_clicked)
        self.headline_reseated = QLabel()
        self.headline_reseated.setObjectName("headline_reseated")
        self.headline_reseated.setVisible(False)
        headline_layout.addLayout(byline_row(self.headline_source, self.headline_reseated))
        layout.addWidget(self.headline)

        # Set well apart from the keywords, which are the source's words and not the deck's.
        # Its top margin goes with it when the deck has no description.
        self.description_label = QLabel()
        self.description_label.setContentsMargins(0, units.GRID_UNIT, 0, 0)
        self.description_label.setWordWrap(True)
        self.description_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.description_label.setObjectName("description_label")
        layout.addWidget(self.description_label)

        layout.addSpacing(units.LARGE_SPACING)
        self.notes_section = NotesSection(self)
        self.notes_section.noteActivated.connect(self.on_note_activated)
        self.notes_section.createRequested.connect(self.on_create_note)
        layout.addWidget(self.notes_section)

        note_events().notes_changed.connect(self.refresh_notes)
        esoterica_events().sources_changed.connect(self.refresh_headline)

        # Add stretch to push everything to the top
        layout.addStretch()

        self._apply_colours()

        # Now show/hide and update the appropriate fields based on the current card
        self.update_card_info(self.card, self.deck)

    def _apply_colours(self):
        muted = muted_text(self.palette())
        self.subtitle.setPalette(with_text_colour(self.subtitle.palette(), muted))
        self._draw_headline_source()

    def _draw_headline_source(self):
        if self.headline_source_name is None:
            return
        colour = muted_text(self.palette()).name()
        self.headline_source.setText(
            f"<a href='esoterica:' style='color: {colour}'>"
            f"{html.escape(self.headline_source_name)}</a>"
        )

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self.subtitle:
            self._apply_colours()

    def _deck_link(self):
        if not self.deck:
            return None
        return (
            f"<a href='deck:{html.escape(str(self.deck.deck_path))}'>"
            f"{html.escape(self.deck.get_name())}</a>"
        )

    def update_subtitle(self):
        """The type, then the number or the suit and rank, under the name"""
        if not self.subtitle or not self.card:
            return
        card = self.card
        facts = [card["type"].replace("_", " ").title()]
        if card["type"] == "minor_arcana":
            facts.append(card.get("display_suit", card["suit"].capitalize()))
            facts.append(card.get("display_rank", card["rank"].capitalize()))
        elif card.get("numeral") and card["numeral"] != card["name"]:
            facts.append(card["numeral"])
        self.subtitle.setText(label_for("joiner").join(facts))

        # The canonical ID
        self.subtitle.setToolTip(card["id"])
        self.subtitle.setAccessibleDescription(card["id"])

    def update_deck_link(self):
        """The deck's name, as a link to it, on the line under the subtitle"""
        if not self.deck_value:
            return
        link = self._deck_link()
        self.deck_value.setText(link or "")
        self.deck_value.setVisible(link is not None)

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

        if self.name_label:
            self.name_label.setText(card["name"])

        self.update_subtitle()
        self.update_deck_link()
        self.refresh_headline()

        # Update description
        has_description = "alt_text" in card and card["alt_text"]

        if self.description_label:
            self.description_label.setText(card["alt_text"] if has_description else "")
            self.description_label.setVisible(bool(has_description))

        self.refresh_notes()

    def refresh_headline(self):
        """Read this card's keywords again from the enabled sources."""
        if not self.headline:
            return

        if self.lead is not None:
            self.headline.layout().removeWidget(self.lead)
            self.lead.deleteLater()
            self.lead = None

        card_id = self.card.get("id") if self.card else None
        readings = get_esoterica_manager().read_card(card_id, deck=self.deck) if card_id else []
        headline = headline_of(readings)
        if headline is None:
            self.headline.setVisible(False)
            return

        reading, entries = headline
        self.lead = lead_row(entries)
        self.lead.setObjectName("lead")
        self.headline.layout().insertWidget(0, self.lead)
        # A byline: the author is shorter than the title and reads as a credit
        self.headline_source_name = reading.author or reading.name
        self.headline_source.setToolTip(reading.name if reading.author else "")
        self._draw_headline_source()
        draw_reseated_icon(
            self.headline_reseated, reseated_note(reading, self.deck), self.headline_source
        )
        self.headline.setVisible(True)

    def on_headline_source_clicked(self, _link):
        if hasattr(self.parent_tab, "show_esoterica_tab"):
            self.parent_tab.show_esoterica_tab()

    def refresh_notes(self):
        """Re-read this card's notes from the Notes tab's index."""
        if not self.notes_section:
            return

        notes_tab = getattr(self.parent_tab, "notes_tab", None)
        card_id = self.card.get("id") if self.card else None
        if not notes_tab or not card_id:
            self.notes_section.set_notes([])
            return

        self.notes_section.set_notes(notes_tab.notes_index.get(card_id, []))

    def on_note_activated(self, file_path):
        if hasattr(self.parent_tab, "open_note"):
            self.parent_tab.open_note(file_path)

    def on_create_note(self):
        notes_tab = getattr(self.parent_tab, "notes_tab", None)
        if not notes_tab:
            return

        self.parent_tab.show_notes_tab()
        notes_tab.create_new_note()
