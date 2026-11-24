"""SPIKE (slop/decan-spike): the 36 numbered pips laid out by decan, three ways.

Throwaway. Placement is read from one esoterica source; the geometry (12 signs of 30°,
three decans of 10°) is the system's and lives here.
"""

import logging
import math
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from PyQt6.QtCore import QDate, QLocale, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsSimpleTextItem,
    QMenu,
    QSpinBox,
    QWidget,
)

from tarot_canvas.models.deck_library import deck_library
from tarot_canvas.models.esoterica import get_esoterica_manager
from tarot_canvas.ui import typography
from tarot_canvas.ui.canvas import DraggableCardItem
from tarot_canvas.ui.canvas.detail import load_card_art
from tarot_canvas.ui.strings import CANVAS, COMMANDS
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab

log = logging.getLogger(__name__)

DOCK_ENV = "TAROT_SPIKE_DECAN_DOCK"

# The one source the spike reads, by its [meta].name (SourceReading carries no identifier)
SOURCE_NAME = "A Guide to Tarot Card Meanings"

SIGNS = (
    "aries",
    "taurus",
    "gemini",
    "cancer",
    "leo",
    "virgo",
    "libra",
    "scorpio",
    "sagittarius",
    "capricorn",
    "aquarius",
    "pisces",
)
# A range's separator, not prose
EN_DASH = chr(0x2013)
# Text presentation, never emoji
VS15 = "︎"
SIGN_GLYPHS = {sign: chr(0x2648 + index) + VS15 for index, sign in enumerate(SIGNS)}
PLANET_GLYPHS = {
    "sun": "☉" + VS15,
    "moon": "☽" + VS15,
    "mercury": "☿" + VS15,
    "venus": "♀" + VS15,
    "mars": "♂" + VS15,
    "jupiter": "♃" + VS15,
    "saturn": "♄" + VS15,
}
RANKS = {
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}

LAYOUTS = ("wheel", "strip", "table")
ORIENTATIONS = ("radial", "upright")
CARD_PX_DEFAULT = 120

# Line alpha out of 255, for rings, spokes and rules
LINE_ALPHA = 70
MARK_ALPHA = 200


# -- data -------------------------------------------------------------------


@dataclass
class SignCards:
    sign: str
    major: object = None
    # The source named more than one sign for the major; it sits on the first
    ambiguous: bool = False
    # (card, planet) in rank order, at most three
    pips: list = field(default_factory=list)


@dataclass
class Placement:
    signs: list
    unplaced: list


def _correspondence(readings, key):
    for reading in readings:
        if reading.name != SOURCE_NAME:
            continue
        for entry in reading.entries:
            if entry.slot == "correspondences" and entry.key == key:
                return entry.value
    return None


def _clean(word):
    word = word.strip().lower()
    return word[4:] if word.startswith("the ") else word


def parse_astrology(value):
    """(planet, sign) from McElroy's "<planet> in <sign>", or None for anything else"""
    if not isinstance(value, str) or " in " not in value:
        return None
    planet, sign = (_clean(part) for part in value.split(" in ", 1))
    if sign not in SIGNS:
        return None
    return planet, sign


def parse_zodiac(value):
    """(sign, ambiguous) from a `zodiac` value, taking the first-named of "a or b" """
    if not isinstance(value, str):
        return None
    named = [_clean(part) for part in value.split(" or ")]
    if named[0] not in SIGNS:
        return None
    return named[0], len(named) > 1


def decan_placement(deck, manager=None):
    """Which card the source puts on which sign and decan, and the cards it puts nowhere"""
    manager = manager or get_esoterica_manager()
    by_sign = {sign: SignCards(sign) for sign in SIGNS}
    pips = {sign: [] for sign in SIGNS}
    unplaced = []
    for card in deck.cards:
        readings = manager.read_card(card.canonical_id, deck)
        astrology = parse_astrology(_correspondence(readings, "astrology"))
        zodiac = parse_zodiac(_correspondence(readings, "zodiac"))
        if astrology is not None and card.rank_key in RANKS:
            planet, sign = astrology
            pips[sign].append((RANKS[card.rank_key], card, planet))
        elif zodiac is not None and by_sign[zodiac[0]].major is None:
            by_sign[zodiac[0]].major = card
            by_sign[zodiac[0]].ambiguous = zodiac[1]
        else:
            unplaced.append(card)
    for sign in SIGNS:
        ranked = sorted(pips[sign], key=lambda pip: pip[0])
        by_sign[sign].pips = [(card, planet) for _, card, planet in ranked[:3]]
        unplaced.extend(card for _, card, _ in ranked[3:])
    placement = Placement([by_sign[sign] for sign in SIGNS], unplaced)
    log.debug(
        "Decan placement for %s: %d pips, %d majors, %d unplaced",
        deck.metadata.name,
        sum(len(s.pips) for s in placement.signs),
        sum(s.major is not None for s in placement.signs),
        len(placement.unplaced),
    )
    return placement


# -- the sun -----------------------------------------------------------------

J2000 = datetime(2000, 1, 1, 12, tzinfo=UTC)
TROPICAL_YEAR = 365.2422


def sun_longitude(when):
    """The sun's apparent ecliptic longitude in degrees at datetime when (UTC), to ~0.01°"""
    n = (when - J2000).total_seconds() / 86400.0
    mean = 280.460 + 0.9856474 * n
    g = math.radians(357.528 + 0.9856003 * n)
    return (mean + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360.0


def decan_of(longitude):
    """0 (Aries, first decan) to 35"""
    return int(longitude // 10.0) % 36


def _crossing(year, k):
    """When the sun reaches 10k° after the equinox that opens `year`'s zodiac year"""
    guess = datetime(year, 3, 20, 12, tzinfo=UTC) + timedelta(days=k * TROPICAL_YEAR / 36)
    target = (10.0 * k) % 360.0

    def ahead(when):
        return (sun_longitude(when) - target + 180.0) % 360.0 - 180.0

    low, high = guess - timedelta(days=8), guess + timedelta(days=8)
    for _ in range(40):
        middle = low + (high - low) / 2
        if ahead(middle) < 0:
            low = middle
        else:
            high = middle
    return low + (high - low) / 2


def decan_dates(when):
    """For the zodiac year holding datetime when: 36 (first day, last day) date pairs"""
    year = when.year if when >= _crossing(when.year, 0) else when.year - 1
    starts = [_crossing(year, k) for k in range(37)]
    return [(starts[k].date(), (starts[k + 1] - timedelta(days=1)).date()) for k in range(36)]


def _date_format():
    """The locale's short date format without its year"""
    fmt = QLocale().dateFormat(QLocale.FormatType.ShortFormat)
    return re.sub(r"[^dM]*y+[^dM]*", "", fmt) or "M/d"


def date_range_text(first, last):
    fmt = _date_format()
    return QDate(first).toString(fmt) + EN_DASH + QDate(last).toString(fmt)


# -- items -------------------------------------------------------------------


class BoardCardItem(DraggableCardItem):
    """A card that can be selected and opened, but never moved"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        QGraphicsPixmapItem.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        QGraphicsPixmapItem.mouseMoveEvent(self, event)

    def mouseReleaseEvent(self, event):
        QGraphicsPixmapItem.mouseReleaseEvent(self, event)


class GlyphItem(QGraphicsSimpleTextItem):
    """A glyph or a date; a sign's glyph selects the sign's cards when clicked"""

    def __init__(self, text, px, colour, on_click=None):
        super().__init__(text)
        self.setFont(typography.in_pixels(QApplication.font(), max(6, px)))
        self.setBrush(colour)
        self.on_click = on_click
        if on_click is not None:
            self.setCursor(Qt.CursorShape.PointingHandCursor)
            self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        else:
            self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def centre_on(self, point, rotation=0.0):
        rect = self.boundingRect()
        self.setTransformOriginPoint(rect.center())
        self.setRotation(rotation)
        self.setPos(point - rect.center())

    def mousePressEvent(self, event):
        if self.on_click is not None:
            self.on_click()
            event.accept()
        else:
            super().mousePressEvent(event)


class Backdrop(QGraphicsItem):
    """Every ring, spoke, rule and outline, beneath the cards, in one fixed rect"""

    frames_home = True

    def __init__(self):
        super().__init__()
        self.circles = []
        self.lines = []
        # (centre, width, height, rotation, style) with style "dashed" or "today"
        self.outlines = []
        self.hand = None
        self.rect = QRectF()
        self.colour = QColor(Qt.GlobalColor.white)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def set_shapes(self, circles, lines, outlines, hand, colour):
        self.prepareGeometryChange()
        self.circles, self.lines, self.outlines, self.hand = circles, lines, outlines, hand
        self.colour = QColor(colour)
        rect = QRectF()
        for r in circles:
            rect = rect.united(QRectF(-r, -r, 2 * r, 2 * r))
        for a, b in lines:
            rect = rect.united(QRectF(a, b).normalized())
        for centre, w, h, _rotation, _style in outlines:
            reach = math.hypot(w, h) / 2 + 4
            rect = rect.united(QRectF(centre.x() - reach, centre.y() - reach, 2 * reach, 2 * reach))
        if hand is not None:
            rect = rect.united(QRectF(hand[0], hand[1]).normalized())
        self.rect = rect.adjusted(-8, -8, 8, 8)
        self.update()

    def boundingRect(self):
        return self.rect

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        line = QColor(self.colour)
        line.setAlpha(LINE_ALPHA)
        pen = QPen(line, 1.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        for r in self.circles:
            painter.drawEllipse(QPointF(0, 0), r, r)
        for a, b in self.lines:
            painter.drawLine(a, b)

        mark = QColor(self.colour)
        mark.setAlpha(MARK_ALPHA)
        for centre, w, h, rotation, style in self.outlines:
            pen = QPen(mark, 2.0 if style == "today" else 1.5)
            pen.setCosmetic(True)
            if style == "dashed":
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.save()
            painter.translate(centre)
            painter.rotate(rotation)
            painter.drawRect(QRectF(-w / 2, -h / 2, w, h))
            painter.restore()

        if self.hand is not None:
            pen = QPen(mark, 2.0)
            pen.setCosmetic(True)
            painter.setPen(pen)
            painter.drawLine(*self.hand)
            painter.setBrush(mark)
            painter.drawEllipse(self.hand[1], 4, 4)


# -- the tab ----------------------------------------------------------------


@dataclass
class Spot:
    """Where a card goes: its centre and its turn"""

    centre: QPointF
    orient: float = 0.0


class BoardTab(CanvasTab):
    """SPIKE: a read-only canvas placing cards by a source's decans"""

    SAVES_CANVAS = False
    # A board keeps no ground on disk; its own (from the Background panel) lasts as long as the
    # tab. Sandbox follows every canvas unless the user gave scratch canvases their own.
    GROUND_KIND = "sandbox"

    def __init__(self, parent=None):
        self.board_layout = "wheel"
        self.orientation = "radial"
        self.date = QDate.currentDate()
        self.card_px = CARD_PX_DEFAULT
        self.show_unplaced = True
        self.show_planets = True
        self.show_dates = True
        self.placement = None
        self.items = {}
        self.glyphs = []
        super().__init__(parent)
        self.tab_name = COMMANDS["new_decan_board"]
        self.board_deck = deck_library.reference()

        # A board is read-only: what would change a card is hidden
        self.paste_action.setVisible(False)
        for action in self.arrange_actions.values():
            action.setVisible(False)

        self.backdrop = Backdrop()
        self.backdrop.setZValue(-1000)
        self.scene.addItem(self.backdrop)

        self.dock = BoardDock(self) if os.environ.get(DOCK_ENV) == "1" else None
        self._home_on_show = True
        self.rebuild()

    # -- read-only ---------------------------------------------------------

    def tools(self):
        return ()

    def command_handlers(self):
        handlers = super().command_handlers()
        for command_id in ("canvas.summon", "canvas.flip", "canvas.rotate", "canvas.delete"):
            del handlers[command_id]
        del handlers["canvas.save_layout_as_spread"]
        return handlers

    def shows_draw_here(self):
        return False

    def on_draw_card(self, at=None):
        pass

    def on_turn_card_by_wheel(self, card, notches, fine):
        pass

    def on_delete_card(self):
        pass

    def on_flip_card(self):
        pass

    def on_rotate_card(self):
        pass

    def on_bring_to_front(self):
        pass

    def on_send_to_back(self):
        pass

    def can_paste_card(self, mime):
        return False

    def can_cut_card(self):
        return False

    def can_delete(self):
        return False

    def build_card_menu(self, item):
        menu = QMenu(self)
        open_action = menu.addAction(CANVAS["open_card"])
        open_action.triggered.connect(lambda: self.open_card_view(item))
        self._menu_entry(menu, "window.copy_card", self.copy_card, self.can_copy_card())
        return menu

    # -- showing -----------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if self.dock is not None:
            self.dock.show()
        if self._home_on_show:
            self._home_on_show = False
            QTimer.singleShot(0, self.on_home)

    def hideEvent(self, event):
        super().hideEvent(event)
        if self.dock is not None and not event.spontaneous():
            self.dock.hide()

    def about_to_close(self):
        super().about_to_close()
        if self.dock is not None:
            self.dock.close()
            self.dock.deleteLater()
            self.dock = None

    def text_colour(self):
        return QApplication.palette().color(QPalette.ColorRole.WindowText)

    # -- building ----------------------------------------------------------

    def set_deck(self, deck):
        self.board_deck = deck
        self.rebuild()

    def set_card_px(self, px):
        self.card_px = px
        self.rebuild()

    def rebuild(self):
        """Read the placement and make every card again"""
        for item in self.items.values():
            self.scene.removeItem(item)
        self.items = {}
        self._cards_by_sign = {}
        self.placement = decan_placement(self.board_deck)
        cards = []
        for sign in self.placement.signs:
            if sign.major is not None:
                cards.append(sign.major)
            cards.extend(card for card, _ in sign.pips)
        cards.extend(self.placement.unplaced)
        for card in cards:
            item = self._make_item(card)
            if item is not None:
                self.items[card.canonical_id] = item
        self.relayout()

    def _make_item(self, card):
        path = card.default_image()
        if not path or not os.path.exists(path):
            log.warning("No art for %s", card.canonical_id)
            return None
        art = load_card_art(path)
        if art is None:
            return None
        pixmap, source_size = art
        pixmap = pixmap.scaledToHeight(self.card_px, Qt.TransformationMode.SmoothTransformation)
        item = BoardCardItem(pixmap, card, self, deck=self.board_deck)
        item.set_art_source(path, source_size)
        return item

    def _card_size(self):
        widths = [item.boundingRect().width() for item in self.items.values()]
        return (max(widths) if widths else self.card_px * 0.58), float(self.card_px)

    def relayout(self):
        """Put every card in its spot for the current layout, and redraw the lines and glyphs"""
        for glyph in self.glyphs:
            self.scene.removeItem(glyph)
        self.glyphs = []
        self.shapes = {"circles": [], "lines": [], "outlines": [], "hand": None}
        self.spots = {}
        self.today_decan = decan_of(
            sun_longitude(
                datetime(self.date.year(), self.date.month(), self.date.day(), 12, tzinfo=UTC)
            )
        )
        self.dates = decan_dates(
            datetime(self.date.year(), self.date.month(), self.date.day(), 12, tzinfo=UTC)
        )

        {"wheel": self._lay_wheel, "strip": self._lay_strip, "table": self._lay_table}[
            self.board_layout
        ]()
        self._lay_unplaced()
        self._mark_ambiguous()

        z = 1.0
        for card_id, item in self.items.items():
            spot = self.spots.get(card_id)
            if spot is None:
                if item.scene() is not None:
                    self.scene.removeItem(item)
                continue
            item.restore(spot.centre - item.boundingRect().center(), z, spot.orient)
            z += 1.0
            if item.scene() is None:
                self.scene.addItem(item)
        self._top_z = z

        colour = self.text_colour()
        self.backdrop.set_shapes(
            self.shapes["circles"],
            self.shapes["lines"],
            self.shapes["outlines"],
            self.shapes["hand"],
            colour,
        )
        self.scene.update()

    def _glyph(self, text, px, point, rotation=0.0, on_click=None):
        item = GlyphItem(text, px, self.text_colour(), on_click)
        item.setZValue(-999)
        item.centre_on(point, rotation)
        self.scene.addItem(item)
        self.glyphs.append(item)
        return item

    def _sign_glyph(self, sign, point):
        return self._glyph(
            SIGN_GLYPHS[sign], self.card_px * 0.28, point, on_click=lambda: self.select_sign(sign)
        )

    def _place(self, card, centre, orient=0.0):
        self.spots[card.canonical_id] = Spot(centre, orient)

    def _today_outline(self, decan, centre, w, h, rotation=0.0):
        if decan == self.today_decan:
            pad = self.card_px * 0.06
            self.shapes["outlines"].append((centre, w + 2 * pad, h + 2 * pad, rotation, "today"))

    def _mark_ambiguous(self):
        w, h = self._card_size()
        pad = self.card_px * 0.06
        for sign in self.placement.signs:
            if sign.major is not None and sign.ambiguous:
                spot = self.spots.get(sign.major.canonical_id)
                if spot is not None:
                    self.shapes["outlines"].append(
                        (spot.centre, w + 2 * pad, h + 2 * pad, spot.orient, "dashed")
                    )

    def _date_text(self, decan):
        first, last = self.dates[decan]
        return date_range_text(first, last)

    # -- wheel -------------------------------------------------------------

    def _lay_wheel(self):
        w, h = self._card_size()
        pad = h * 0.12
        glyph = h * 0.28
        planet = h * 0.16
        small = h * 0.10
        radial = self.orientation == "radial"
        # The card's extent along the ring, and across it
        along = w if radial else h
        across = h

        r_major = max(12 * (along + pad) / (2 * math.pi), across * 0.75)
        r0 = max(r_major - across / 2 - pad, 0.0)
        r1 = r_major + across / 2 + pad
        r_pip = max(36 * (along + pad / 2) / (2 * math.pi), r1 + 1.6 * glyph + pad + across / 2)
        r2 = r_pip - across / 2 - pad
        r_sign = (r1 + r2) / 2
        r3 = r_pip + across / 2 + pad
        r_planet = r3 + planet
        r_date = r_planet + (planet if self.show_planets else 0) + small * 0.5
        date_length = small * 7.5 if self.show_dates else 0
        outer = r_date + date_length + (small if self.show_dates else 0)

        def point(longitude, r):
            theta = math.radians(180.0 + longitude)
            return QPointF(r * math.cos(theta), -r * math.sin(theta))

        def outward(longitude):
            # Qt's clockwise turn that points a card's top away from the centre
            return (90.0 - (180.0 + longitude)) % 360 if radial else 0.0

        circles = [r for r in (r0, r1, r2, r3, outer) if r > 0]
        self.shapes["circles"] = circles
        lines = []
        for s in range(12):
            lines.append((point(30 * s, r0), point(30 * s, outer)))
        for d in range(36):
            if d % 3:
                lines.append((point(10 * d, r2), point(10 * d, outer)))
        self.shapes["lines"] = lines

        for s, sign in enumerate(self.placement.signs):
            middle = 30 * s + 15
            self._sign_glyph(sign.sign, point(middle, r_sign))
            if sign.major is not None:
                self._place(sign.major, point(middle, r_major), outward(middle))
            for slot, (card, planet_name) in enumerate(sign.pips):
                decan = 3 * s + slot
                longitude = 10 * decan + 5
                self._place(card, point(longitude, r_pip), outward(longitude))
                if self.show_planets:
                    self._glyph(
                        PLANET_GLYPHS.get(planet_name, "?"), planet, point(longitude, r_planet)
                    )
                if self.show_dates:
                    # Read along the radius, never upside down
                    theta = 180.0 + longitude
                    rotation = -theta
                    if 90.0 < theta % 360 < 270.0:
                        rotation += 180.0
                    self._glyph(
                        self._date_text(decan),
                        small,
                        point(longitude, r_date + date_length / 2),
                        rotation,
                    )

        longitude = sun_longitude(
            datetime(self.date.year(), self.date.month(), self.date.day(), 12, tzinfo=UTC)
        )
        self.shapes["hand"] = (point(longitude, r0 * 0.2), point(longitude, outer + small))
        self.layout_rect = QRectF(-outer, -outer, 2 * outer, 2 * outer)

    # -- strip -------------------------------------------------------------

    def _lay_strip(self):
        w, h = self._card_size()
        pad = h * 0.12
        glyph = h * 0.28
        planet = h * 0.16
        small = h * 0.10
        step = w + w * 0.15
        y_major = 0.0
        y_glyph = h / 2 + pad + glyph * 0.6
        y_pip = y_glyph + glyph * 0.6 + pad + h / 2
        y_planet = y_pip + h / 2 + pad + planet * 0.6
        y_date = y_planet + (planet * 0.6 + pad if self.show_planets else 0) + small
        top = -h / 2 - pad
        bottom = y_date + small + pad

        lines = []
        for s in range(13):
            x = 3 * s * step - step / 2
            lines.append((QPointF(x, top), QPointF(x, bottom)))
        for d in range(36):
            if d % 3:
                x = d * step - step / 2
                lines.append((QPointF(x, y_pip + h / 2), QPointF(x, bottom)))
        rule_y = y_glyph + glyph * 0.6 + pad / 2
        lines.append((QPointF(-step / 2, rule_y), QPointF(36 * step - step / 2, rule_y)))
        self.shapes["lines"] = lines

        for s, sign in enumerate(self.placement.signs):
            x_mid = (3 * s + 1) * step
            self._sign_glyph(sign.sign, QPointF(x_mid, y_glyph))
            if sign.major is not None:
                self._place(sign.major, QPointF(x_mid, y_major))
            for slot, (card, planet_name) in enumerate(sign.pips):
                decan = 3 * s + slot
                x = decan * step
                self._place(card, QPointF(x, y_pip))
                self._today_outline(decan, QPointF(x, y_pip), w, h)
                if self.show_planets:
                    self._glyph(PLANET_GLYPHS.get(planet_name, "?"), planet, QPointF(x, y_planet))
                if self.show_dates:
                    self._glyph(self._date_text(decan), small, QPointF(x, y_date))
        self.layout_rect = QRectF(-step / 2, top, 36 * step, bottom - top)

    # -- table -------------------------------------------------------------

    def _lay_table(self):
        w, h = self._card_size()
        pad = h * 0.12
        glyph = h * 0.28
        planet = h * 0.16
        small = h * 0.10
        glyph_col = glyph * 2.0
        x_major = glyph_col / 2 + pad + w / 2
        x_pips = [x_major + (w + pad * 2) * (k + 1) for k in range(3)]
        under = (planet * 1.2 if self.show_planets else 0) + (small * 1.6 if self.show_dates else 0)
        row = h + pad * 2 + under
        left = -glyph_col / 2
        right = x_pips[-1] + w / 2 + pad

        lines = [
            (QPointF(glyph_col / 2, -h / 2 - pad), QPointF(glyph_col / 2, 12 * row - h / 2 - pad))
        ]
        for r in range(13):
            y = r * row - h / 2 - pad
            lines.append((QPointF(left, y), QPointF(right, y)))
        self.shapes["lines"] = lines

        for s, sign in enumerate(self.placement.signs):
            y = s * row
            self._sign_glyph(sign.sign, QPointF(0, y))
            if sign.major is not None:
                self._place(sign.major, QPointF(x_major, y))
            for slot, (card, planet_name) in enumerate(sign.pips):
                decan = 3 * s + slot
                x = x_pips[slot]
                self._place(card, QPointF(x, y))
                self._today_outline(decan, QPointF(x, y), w, h)
                below = y + h / 2 + pad
                if self.show_planets:
                    self._glyph(
                        PLANET_GLYPHS.get(planet_name, "?"),
                        planet,
                        QPointF(x, below + planet * 0.5),
                    )
                    below += planet * 1.2
                if self.show_dates:
                    self._glyph(self._date_text(decan), small, QPointF(x, below + small * 0.6))
        self.layout_rect = QRectF(left, -h / 2 - pad, right - left, 12 * row)

    # -- unplaced ----------------------------------------------------------

    def _lay_unplaced(self):
        if not self.show_unplaced:
            return
        w, h = self._card_size()
        gap = h * 0.12
        rect = self.layout_rect
        if self.board_layout == "strip":
            columns = 15
            x0 = rect.left() + w / 2
            y0 = rect.bottom() + h * 0.8 + h / 2
        else:
            columns = 6
            x0 = rect.right() + w * 1.5 + w / 2
            y0 = rect.top() + h / 2
        for index, card in enumerate(self.placement.unplaced):
            column, row = index % columns, index // columns
            self._place(card, QPointF(x0 + column * (w + gap), y0 + row * (h + gap)))

    # -- selecting a sign --------------------------------------------------

    def select_sign(self, sign_name):
        """Select the sign's major and its three pips"""
        sign = next(s for s in self.placement.signs if s.sign == sign_name)
        cards = ([sign.major] if sign.major is not None else []) + [c for c, _ in sign.pips]
        self.scene.clearSelection()
        for card in cards:
            item = self.items.get(card.canonical_id)
            if item is not None and item.scene() is not None:
                item.setSelected(True)


class BoardDock(QWidget):
    """SPIKE: a floating window of the board's knobs, labelled by identifier"""

    def __init__(self, tab):
        super().__init__(tab, Qt.WindowType.Tool)
        self.tab = tab
        self.setWindowTitle("decan_board")
        form = QFormLayout(self)

        self.layout_box = QComboBox()
        self.layout_box.addItems(LAYOUTS)
        self.layout_box.currentTextChanged.connect(self._set_layout)
        form.addRow("layout", self.layout_box)

        self.orientation_box = QComboBox()
        self.orientation_box.addItems(ORIENTATIONS)
        self.orientation_box.currentTextChanged.connect(self._set_orientation)
        form.addRow("orientation", self.orientation_box)

        self.date_edit = QDateEdit(tab.date)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self._set_date)
        form.addRow("date", self.date_edit)

        self.decks = list(deck_library.decks())
        self.deck_box = QComboBox()
        for deck in self.decks:
            self.deck_box.addItem(deck.metadata.identifier or os.path.basename(str(deck.root_path)))
        for index, deck in enumerate(self.decks):
            if str(deck.root_path) == str(tab.board_deck.root_path):
                self.deck_box.setCurrentIndex(index)
        self.deck_box.currentIndexChanged.connect(lambda i: tab.set_deck(self.decks[i]))
        form.addRow("deck", self.deck_box)

        self.unplaced_box = QCheckBox()
        self.unplaced_box.setChecked(tab.show_unplaced)
        self.unplaced_box.toggled.connect(lambda on: self._set("show_unplaced", on))
        form.addRow("unplaced", self.unplaced_box)

        self.card_px_box = QSpinBox()
        self.card_px_box.setRange(30, 500)
        self.card_px_box.setSingleStep(10)
        self.card_px_box.setValue(tab.card_px)
        self.card_px_box.setKeyboardTracking(False)
        self.card_px_box.valueChanged.connect(tab.set_card_px)
        form.addRow("card_px", self.card_px_box)

        self.planets_box = QCheckBox()
        self.planets_box.setChecked(tab.show_planets)
        self.planets_box.toggled.connect(lambda on: self._set("show_planets", on))
        form.addRow("planets", self.planets_box)

        self.dates_box = QCheckBox()
        self.dates_box.setChecked(tab.show_dates)
        self.dates_box.toggled.connect(lambda on: self._set("show_dates", on))
        form.addRow("dates", self.dates_box)

    def _set(self, name, value):
        setattr(self.tab, name, value)
        self.tab.relayout()

    def _set_layout(self, name):
        self._set("board_layout", name)
        self.tab.on_home()

    def _set_orientation(self, name):
        self._set("orientation", name)
        self.tab.on_home()

    def _set_date(self, date):
        self._set("date", date)
