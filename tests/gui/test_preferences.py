from PyQt6.QtCore import QSettings

from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog


def test_apply_updates_open_canvas_background(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    canvas_tab = window.new_canvas_tab()

    dialog = PreferencesDialog(window)
    qtbot.addWidget(dialog)
    dialog.settings_changed.connect(window.apply_settings_to_open_canvases)
    index = dialog.bg_combo.findText("Solid Color")
    dialog.bg_combo.setCurrentIndex(index)
    dialog.apply_settings()

    settings = QSettings("ArcanaLand", "TarotCanvas")
    assert settings.value("appearance/background_style") == "Solid Color"
    # The canvas tab's brush must reflect the *new* choice, not whatever it
    # rendered at construction time.
    assert canvas_tab.view.backgroundBrush().color() == dialog.bg_color

    # CanvasTab.__init__ schedules ensure_window_bounds/update_tab_icon via
    # QTimer.singleShot (up to 1000ms out); let them fire before qtbot tears
    # the widgets down, or they land on already-deleted C++ objects and crash.
    qtbot.wait(1100)


def test_disabling_animations_stops_new_cards_animating(qtbot, monkeypatch):
    from PyQt6.QtCore import QAbstractAnimation

    from tarot_canvas.ui.canvas import DraggableCardItem
    from tarot_canvas.ui.canvas import card_item as card_item_module

    settings = QSettings("ArcanaLand", "TarotCanvas")
    settings.setValue("appearance/enable_animations", False)

    # The wobble start is scheduled behind a random 0-1000ms QTimer.singleShot;
    # pin it to 0 so the test doesn't need to sleep out the worst case.
    monkeypatch.setattr(card_item_module.random, "randint", lambda a, b: 0)

    window = MainWindow()
    qtbot.addWidget(window)
    canvas_tab = window.new_canvas_tab()

    card = canvas_tab.deck.get_all_cards()[0]
    canvas_tab.add_specific_card(card)
    qtbot.wait(50)

    items = [item for item in canvas_tab.scene.items() if isinstance(item, DraggableCardItem)]
    assert items, "expected a card item to have been added to the canvas"
    assert items[0].rotation_anim.state() == QAbstractAnimation.State.Stopped

    # See the comment in test_apply_updates_open_canvas_background: flush
    # CanvasTab's own pending singleShot timers before teardown.
    qtbot.wait(1100)
