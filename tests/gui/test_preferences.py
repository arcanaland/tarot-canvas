from tarot_canvas.settings import BACKGROUND_STYLE_KEY, get_settings
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
