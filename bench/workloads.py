"""What the canvas is asked to do each frame."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from PyQt6.QtCore import QPointF

# How far a dragged card or the camera travels from where it started, in logical px
DRAG_REACH_PX = 240.0
PAN_REACH_PX = 300.0
# One lap of a drag or pan path, in seconds of simulated time
LAP_S = 4.0


def _nothing(canvas):
    return None


def _still(canvas, state, t):
    pass


@dataclass(frozen=True)
class Workload:
    name: str
    description: str
    # Whether the cards drift and tilt on their own, as at Motion: Full
    ambient: bool = True
    # Repaint the whole viewport every frame whether or not anything moved
    repaint: bool = False
    # Called once before warmup; its result is handed to every step
    start: Callable = field(default=_nothing)
    # Called at the start of every frame with the simulated time t
    step: Callable = field(default=_still)


def lissajous(t, reach):
    """A figure-of-eight through the origin, one lap every LAP_S."""
    phase = math.tau * t / LAP_S
    return QPointF(reach * math.sin(phase), reach * 0.5 * math.sin(2 * phase))


def _start_drag(canvas):
    card = canvas.cards()[-1]
    card._pressed = True
    card.begin_drag()
    return card, QPointF(card.pos())


def _step_drag(canvas, state, t):
    card, origin = state
    card.setPos(origin + lissajous(t, DRAG_REACH_PX))


def _start_group_drag(canvas):
    cards = canvas.cards()
    for card in cards:
        card.setSelected(True)
    cards[-1]._pressed = True
    cards[-1].begin_drag()
    return [(card, QPointF(card.pos())) for card in cards]


def _step_group_drag(canvas, state, t):
    offset = lissajous(t, DRAG_REACH_PX)
    for card, origin in state:
        card.setPos(origin + offset)


def _start_pan(canvas):
    return canvas.scroll_position()


def _step_pan(canvas, origin, t):
    canvas.scroll_to(origin + lissajous(t, PAN_REACH_PX))


WORKLOADS = (
    Workload(
        "repaint",
        "flat, still cards; the whole viewport repainted each frame",
        ambient=False,
        repaint=True,
    ),
    Workload("ambient", "every card drifting and tilting in perspective"),
    Workload("drag", "the top card dragged over the rest", start=_start_drag, step=_step_drag),
    Workload(
        "group-drag",
        "every card selected and dragged together",
        start=_start_group_drag,
        step=_step_group_drag,
    ),
    Workload("pan", "the camera panning while the cards drift", start=_start_pan, step=_step_pan),
)


def find_workload(name):
    for workload in WORKLOADS:
        if workload.name == name:
            return workload
    return None
