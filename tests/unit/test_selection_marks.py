import pytest
from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QColor, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QStyle,
    QStyleOptionGraphicsItem,
)

from tarot_canvas.ui.canvas.alignment import logical_rect
from tarot_canvas.ui.canvas.card_item import DraggableCardItem
from tarot_canvas.ui.canvas.motion import SHADOW_Z_OFFSET, MotionChannels
from tarot_canvas.ui.canvas.selection import (
    AUREOLE_OPACITY,
    AUREOLE_Z_OFFSET,
    CORNER_BASE_OPACITY,
    CORNER_MIN_ARM_SCREEN_PX,
    CORNERS,
    GILT_ON_DARK,
    GILT_ON_LIGHT,
    corner_dips,
    corner_geometry,
    corner_glint,
    gilt_for_ground,
)

CARD_W, CARD_H = 120, 200
FRAME = 1.0 / 60.0
TL, TR, BR, BL = range(4)


class StubTab:
    def __init__(self, reactive=True):
        self.reactive = reactive

    def reactive_is_allowed(self):
        return self.reactive


@pytest.fixture
def card(qapp):
    scenes = []  # a scene takes its items down with it, so keep each one alive

    def build(reactive=True, in_scene=True):
        pixmap = QPixmap(CARD_W, CARD_H)
        pixmap.fill()
        item = DraggableCardItem(pixmap, {"id": "major_arcana/star"}, StubTab(reactive))
        if in_scene:
            scene = QGraphicsScene()
            scene.addItem(item)
            scenes.append(scene)
        return item

    return build


def run(item, frames, ambient_gain=0.0):
    for frame in range(frames):
        item.advance_motion(frame * FRAME, FRAME, ambient_gain)


def opacities(item):
    return [corner.opacity() for corner in item.marks.corners]


# Qt's dashed rectangle


def paint_into_image(item, paint, selected):
    image = QImage(CARD_W, CARD_H, QImage.Format.Format_ARGB32)
    image.fill(0)
    option = QStyleOptionGraphicsItem()
    option.state = QStyle.StateFlag.State_Selected if selected else QStyle.StateFlag.State_None
    option.rect = item.boundingRect().toRect()
    option.exposedRect = item.boundingRect()
    painter = QPainter(image)
    paint(painter, option)
    painter.end()
    return image


def test_a_selected_card_paints_exactly_as_an_unselected_one(card):
    item = card(in_scene=False)

    def ours(painter, option):
        item.paint(painter, option, None)

    def stock(painter, option):
        QGraphicsPixmapItem.paint(item, painter, option, None)

    # The stock paint does draw the dashed rectangle, so the comparison below means something
    assert paint_into_image(item, stock, True) != paint_into_image(item, stock, False)
    assert paint_into_image(item, ours, True) == paint_into_image(item, ours, False)


# The aureole


def test_nothing_is_built_until_the_card_is_first_selected(card):
    item = card()

    assert not item.marks.built
    assert set(item.scene().items()) == {item, item.shadow}


def test_the_aureole_follows_its_card_into_and_out_of_a_scene(card):
    item = card()
    item.setSelected(True)
    scene = item.scene()
    assert item.marks.aureole.scene() is scene

    scene.removeItem(item)
    assert item.marks.aureole.scene() is None

    scene.addItem(item)
    assert item.marks.aureole.scene() is scene


def test_the_aureole_sits_beneath_the_shadow_and_keeps_there_when_restacked(card):
    item = card()
    item.setSelected(True)

    item.setZValue(7.0)

    assert item.marks.aureole.zValue() == 7.0 + AUREOLE_Z_OFFSET
    assert item.marks.aureole.zValue() < item.shadow.zValue() == 7.0 + SHADOW_Z_OFFSET


def test_the_aureole_is_centred_on_its_card_and_does_not_drop_with_lift(card):
    item = card(reactive=False)
    item.setPos(QPointF(300.0, 120.0))
    item.setSelected(True)

    aureole = item.marks.aureole
    centre = aureole.mapToScene(aureole.boundingRect().center())
    card_centre = item.mapToScene(item.boundingRect().center())
    assert centre.x() == pytest.approx(card_centre.x(), abs=1.0)
    assert centre.y() == pytest.approx(card_centre.y(), abs=1.0)
    # The shadow, by contrast, sits below the card
    shadow_centre = item.shadow.mapToScene(item.shadow.boundingRect().center())
    assert shadow_centre.y() > centre.y()


def test_the_aureole_follows_a_card_moved_with_the_clock_stopped(card):
    item = card(reactive=False)
    item.setSelected(True)
    before = item.marks.aureole.pos()

    item.setPos(QPointF(400.0, 250.0))

    moved = item.marks.aureole.pos() - before
    assert moved.x() == pytest.approx(400.0)
    assert moved.y() == pytest.approx(250.0)


def test_the_aureole_takes_the_shadows_silhouette(card):
    item = card()
    item.setSelected(True)

    assert item.marks.aureole.boundingRect() == item.shadow.boundingRect()


# Selection, by motion tier


def test_off_lights_and_unlights_the_card_at_once(card):
    item = card(reactive=False)

    item.setSelected(True)
    assert item.marks.aureole.isVisible()
    assert item.marks.aureole.opacity() == pytest.approx(AUREOLE_OPACITY)
    assert opacities(item) == pytest.approx([CORNER_BASE_OPACITY] * 4)

    item.setSelected(False)
    assert not item.marks.aureole.isVisible()
    assert not any(corner.isVisible() for corner in item.marks.corners)


def test_reactive_fades_the_light_in_and_gathers_the_corners(card):
    item = card()

    item.setSelected(True)
    run(item, 2)
    part_way = item.marks.aureole.opacity()
    assert 0.0 < part_way < AUREOLE_OPACITY
    assert item.marks.corners[0].scale() > 1.0  # still gathering in from outside

    run(item, 60)
    assert item.marks.aureole.opacity() == pytest.approx(AUREOLE_OPACITY)
    assert item.marks.corners[0].scale() == 1.0


def test_reactive_fades_the_light_out_and_then_hides_it(card):
    item = card()
    item.setSelected(True)
    run(item, 60)

    item.setSelected(False)
    run(item, 2)
    assert item.marks.aureole.isVisible()

    run(item, 60)
    assert not item.marks.aureole.isVisible()
    assert not any(corner.isVisible() for corner in item.marks.corners)


def test_a_settled_canvas_lands_the_fade_rather_than_freezing_it(card):
    item = card()
    item.setSelected(True)
    run(item, 2)

    item.settle_motion()

    assert item.marks.aureole.opacity() == pytest.approx(AUREOLE_OPACITY)


# The corners


def test_corners_are_children_of_their_card_and_invisible_to_layout(card):
    item = card()
    before = logical_rect(item)

    item.setSelected(True)

    assert len(item.marks.corners) == len(CORNERS)
    assert all(corner.parentItem() is item for corner in item.marks.corners)
    assert logical_rect(item) == before


def test_corners_sit_outside_the_card_and_never_over_the_art(card):
    item = card()
    item.setSelected(True)
    art = item.boundingRect()

    for corner in item.marks.corners:
        path = corner.path()
        assert not path.intersects(art.adjusted(1, 1, -1, -1))
        assert path.boundingRect().intersects(art.adjusted(-20, -20, 20, 20))


def test_corners_are_mirror_images(card):
    item = card()
    item.setSelected(True)
    sizes = {
        (
            round(corner.path().boundingRect().width(), 6),
            round(corner.path().boundingRect().height(), 6),
        )
        for corner in item.marks.corners
    }
    assert len(sizes) == 1


def test_the_corners_take_the_ground_tone(card):
    item = card()
    item.setSelected(True)
    item.set_gilt(QColor(GILT_ON_LIGHT))

    assert all(corner.brush().color() == QColor(GILT_ON_LIGHT) for corner in item.marks.corners)


# The glint: its sign comes from the drag-tilt report's one rule, not a fresh derivation


def depth(transform, point):
    """The projective w of a mapped point: larger is further from the viewer."""
    return transform.m13() * point.x() + transform.m23() * point.y() + transform.m33()


@pytest.mark.parametrize(
    ("tilt_x", "tilt_y", "spin"),
    [
        (3.0, 0.0, 0.0),
        (-3.0, 0.0, 0.0),
        (0.0, 3.0, 0.0),
        (0.0, -3.0, 0.0),
        (2.0, 5.0, 0.0),
        (-4.0, 1.0, 0.0),
        (0.0, 3.0, 90.0),
        (3.0, 0.0, 180.0),
        (2.0, -5.0, 270.0),
    ],
)
def test_the_corner_the_transform_sends_furthest_away_is_the_one_that_glints(tilt_x, tilt_y, spin):
    channels = MotionChannels(tilt_x=tilt_x, tilt_y=tilt_y, spin=spin)
    transform = channels.compose(CARD_W, CARD_H)
    depths = [depth(transform, p) for p in channels.corners(CARD_W, CARD_H)]
    dips = corner_dips(tilt_x, tilt_y, spin)

    assert dips.index(max(dips)) in {
        i for i, d in enumerate(depths) if d == pytest.approx(max(depths), abs=1e-9)
    }
    assert dips.index(min(dips)) in {
        i for i, d in enumerate(depths) if d == pytest.approx(min(depths), abs=1e-9)
    }


@pytest.mark.parametrize(
    ("point", "bright"),
    [
        ((CARD_W * 0.1, CARD_H * 0.1), TL),
        ((CARD_W * 0.9, CARD_H * 0.1), TR),
        ((CARD_W * 0.9, CARD_H * 0.9), BR),
        ((CARD_W * 0.1, CARD_H * 0.9), BL),
    ],
)
def test_hover_makes_the_corner_under_the_cursor_flare(card, point, bright):
    item = card()
    item.setSelected(True)
    item.begin_hover(QPointF(*point))
    run(item, 60)

    glints = opacities(item)
    assert glints.index(max(glints)) == bright
    assert glints[bright] > CORNER_BASE_OPACITY


@pytest.mark.parametrize(
    ("dx", "dy", "leading"),
    [
        (10.0, 0.0, {TR, BR}),
        (-10.0, 0.0, {TL, BL}),
        (0.0, 10.0, {BL, BR}),
        (0.0, -10.0, {TL, TR}),
    ],
)
def test_the_leading_corners_of_a_drag_catch_the_light(card, dx, dy, leading):
    item = card()
    item.setSelected(True)
    item._dragging = True
    for frame in range(20):
        item.setPos(QPointF(frame * dx, frame * dy))
        item.advance_motion(frame * FRAME, FRAME, 0.0)

    glints = opacities(item)
    trailing = set(range(4)) - leading
    assert min(glints[i] for i in leading) > max(glints[i] for i in trailing)


def test_a_quarter_turned_card_glints_by_screen_direction_not_item_corner(card):
    item = card(reactive=False)
    item.set_orient(90)
    item.setSelected(True)
    item.motion.face_y = 6.0  # screen-left edge goes down
    item.marks.apply()

    glints = opacities(item)
    # a quarter turn clockwise puts the item's bottom edge on the screen's left
    assert glints[BL] > CORNER_BASE_OPACITY
    assert glints[BR] > CORNER_BASE_OPACITY
    assert glints[TL] < CORNER_BASE_OPACITY
    assert glints[TR] < CORNER_BASE_OPACITY


def test_a_flat_card_holds_every_corner_at_the_base_glint():
    assert [corner_glint(d) for d in corner_dips(0.0, 0.0, 0.0)] == [CORNER_BASE_OPACITY] * 4


def test_a_corner_turned_away_still_reads():
    assert corner_glint(-1000.0) > 0.0
    assert corner_glint(1000.0) == 1.0


# Holding up across zoom


def test_the_corners_keep_their_geometry_at_1x(card):
    item = card()
    item.setSelected(True)
    before = item.marks._geometry

    item.set_view_scale(1.15)

    assert item.marks._geometry is before


def test_the_corners_grow_in_item_space_when_zoomed_far_out(card):
    item = card()
    item.setSelected(True)
    near = item.marks.corners[0].path().boundingRect()

    item.set_view_scale(0.25)  # far enough out for the floor, not so far the cap takes over

    far = item.marks.corners[0].path().boundingRect()
    assert far.width() > near.width()
    assert far.width() * 0.25 >= CORNER_MIN_ARM_SCREEN_PX


def test_the_floor_never_lets_opposite_arms_meet():
    arm, root, gap = corner_geometry(CARD_W, CARD_H, 0.001)
    assert 2 * arm < min(CARD_W, CARD_H)


# The ground


@pytest.mark.parametrize(
    ("ground", "tone"),
    [
        (QColor(50, 30, 80), GILT_ON_DARK),  # the gradient's centre
        (QColor(220, 210, 240), GILT_ON_LIGHT),  # the lavender checkerboard
        (QColor("#ffffff"), GILT_ON_LIGHT),
        (QColor("#000000"), GILT_ON_DARK),
    ],
)
def test_the_gilt_follows_the_ground(ground, tone):
    assert gilt_for_ground(ground) == QColor(tone)


def test_a_new_tone_recolours_an_aureole_already_built(card):
    item = card()
    item.setSelected(True)
    before = item.marks.aureole.pixmap().toImage()

    item.set_gilt(QColor(GILT_ON_LIGHT))

    after = item.marks.aureole.pixmap().toImage()
    assert after != before
    assert QRectF(after.rect()) == QRectF(before.rect())
