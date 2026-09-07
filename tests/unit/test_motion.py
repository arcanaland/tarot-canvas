import math
import sys

import pytest
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QPixmap, QTransform, qAlpha

from tarot_canvas.ui.canvas.motion import (
    DRIFT_AMPLITUDE_PX,
    LIFT_PLACED,
    LIFT_REST,
    MAX_DT,
    SHADOW_BLUR_PX,
    TILT_AMPLITUDE_DEG,
    AmbientDrift,
    MotionChannels,
    MotionClock,
    PinkOscillator,
    Spring,
    approach,
    build_contact_shadow,
    drift_phases,
    rest,
    shadow_geometry,
    system_animations_enabled,
)

CARD = (300.0, 500.0)
CORNERS = [(0.0, 0.0), (300.0, 0.0), (300.0, 500.0), (0.0, 500.0)]


def test_zeroed_channels_compose_to_exact_identity():
    """The whole of phase 2 rests on this: the substrate must be invisible."""
    assert MotionChannels().compose(*CARD).isIdentity()


def test_orient_matches_the_setrotation_it_replaces():
    """Turning a card through the channel must be pixel-identical to the old call."""
    composed = MotionChannels(orient=180.0).compose(*CARD)

    previous = QTransform()
    previous.translate(150.0, 250.0)  # what setTransformOriginPoint(centre) established
    previous.rotate(180.0)
    previous.translate(-150.0, -250.0)

    for x, y in CORNERS:
        cx, cy = composed.map(x, y)
        px, py = previous.map(x, y)
        assert cx == pytest.approx(px, abs=1e-9)
        assert cy == pytest.approx(py, abs=1e-9)


def edge_heights(transform):
    """The heights of the card's two vertical edges under `transform`."""
    left = transform.map(*CORNERS[3])[1] - transform.map(*CORNERS[0])[1]
    right = transform.map(*CORNERS[2])[1] - transform.map(*CORNERS[1])[1]
    return left, right


def test_tilt_produces_a_real_perspective_trapezoid():
    """Not a 2-D spin: the card plane turns in space, so parallel edges stop being equal."""
    tilted = MotionChannels(tilt_y=6.0).compose(*CARD)
    assert not tilted.isAffine()

    # Rotating about the vertical axis swings one side away from the viewer, so the two
    # vertical edges stop being the same height. A 2-D spin can never do that. The
    # threshold tracks the tuned perspective strength: this asserted a 50 px difference
    # back when the substrate carried the RFC spike's untuned value, which was nine times
    # too strong and pointed the wrong way (see below).
    left, right = edge_heights(tilted)
    assert abs(left - right) > 20.0


def test_tilt_amplifies_qt_own_perspective_rather_than_inverting_it():
    """The regression guard for a sign bug that made cards pump instead of tilt.

    `QTransform.rotate(angle, axis)` already applies a projective divide of its own, at an
    effective viewing distance of 1024 px. Our extra term has to push the same way; a
    positive one subtracts, and at any useful magnitude it flips the trapezoid so the edge
    turning *away* from the viewer is the one that grows.
    """
    bare = QTransform()
    bare.translate(150.0, 250.0)
    bare.rotate(6.0, Qt.Axis.YAxis)
    bare.translate(-150.0, -250.0)

    bare_left, bare_right = edge_heights(bare)
    ours_left, ours_right = edge_heights(MotionChannels(tilt_y=6.0).compose(*CARD))

    # Same side near, and further from square than Qt manages alone.
    assert (ours_right - ours_left) * (bare_right - bare_left) > 0.0
    assert abs(ours_right - ours_left) > abs(bare_right - bare_left)


def test_tilt_is_continuous_through_zero():
    """Drift crosses zero constantly; a step there would read as a twitch every cycle."""
    for tilt in (1e-3, 1e-4, 1e-5):
        composed = MotionChannels(tilt_y=tilt).compose(*CARD)
        worst = max(
            max(abs(composed.map(x, y)[0] - x), abs(composed.map(x, y)[1] - y)) for x, y in CORNERS
        )
        assert worst < tilt * 20.0  # shrinks linearly with the angle, no constant term


def test_approach_converges_identically_at_60hz_and_144hz():
    """Framerate independence, the property Balatro-Feel's Lerp does not have."""
    slow = fast = 0.0
    for _ in range(60):
        slow = approach(slow, 1.0, 5.0, 1.0 / 60.0)
    for _ in range(144):
        fast = approach(fast, 1.0, 5.0, 1.0 / 144.0)

    assert slow == pytest.approx(fast, abs=1e-9)
    assert slow == pytest.approx(1.0 - math.exp(-5.0), abs=1e-9)


def test_approach_never_overshoots_and_is_inert_without_time():
    assert approach(0.0, 1.0, 1e6, 1.0) <= 1.0
    assert approach(0.0, 1.0, 5.0, 0.0) == 0.0
    assert approach(0.0, 1.0, 0.0, 1.0) == 0.0


def test_clock_runs_only_while_something_listens(qapp):
    clock = MotionClock()
    ticks = []

    assert not clock.is_running()
    clock.subscribe(ticks.append)
    assert clock.is_running()
    clock.subscribe(ticks.append)  # a repeat subscribe must not double-drive
    clock.unsubscribe(ticks.append)
    assert not clock.is_running()
    clock.unsubscribe(ticks.append)  # unsubscribing twice is not an error


def test_clock_ticks_with_monotonic_time_and_a_clamped_dt(qtbot):
    clock = MotionClock()
    ticks = []
    clock.subscribe(lambda t, dt: ticks.append((t, dt)))

    qtbot.waitUntil(lambda: len(ticks) >= 3, timeout=1000)

    times = [t for t, _ in ticks]
    assert times == sorted(times)
    assert all(0.0 < dt <= MAX_DT for _, dt in ticks)


def test_portal_read_answers_with_a_bool_on_any_desktop():
    """CI has no session bus, a developer machine does; both must give a usable answer."""
    assert isinstance(system_animations_enabled(), bool)


def test_portal_failure_leaves_motion_enabled(monkeypatch):
    """A desktop-integration failure must not be what switches the app's feature off."""
    monkeypatch.setitem(sys.modules, "PyQt6.QtDBus", None)  # makes the import raise
    assert system_animations_enabled() is True


# Ambient drift


def test_oscillator_stays_within_its_amplitude_over_a_long_sweep():
    """The 1/f weights are normalised, so an amplitude constant means what it says."""
    oscillator = PinkOscillator(drift_phases("the-tower", 4))
    assert max(abs(oscillator.value(i * 0.05)) for i in range(20000)) <= 1.0


def test_a_card_breathes_the_same_way_every_session():
    """Seeded from the card's id, not from `id(item)` or a salted `hash()`."""
    assert drift_phases("major_arcana/the_fool", 16) == drift_phases("major_arcana/the_fool", 16)
    assert drift_phases("major_arcana/the_fool", 16) != drift_phases(
        "major_arcana/the_magician", 16
    )
    assert all(0.0 <= phase < math.tau for phase in drift_phases("x", 16))


def test_two_cards_are_never_in_step():
    """N cards drifting together would read as the whole spread sliding, not as N cards."""
    fool = AmbientDrift("major_arcana/the_fool")
    magician = AmbientDrift("major_arcana/the_magician")
    assert any(
        abs(a - b) > 0.5
        for t in (0.0, 3.0, 17.0, 100.0)
        for a, b in zip(fool.sample(t), magician.sample(t), strict=True)
    )


def test_drift_is_bounded_by_the_amplitude_constants():
    """Halving a constant must halve what is on screen, with no hidden headroom."""
    drift = AmbientDrift("major_arcana/the_hermit")
    for i in range(20000):
        tilt_x, tilt_y, drift_x, drift_y = drift.sample(i * 0.05)
        assert abs(tilt_x) <= TILT_AMPLITUDE_DEG
        assert abs(tilt_y) <= TILT_AMPLITUDE_DEG
        assert abs(drift_x) <= DRIFT_AMPLITUDE_PX
        assert abs(drift_y) <= DRIFT_AMPLITUDE_PX


def test_drift_never_stalls_and_never_jumps():
    """The old wobble stalled at all four of its segment joints; a C-infinity sum cannot.

    A stall reads as a stutter and a jump reads as a snap, and the previous implementation
    managed both. Over a minute of 16 ms ticks, every step is small and none is zero.
    """
    drift = AmbientDrift("major_arcana/the_moon")
    steps = []
    previous = drift.sample(0.0)
    for i in range(1, 3750):
        current = drift.sample(i * 0.016)
        steps.append(max(abs(a - b) for a, b in zip(current, previous, strict=True)))
        previous = current

    assert max(steps) < 0.2  # no snap
    assert min(steps) > 0.0  # no stall


def test_drift_does_not_start_from_a_special_case_at_zero():
    """Cards are added while the clock is already running; t=0 must not be a home position."""
    assert any(abs(v) > 1e-6 for v in AmbientDrift("major_arcana/the_star").sample(0.0))


# The reactive tier


def test_the_spring_overshoots_once_and_then_stops_exactly():
    """The whole reason `lift` gets a spring rather than approach(): a settle has weight.

    approach() converges from one side by construction, which reads as the card being
    lowered by machinery. The spring passes its target once and lands on it exactly — the
    rest floor is what makes "exactly" true, and it is what stops an idle canvas repainting.
    """
    spring = Spring(LIFT_PLACED)
    trace = [spring.advance(LIFT_REST, 1.0 / 60.0) for _ in range(240)]

    assert min(trace) < LIFT_REST  # it went past
    assert max(trace) <= LIFT_PLACED  # and not the other way first
    assert trace[-1] == LIFT_REST  # exactly, not asymptotically
    assert spring.velocity == 0.0


def test_the_spring_settles_the_same_way_at_60hz_and_144hz():
    """Substepping is what buys this; an explicit spring stepped at dt alone would not."""
    slow = Spring(LIFT_PLACED)
    fast = Spring(LIFT_PLACED)
    for _ in range(30):
        slow.advance(LIFT_REST, 1.0 / 60.0)
    for _ in range(72):
        fast.advance(LIFT_REST, 1.0 / 144.0)

    assert slow.value == pytest.approx(fast.value, abs=1e-4)


def test_the_spring_survives_a_stalled_event_loop():
    """MAX_DT permits a 100 ms tick after a modal dialog. An unsubstepped spring explodes."""
    spring = Spring(LIFT_PLACED)
    for _ in range(50):
        spring.advance(LIFT_REST, MAX_DT)

    assert spring.value == pytest.approx(LIFT_REST, abs=1e-3)


def test_rest_snaps_only_once_the_difference_stops_mattering():
    assert rest(1.0 + 1e-9, 1.0) == 1.0
    assert rest(1.5, 1.0) == 1.5


def test_reactive_tilt_is_not_scaled_by_the_ambient_gain():
    """RFC-024 rule 2 in one assertion: one gate scales one tier.

    Hover and drag tilt the card too, so they get their own channels rather than borrowing
    the ambient ones — otherwise gating ambient would silently gate the hover response as
    well, and `Reactive` could not differ from `Off`.
    """
    ambient = MotionChannels(tilt_x=3.0, tilt_y=3.0)
    reactive = MotionChannels(face_x=3.0, face_y=3.0)

    assert ambient.compose(*CARD) == reactive.compose(*CARD)
    assert not MotionChannels(face_x=3.0).compose(*CARD).isAffine()  # real perspective


def test_face_and_tilt_sum_into_one_plane_rather_than_composing_twice():
    combined = MotionChannels(tilt_y=1.0, face_y=2.0).compose(*CARD)

    assert combined == MotionChannels(tilt_y=3.0).compose(*CARD)


def test_the_tilt_signs_the_reactive_targets_are_written_against():
    """Pinned because the hover and lean directions are derived from them.

    Measured rather than assumed: `compose()` carries an extra projective term of its own,
    so which edge recedes is a property of this composition and not of Qt's axis convention.
    """
    left, right = edge_heights(MotionChannels(tilt_y=3.0).compose(*CARD))
    assert left < right  # tilt_y > 0 turns the left edge away

    corners = [MotionChannels(tilt_x=3.0).compose(*CARD).map(QPointF(x, y)) for x, y in CORNERS]
    top = math.dist((corners[0].x(), corners[0].y()), (corners[1].x(), corners[1].y()))
    bottom = math.dist((corners[3].x(), corners[3].y()), (corners[2].x(), corners[2].y()))
    assert top < bottom  # tilt_x > 0 turns the top edge away


def test_orient_lag_leaves_the_composed_angle_untouched_at_the_moment_of_a_turn():
    """A turn is a lag, not a jump: the display is continuous across `set_orient`."""
    before = MotionChannels(orient=0.0).compose(*CARD)
    after = MotionChannels(orient=90.0, orient_lag=-90.0).compose(*CARD)

    assert before == after


def test_the_contact_shadow_is_softer_and_larger_than_the_card_it_grounds():
    pixmap = QPixmap(120, 200)
    pixmap.fill(Qt.GlobalColor.black)

    shadow = build_contact_shadow(pixmap)
    image = shadow.toImage()

    # Padded on every side, so the penumbra is not clipped at the silhouette's edge.
    assert shadow.width() > pixmap.width()
    assert shadow.height() > pixmap.height()
    # Opaque in the middle, feathered at the border — a hard-edged copy would fail both.
    assert qAlpha(image.pixel(image.width() // 2, image.height() // 2)) > 200
    assert 0 < qAlpha(image.pixel(int(SHADOW_BLUR_PX * 0.6), image.height() // 2)) < 200
    assert qAlpha(image.pixel(0, 0)) == 0


def test_a_lifted_card_casts_a_wider_fainter_shadow_further_from_itself():
    """Penumbra separation is the whole of what makes a card read as floating."""
    resting = shadow_geometry(LIFT_REST)
    lifted = shadow_geometry(LIFT_PLACED)

    assert lifted[0] > resting[0]  # further
    assert lifted[1] > resting[1]  # wider
    assert lifted[2] < resting[2]  # fainter
