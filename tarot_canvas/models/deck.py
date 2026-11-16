import glob
import logging
import os
import random
import tomllib

from tarot_canvas.models.card_ids import COURTS, MAJOR_ARCANA_COUNT, PIPS, SUITS, roman
from tarot_canvas.models.deck_types import (
    Card,
    CardImage,
    CardKind,
    DeckLink,
    DeckMetadata,
    SuitInfo,
)

log = logging.getLogger(__name__)

CANONICAL_MAJOR_ARCANA_NAMES = {
    "00": "The Fool",
    "01": "The Magician",
    "02": "The High Priestess",
    "03": "The Empress",
    "04": "The Emperor",
    "05": "The Hierophant",
    "06": "The Lovers",
    "07": "The Chariot",
    "08": "Strength",
    "09": "The Hermit",
    "10": "Wheel of Fortune",
    "11": "Justice",
    "12": "The Hanged Man",
    "13": "Death",
    "14": "Temperance",
    "15": "The Devil",
    "16": "The Tower",
    "17": "The Star",
    "18": "The Moon",
    "19": "The Sun",
    "20": "Judgement",
    "21": "The World",
}

RASTER_EXTENSIONS = (".png", ".webp", ".jpg", ".jpeg")


UNKNOWN_DECK = "Unknown Deck"

METADATA_TEXT_FIELDS = (
    "identifier",
    "schema_version",
    "version",
    "description",
    "license",
    "attribution",
    "publisher",
    "website",
    "copyright",
    "created_date",
    "updated_date",
    "published_date",
)


def _text(value):
    """A [deck] scalar as stripped text, or None when absent, empty or not a scalar."""
    if value is None or isinstance(value, bool | dict | list | tuple):
        return None
    return str(value).strip() or None


def _tags(value):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list | tuple):
        return ()
    return tuple(text for text in (str(tag).strip() for tag in value) if text)


def _links(value):
    """[deck].links with a string rel and an http(s) url, in declared order."""
    if not isinstance(value, list):
        return ()
    links = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        rel, url, title = entry.get("rel"), entry.get("url"), entry.get("title")
        if not isinstance(rel, str) or not isinstance(url, str):
            continue
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            continue
        title = title.strip() if isinstance(title, str) else ""
        links.append(DeckLink(rel, url, title or None))
    return tuple(links)


def _pattern(table, root_path=None):
    """The target of the deck's one `pattern` relation, or None."""
    related = table.get("related")
    if not isinstance(related, list):
        return None
    targets = [
        entry.get("target")
        for entry in related
        if isinstance(entry, dict) and entry.get("rel") == "pattern"
    ]
    if len(targets) > 1:
        log.warning(
            "%s: [deck].related names more than one pattern, so the deck is read as having none",
            root_path,
        )
        return None
    if not targets or not isinstance(targets[0], str) or not targets[0].strip():
        return None
    return targets[0].strip()


def read_metadata(table, root_path=None):
    """DeckMetadata from a deck.toml's [deck] table."""
    if not isinstance(table, dict):
        table = {}
    return DeckMetadata(
        name=_text(table.get("name")) or UNKNOWN_DECK,
        artist=_text(table.get("artist")) or _text(table.get("author")),
        pattern=_pattern(table, root_path),
        tags=_tags(table.get("tags")),
        links=_links(table.get("links")),
        **{field: _text(table.get(field)) for field in METADATA_TEXT_FIELDS},
    )


def rasters_by_stem(names):
    """{stem: file name} over RASTER_EXTENSIONS; a stem in several formats takes the first."""
    best = {}
    for name in names:
        stem, ext = os.path.splitext(name)
        if ext in RASTER_EXTENSIONS:
            rank = RASTER_EXTENSIONS.index(ext)
            if stem not in best or rank < best[stem][0]:
                best[stem] = (rank, name)
    return {stem: name for stem, (_, name) in best.items()}


class TarotDeck:  # implements deck_types.Deck
    """A deck read from its directory, behind the `Deck` surface."""

    def __init__(self, root_path):
        self.root_path = root_path
        self._card_backs = None
        self._default_back = None
        self._localized_names_cache = {}
        self._localized_alt_texts_cache = {}
        self._raster_folders = None
        self._raster_index = {}

        self._manifest = self._load_manifest()
        self.metadata = read_metadata(self._manifest.get("deck"), root_path)
        self._suit_aliases = self._extract_suit_aliases()
        self._court_aliases = self._extract_court_aliases()
        self._excluded_cards, self._excluded_reason = self._extract_excluded_cards()

        self._cards = tuple(self._load_all_cards())

    # --------------------------------
    # PRIVATE DATA LOADING METHODS
    # --------------------------------

    def _load_manifest(self):
        """deck.toml, as read."""
        deck_file = os.path.join(self.root_path, "deck.toml")
        if not os.path.exists(deck_file):
            raise FileNotFoundError(f"deck.toml not found in {self.root_path}")

        with open(deck_file, "rb") as f:
            manifest = tomllib.load(f)
            log.debug(
                "Loaded metadata for deck: %s", manifest.get("deck", {}).get("name", "Unknown")
            )
            return manifest

    def _extract_suit_aliases(self):
        """Extract suit aliases from metadata."""
        aliases = {}
        if "aliases" in self._manifest and "suits" in self._manifest["aliases"]:
            for canonical_suit, custom_name in self._manifest["aliases"]["suits"].items():
                aliases[canonical_suit] = custom_name

        if aliases:
            log.debug("Deck '%s' has suit aliases: %s", self.metadata.name, aliases)
        return aliases

    def _extract_court_aliases(self):
        """Extract court card aliases from metadata."""
        aliases = {}
        if "aliases" in self._manifest and "courts" in self._manifest["aliases"]:
            for canonical_court, custom_name in self._manifest["aliases"]["courts"].items():
                aliases[canonical_court] = custom_name
        return aliases

    def _extract_excluded_cards(self):
        """Extract excluded cards list from metadata."""
        excluded = set()
        reason = ""

        if "deck" in self._manifest and "excluded_cards" in self._manifest["deck"]:
            excluded_data = self._manifest["deck"]["excluded_cards"]
            if "cards" in excluded_data and isinstance(excluded_data["cards"], list):
                excluded.update(excluded_data["cards"])

            if "reason" in excluded_data:
                reason = excluded_data["reason"]

        if excluded:
            log.debug("Deck '%s' has %s excluded cards", self.metadata.name, len(excluded))

        return excluded, reason

    def _card_entry(self, card_id):
        """The [cards."<id>"] table for a card"""
        cards = self._manifest.get("cards")
        if not isinstance(cards, dict):
            return {}

        entry = cards.get(card_id)
        return entry if isinstance(entry, dict) else {}

    def _manifest_name(self, card_id):
        """The manifest step of a card's name chain and whether it truncates."""
        entry = self._card_entry(card_id)
        name = entry.get("name")
        if not name:
            supplied = entry.get("supplied_name")
            if isinstance(supplied, dict):
                name = supplied.get("text")
        return (name or None), bool(entry.get("unnamed"))

    def _numeral(self, card_id, number):
        """What a major's face prints as its number, or None if it prints none"""
        entry = self._card_entry(card_id)
        if entry.get("unnumbered"):
            return None
        declared = entry.get("number")
        if isinstance(declared, str) and declared:
            return declared
        return roman(number).upper() or "0"

    def _load_all_cards(self):
        """Load all cards from the deck, respecting exclusions."""
        cards = []

        # Load major arcana cards
        cards.extend(self._load_major_arcana_cards())

        # Load minor arcana cards
        for suit in SUITS:
            cards.extend(self._load_minor_arcana_cards(suit))

        # Add custom cards if any
        if "custom_cards" in self._manifest:
            # TODO: Add support for custom cards
            pass

        # Filter out excluded cards
        filtered_cards = [card for card in cards if card.canonical_id not in self._excluded_cards]

        excluded_count = len(cards) - len(filtered_cards)
        if excluded_count > 0:
            log.info("Excluded %s cards from deck: %s", excluded_count, self.metadata.name)

        log.info("Loaded %s cards for deck: %s", len(filtered_cards), self.metadata.name)
        return filtered_cards

    def _load_major_arcana_cards(self):
        """Load all major arcana cards from the deck."""
        cards = []

        # Cache localized data to avoid repeated file access
        names = self._load_localized_names()
        alt_texts = self._load_localized_alt_texts()

        # Standard major arcana: 0-21
        for i in range(MAJOR_ARCANA_COUNT):
            card_id = f"major_arcana.{i:02d}"

            # Try to get name from localized names, fallback to default
            key = f"{i:02d}"
            numeral = self._numeral(card_id, i)
            name = None
            if names and "major_arcana" in names and key in names["major_arcana"]:
                name = names["major_arcana"][key]
            if not name:
                name, truncated = self._manifest_name(card_id)
                if not name and not truncated:
                    name = CANONICAL_MAJOR_ARCANA_NAMES.get(key)

                # An untitled face keeps its number rather than gaining a name.
                name = name or numeral or key

            images = self._card_images("major_arcana", key)

            # Get alt text for the card
            alt_text = None
            if (
                alt_texts
                and "major_arcana" in alt_texts
                and f"{i:02d}" in alt_texts["major_arcana"]
            ):
                alt_text = alt_texts["major_arcana"][f"{i:02d}"]
            alt_text = alt_text or self._card_entry(card_id).get("alt_text")

            cards.append(
                Card(
                    canonical_id=card_id,
                    kind=CardKind.MAJOR,
                    display_name=name,
                    number=numeral,
                    position=i,
                    alt_text=alt_text,
                    images=images,
                )
            )

        return cards

    def _load_minor_arcana_cards(self, suit):
        """Load all cards for a specific suit."""
        cards = []

        # Cache localized data
        names = self._load_localized_names()
        alt_texts = self._load_localized_alt_texts()

        # Get display suit name (using alias if available)
        display_suit = self._suit_name(suit)

        # Process numbered cards (ace through ten)
        for rank in PIPS:
            card = self._build_minor_arcana_card(suit, rank, display_suit, names, alt_texts)
            cards.append(card)

        # Process court cards
        for court in COURTS:
            card = self._build_court_card(suit, court, display_suit, names, alt_texts)
            cards.append(card)

        return cards

    def _build_minor_arcana_card(self, suit, rank, display_suit, names, alt_texts):
        """Build a minor arcana numbered card (ace through ten)."""
        card_id = f"minor_arcana.{suit}.{rank}"

        # Try to get name from localized names, fallback to default with display suit name
        name = None
        if (
            names
            and "minor_arcana" in names
            and suit in names["minor_arcana"]
            and rank in names["minor_arcana"][suit]
        ):
            name = names["minor_arcana"][suit][rank]
        if not name:
            name, truncated = self._manifest_name(card_id)
            if not name and not truncated:
                name = f"{rank.capitalize()} of {display_suit}"
            name = name or rank.capitalize()

        images = self._card_images(f"minor_arcana/{suit}", rank)

        # Get alt text for the card
        alt_text = None
        if (
            alt_texts
            and "minor_arcana" in alt_texts
            and suit in alt_texts["minor_arcana"]
            and rank in alt_texts["minor_arcana"][suit]
        ):
            alt_text = alt_texts["minor_arcana"][suit][rank]
        alt_text = alt_text or self._card_entry(card_id).get("alt_text")

        return Card(
            canonical_id=card_id,
            kind=CardKind.MINOR,
            display_name=name,
            suit_key=suit,
            rank_key=rank,
            display_suit=display_suit,
            alt_text=alt_text,
            images=images,
        )

    def _build_court_card(self, suit, court, display_suit, names, alt_texts):
        """Build a court card (page, knight, queen, king)."""
        card_id = f"minor_arcana.{suit}.{court}"

        # Get display court name (using alias if available)
        display_court = self.display_rank_name(court)

        # Try to get name from localized names, fallback to default with display names
        name = None
        if (
            names
            and "minor_arcana" in names
            and suit in names["minor_arcana"]
            and court in names["minor_arcana"][suit]
        ):
            name = names["minor_arcana"][suit][court]
        if not name:
            name, truncated = self._manifest_name(card_id)
            if not name and not truncated:
                name = f"{display_court} of {display_suit}"
            name = name or display_court

        images = self._card_images(f"minor_arcana/{suit}", court)

        # Get alt text for the card
        alt_text = None
        if (
            alt_texts
            and "minor_arcana" in alt_texts
            and suit in alt_texts["minor_arcana"]
            and court in alt_texts["minor_arcana"][suit]
        ):
            alt_text = alt_texts["minor_arcana"][suit][court]
        alt_text = alt_text or self._card_entry(card_id).get("alt_text")

        return Card(
            canonical_id=card_id,
            kind=CardKind.MINOR,
            display_name=name,
            suit_key=suit,
            rank_key=court,
            display_suit=display_suit,
            display_rank=display_court,
            alt_text=alt_text,
            images=images,
        )

    def _card_images(self, card_type, card_id):
        """The card's best image first, then its other rasters, highest first."""
        rasters = {
            path: CardImage(path, "raster", height)
            for height, path in sorted(
                self._raster_images(card_type, card_id).items(), reverse=True
            )
        }
        best = self._find_card_image_path(card_type, card_id)
        if best is None:
            return tuple(rasters.values())
        first = rasters.pop(best, None) or CardImage(
            best, "scalable" if best.endswith(".svg") else "raster"
        )
        return (first, *rasters.values())

    def _find_card_image_path(self, card_type, card_id):
        """Find the best available image for a card."""
        # Check in preferred order: h1200, h2400, h750, scalable, ansi32
        for folder in ["h1200", "h2400", "h750", "scalable"]:
            for ext in [".png", ".webp", ".jpg", ".jpeg", ".svg"]:
                path = os.path.join(self.root_path, folder, card_type, f"{card_id}{ext}")
                if os.path.exists(path):
                    return path

        # Try to find an image in any "h" prefixed folder, prioritizing highest resolution
        h_folders = []
        for item in os.listdir(self.root_path):
            if (
                os.path.isdir(os.path.join(self.root_path, item))
                and item.startswith("h")
                and item[1:].isdigit()
            ):
                h_folders.append(item)

        # Sort by resolution (numeric value after 'h') in descending order
        h_folders.sort(key=lambda x: int(x[1:]), reverse=True)

        # Look in each folder in order of resolution
        for folder in h_folders:
            pattern = os.path.join(self.root_path, folder, card_type, f"{card_id}.*")
            matches = glob.glob(pattern)
            if matches:
                return matches[0]

        # If not found in h folders, check any remaining folders
        pattern = os.path.join(self.root_path, "*", card_type, f"{card_id}.*")
        matches = glob.glob(pattern)
        if matches:
            return matches[0]

        # Return a placeholder if no image found
        log.warning("No image found for card: %s/%s", card_type, card_id)
        return None

    def _raster_images(self, card_type, card_id):
        """A card's raster images as {height: path}."""
        if self._raster_folders is None:
            self._raster_folders = {}
            try:
                entries = sorted(os.listdir(self.root_path))
            except OSError:
                entries = []
            for item in entries:
                if (
                    item.startswith("h")
                    and item[1:].isdigit()
                    and os.path.isdir(os.path.join(self.root_path, item))
                ):
                    self._raster_folders.setdefault(int(item[1:]), item)
        if card_type not in self._raster_index:
            self._raster_index[card_type] = self._index_raster_card_type(card_type)
        return dict(self._raster_index[card_type].get(card_id, {}))

    def _index_raster_card_type(self, card_type):
        """{card_id: {height: path}} for one card type."""
        index = {}
        for height, folder in self._raster_folders.items():
            directory = os.path.join(self.root_path, folder, card_type)
            try:
                names = os.listdir(directory)
            except OSError:
                continue
            for stem, name in rasters_by_stem(names).items():
                index.setdefault(stem, {})[height] = os.path.join(directory, name)
        return index

    def _name_files_are_faceted(self):
        """Whether name files nest every table under its facet, as 2.0's do.

        The shape follows from the manifest's schema_version, never from the
        name file's contents (deck spec 7.2): a 2.0 file may carry alt text alone.
        """
        major = str(self.metadata.schema_version or "1.0").split(".")[0]
        return major.isdigit() and int(major) >= 2

    def _facet(self, data, facet):
        """A name-file facet"""
        if not isinstance(data, dict):
            return None

        # 2.0: [name.card.<kind>] and [alt_text.card.<kind>]
        if self._name_files_are_faceted():
            table = data.get(facet)
            cards = table.get("card") if isinstance(table, dict) else None
            return cards if isinstance(cards, dict) else None

        # 1.0: names at the top level, alt text under [alt_text.<kind>]
        table = data if facet == "name" else data.get(facet)
        return table if isinstance(table, dict) else None

    def _name_file_tags(self, lang=None):
        """Name-file language tags to try most preferred first"""
        requested = lang or _text(self._manifest.get("deck", {}).get("default_language"))
        tags = []
        if requested:
            parts = str(requested).split("-")
            tags += ["-".join(parts[:i]) for i in range(len(parts), 0, -1)]
        if "en" not in tags:
            tags.append("en")
        return tags

    def _read_name_file(self, lang=None):
        """The first name file that exists, by preference order, or None."""
        for tag in self._name_file_tags(lang):
            path = os.path.join(self.root_path, "names", f"{tag}.toml")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    return tomllib.load(f)
        return None

    def _load_localized_names(self, lang=None):
        """Load localized names for cards."""
        if lang not in self._localized_names_cache:
            self._localized_names_cache[lang] = self._facet(self._read_name_file(lang), "name")
        return self._localized_names_cache[lang]

    def _load_localized_alt_texts(self, lang=None):
        """Load alt texts for cards from localization files."""
        if lang not in self._localized_alt_texts_cache:
            self._localized_alt_texts_cache[lang] = self._facet(
                self._read_name_file(lang), "alt_text"
            )
        return self._localized_alt_texts_cache[lang]

    def _load_card_backs(self):
        """{stem: path} for the deck's backs, and the default back's stem.

        A back is card_backs/<stem>.<ext> over RASTER_EXTENSIONS, and when a stem is in
        more than one format the first in that order wins, as a face does.
        """
        # TODO(spec §6.5): card_backs/ under an image root, [card_backs.designs], and SVG
        default_back = self._manifest.get("card_backs", {}).get("default", "classic")

        directory = os.path.join(self.root_path, "card_backs")
        try:
            names = os.listdir(directory)
        except OSError:
            names = []
        backs = {
            stem: os.path.join(directory, name)
            for stem, name in sorted(rasters_by_stem(names).items())
        }

        self._card_backs = backs
        self._default_back = default_back

        return backs, default_back

    def _suit_name(self, suit_key):
        return self._suit_aliases.get(suit_key) or suit_key.capitalize()

    # --------------------------------
    # PUBLIC SURFACE
    # --------------------------------

    @property
    def cards(self):
        return self._cards

    @property
    def suits(self):
        """Canonical suits in SUITS order, then any other suit in the order its cards appear.

        A canonical suit with no card left is `excluded`.
        """
        found = []
        for card in self._cards:
            if card.kind is CardKind.MINOR and card.suit_key and card.suit_key not in found:
                found.append(card.suit_key)
        keys = list(SUITS) + [suit for suit in found if suit not in SUITS]
        return tuple(SuitInfo(key, self._suit_name(key), excluded=key not in found) for key in keys)

    @property
    def exclusion_reason(self):
        return self._excluded_reason or None

    def find_card(self, card_id):
        return next((card for card in self._cards if card.canonical_id == card_id), None)

    def cards_of_kind(self, kind):
        return [card for card in self._cards if card.kind is kind]

    def cards_in_suit(self, suit_key):
        return [card for card in self._cards if card.suit_key == suit_key]

    def random_card(self):
        return random.choice(self._cards) if self._cards else None

    def display_rank_name(self, rank_key):
        """A rank's name, using the deck's court aliases."""
        return self._court_aliases.get(rank_key) or rank_key.capitalize()

    def get_card_backs(self):
        """Get available card back images and the default back."""
        if self._card_backs is None:
            self._card_backs, self._default_back = self._load_card_backs()
        return self._card_backs, self._default_back
