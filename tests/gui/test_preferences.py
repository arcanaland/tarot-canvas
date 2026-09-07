from tarot_canvas.settings import (
    ANIMATIONS_ENABLED_KEY,
    BACKGROUND_STYLE_KEY,
    MOTION_LEVEL_KEY,
    MOTION_LEVELS,
    get_settings,
)
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog


def test_clean_settings_use_gradient_background(qtbot):
    settings = get_settings()
    settings.clear()
    settings.sync()

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.bg_combo.currentText() == "Gradient"

    canvas_tab = CanvasTab()
    qtbot.addWidget(canvas_tab)
    assert canvas_tab.view.backgroundBrush().gradient() is not None


def test_saved_checkerboard_background_is_preserved(qtbot):
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "Checkerboard")
    settings.sync()

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.bg_combo.currentText() == "Checkerboard"

    canvas_tab = CanvasTab()
    qtbot.addWidget(canvas_tab)
    assert not canvas_tab.view.backgroundBrush().texture().isNull()


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

    settings = get_settings()
    assert settings.value(BACKGROUND_STYLE_KEY) == "Solid Color"

    # The canvas tab's brush must reflect the new choice
    assert canvas_tab.view.backgroundBrush().color() == dialog.bg_color

    qtbot.wait(1100)


def test_motion_level_control_shows_what_the_canvas_is_doing(qtbot):
    """The migration is one-way, so the dialog has to show its result, not a default.

    A user whose old `enable_animations` was false is mapped to Off on first read. Without
    this control that is unreachable from inside the app, and the users it catches are
    exactly the ones with an opinion about canvas motion.
    """
    settings = get_settings()
    settings.clear()
    settings.setValue(ANIMATIONS_ENABLED_KEY, False)
    settings.sync()

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.motion_combo.currentData() == "Off"

    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("Full"))
    dialog.apply_settings()
    assert get_settings().value(MOTION_LEVEL_KEY) == "Full"


def test_applying_a_motion_level_reaches_an_open_canvas(qtbot):
    settings = get_settings()
    settings.clear()
    settings.setValue(MOTION_LEVEL_KEY, "Off")
    settings.sync()

    window = MainWindow()
    qtbot.addWidget(window)
    canvas_tab = window.new_canvas_tab()
    assert not canvas_tab.motion_is_enabled()

    dialog = PreferencesDialog(window)
    qtbot.addWidget(dialog)
    dialog.settings_changed.connect(window.apply_settings_to_open_canvases)
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("Full"))
    dialog.apply_settings()

    assert canvas_tab.motion_level == "Full"
    assert canvas_tab.motion_is_enabled()


def test_every_stored_motion_level_is_selectable(qtbot):
    """A level reachable only through QSettings would be silently rewritten on Apply."""
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    for level in MOTION_LEVELS:
        assert dialog.motion_combo.findData(level) >= 0
