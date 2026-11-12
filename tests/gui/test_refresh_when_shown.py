from PyQt6.QtWidgets import QWidget

from tarot_canvas.ui.refresh_when_shown import RefreshWhenShown


def watched(qtbot):
    widget = QWidget()
    qtbot.addWidget(widget)
    calls = []
    return widget, calls, RefreshWhenShown(widget, lambda: calls.append(1))


def test_a_shown_widget_refreshes_at_each_change(qtbot):
    widget, calls, refresh = watched(qtbot)
    widget.show()
    qtbot.waitExposed(widget)

    refresh.changed()
    refresh.changed()
    assert calls == [1, 1]


def test_a_hidden_widget_refreshes_once_when_next_shown(qtbot):
    widget, calls, refresh = watched(qtbot)
    for _ in range(3):
        refresh.changed()
    assert calls == []

    widget.show()
    qtbot.waitExposed(widget)
    assert calls == [1]

    widget.hide()
    widget.show()
    assert calls == [1]


def test_a_widget_shown_with_nothing_changed_does_not_refresh(qtbot):
    widget, calls, _refresh = watched(qtbot)
    widget.show()
    qtbot.waitExposed(widget)
    assert calls == []
