import pytest
from PyQt6.QtCore import QMargins
from PyQt6.QtGui import QColor, QPalette

from tarot_canvas.settings import (
    ANIMATIONS_ENABLED_KEY,
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    CANVAS_TAB_MINIMAP_KEY,
    CHECKERBOARD_COLOR_DEFAULT,
    CHECKERBOARD_COLOR_KEY,
    MOTION_LEVEL_DEFAULT,
    MOTION_LEVEL_KEY,
    MOTION_LEVELS,
    READING_TEXT_SCALE_DEFAULT,
    READING_TEXT_SCALE_KEY,
    READING_TEXT_SCALE_STEPS,
    SHOW_AVAILABLE_DECKS_KEY,
    THEME_KEY,
    get_reading_text_scale,
    get_settings,
)
from tarot_canvas.ui.library.catalog_client import deck_catalog
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog
from tarot_canvas.utils.theme_manager import ThemeManager, ThemeType


@pytest.fixture
def theme_kept():
    """ThemeManager is a singleton, and remembers the theme across isolated_settings"""
    manager = ThemeManager.get_instance()
    before = manager.get_current_theme()
    yield manager
    manager.set_theme(before)


def test_the_dialog_shows_the_theme_in_force(qtbot, theme_kept):
    theme_kept.set_theme(ThemeType.DARK)

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    assert dialog.theme_combo.currentData() == "dark"


def test_applying_a_theme_reaches_the_theme_manager(qtbot, theme_kept):
    theme_kept.set_theme(ThemeType.SYSTEM)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    dialog.theme_combo.setCurrentIndex(dialog.theme_combo.findData("light"))
    dialog.apply_settings()

    assert theme_kept.get_current_theme() is ThemeType.LIGHT
    assert get_settings().value(THEME_KEY) == "light"


def test_each_sidebar_row_shows_its_page(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    controls = [
        dialog.theme_combo,
        dialog.bg_combo,
        dialog.show_available_decks_check,
        dialog.shortcuts_page.tree,
    ]
    assert dialog.page_list.count() == len(controls)

    for row, control in enumerate(controls):
        dialog.page_list.setCurrentRow(row)
        assert dialog.page_stack.currentWidget().isAncestorOf(control)
        assert dialog.page_title.text() == dialog.page_list.item(row).text()


def test_the_sidebar_is_the_librarys_and_runs_edge_to_edge(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    assert isinstance(dialog.page_list, PlacesSidebar)
    # Darker than the page beside it, as in Dolphin's Configure dialog
    assert dialog.page_list.autoFillBackground()
    assert dialog.page_list.backgroundRole() == QPalette.ColorRole.Base
    assert dialog.layout().contentsMargins() == QMargins(0, 0, 0, 0)


def test_the_dialog_opens_at_the_size_it_was_left(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.width() >= PreferencesDialog.DEFAULT_SIZE.width()
    assert dialog.height() >= PreferencesDialog.DEFAULT_SIZE.height()

    dialog.show()
    # Small enough for the offscreen screen, which restoreGeometry clamps to
    dialog.resize(dialog.width() + 20, dialog.height() + 10)
    size = dialog.size()
    dialog.reject()

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert reopened.size() == size


def test_the_swatch_is_shown_for_the_styles_drawn_from_a_colour(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    for key in ("checkerboard", "gradient", "solid"):
        dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData(key))
        assert dialog.bg_color_btn.isHidden() is (key == "gradient")


def test_the_swatch_edits_the_selected_styles_own_colour(qtbot, monkeypatch):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    picked = []
    monkeypatch.setattr(
        "tarot_canvas.ui.windows.preferences_dialog.QColorDialog.getColor",
        lambda initial, parent: picked.append(QColor(initial)) or QColor("#335544"),
    )

    dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData("checkerboard"))
    dialog.select_bg_color()
    assert picked[-1] == QColor(CHECKERBOARD_COLOR_DEFAULT)
    assert dialog.checkerboard_color == QColor("#335544")
    assert dialog.bg_color == QColor(BACKGROUND_COLOR_DEFAULT)

    # Switching style and back keeps both
    dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData("solid"))
    assert dialog.swatch_color() == QColor(BACKGROUND_COLOR_DEFAULT)
    dialog.select_bg_color()
    assert picked[-1] == QColor(BACKGROUND_COLOR_DEFAULT)
    assert dialog.bg_color == QColor("#335544")
    dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData("checkerboard"))
    assert dialog.swatch_color() == QColor("#335544")


def test_the_checkerboard_colour_is_stored_and_shown_again(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.set_checkerboard_color(QColor("#335544"))
    assert dialog.apply_button.isEnabled()

    dialog.accept()

    assert get_settings().value(CHECKERBOARD_COLOR_KEY) == "#335544"
    assert get_settings().value(BACKGROUND_COLOR_KEY) == BACKGROUND_COLOR_DEFAULT
    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert reopened.checkerboard_color == QColor("#335544")


def test_apply_is_offered_only_while_the_form_differs_from_what_is_stored(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert not dialog.apply_button.isEnabled()

    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("Off"))
    assert dialog.apply_button.isEnabled()

    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData(MOTION_LEVEL_DEFAULT))
    assert not dialog.apply_button.isEnabled()

    dialog.set_bg_color(QColor("#ffffff"))
    assert dialog.apply_button.isEnabled()
    dialog.apply_settings()
    assert not dialog.apply_button.isEnabled()


def test_restore_defaults_resets_the_form_and_stores_nothing(qtbot, theme_kept):
    theme_kept.set_theme(ThemeType.DARK)
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "solid")
    settings.setValue(BACKGROUND_COLOR_KEY, "#ffffff")
    settings.setValue(CHECKERBOARD_COLOR_KEY, "#000000")
    settings.setValue(MOTION_LEVEL_KEY, "Off")
    settings.setValue(CANVAS_TAB_MINIMAP_KEY, False)
    settings.setValue(SHOW_AVAILABLE_DECKS_KEY, False)
    settings.setValue(READING_TEXT_SCALE_KEY, 150)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    stored = {key: settings.value(key) for key in settings.allKeys()}

    dialog.restore_defaults()

    assert dialog.form_state()[:-1] == (
        "system",
        READING_TEXT_SCALE_DEFAULT,
        BACKGROUND_STYLE_DEFAULT,
        BACKGROUND_COLOR_DEFAULT,
        CHECKERBOARD_COLOR_DEFAULT,
        MOTION_LEVEL_DEFAULT,
        True,
        True,
    )
    assert dialog.apply_button.isEnabled()
    assert {key: settings.value(key) for key in settings.allKeys()} == stored
    assert theme_kept.get_current_theme() is ThemeType.DARK


def test_ok_stores_keys_not_labels(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData("solid"))
    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("Reactive"))

    dialog.accept()

    settings = get_settings()
    assert settings.value(BACKGROUND_STYLE_KEY) == "solid"
    assert settings.value(MOTION_LEVEL_KEY) == "Reactive"


def test_clean_settings_use_gradient_background(qtbot):
    settings = get_settings()
    settings.clear()
    settings.sync()

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.bg_combo.currentData() == "gradient"

    canvas_tab = CanvasTab()
    qtbot.addWidget(canvas_tab)
    assert canvas_tab.view.backgroundBrush().gradient() is not None


@pytest.mark.parametrize("stored", ["checkerboard", "Checkerboard"])
def test_saved_checkerboard_background_is_preserved(qtbot, stored):
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, stored)
    settings.sync()

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.bg_combo.currentData() == "checkerboard"

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
    dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData("solid"))
    dialog.apply_settings()

    settings = get_settings()
    assert settings.value(BACKGROUND_STYLE_KEY) == "solid"

    # The canvas tab's brush must reflect the new choice
    assert canvas_tab.view.backgroundBrush().color() == dialog.bg_color

    qtbot.wait(1100)


def test_motion_level_control_shows_what_the_canvas_is_doing(qtbot):
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
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    for level in MOTION_LEVELS:
        assert dialog.motion_combo.findData(level) >= 0


@pytest.fixture
def switch_unset():
    """QSettings is shared across the process, so a test that turns the switch off leaks."""
    get_settings().remove(SHOW_AVAILABLE_DECKS_KEY)
    yield
    get_settings().remove(SHOW_AVAILABLE_DECKS_KEY)


def test_show_available_decks_round_trips(qtbot, switch_unset):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.show_available_decks_check.isChecked()  # on by default

    dialog.show_available_decks_check.setChecked(False)
    dialog.apply_settings()
    assert get_settings().value(SHOW_AVAILABLE_DECKS_KEY, type=bool) is False

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert not reopened.show_available_decks_check.isChecked()


def test_applying_the_switch_reaches_the_catalog(qtbot, monkeypatch, switch_unset):
    """The catalog reads the key once, so the change path is the window's."""
    told = []
    monkeypatch.setattr(deck_catalog(), "set_enabled", told.append)

    def untick_and_apply(dialog):
        dialog.show_available_decks_check.setChecked(False)
        dialog.apply_settings()
        return 0

    monkeypatch.setattr(PreferencesDialog, "exec", untick_and_apply)
    window = MainWindow()
    qtbot.addWidget(window)
    window.show_preferences()

    assert told == [False]


@pytest.fixture
def minimap_unset():
    get_settings().remove(CANVAS_TAB_MINIMAP_KEY)
    yield
    get_settings().remove(CANVAS_TAB_MINIMAP_KEY)


def test_the_canvas_tab_minimap_round_trips(qtbot, minimap_unset):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.canvas_tab_minimap_check.isChecked()

    dialog.canvas_tab_minimap_check.setChecked(False)
    assert dialog.apply_button.isEnabled()
    dialog.apply_settings()
    assert get_settings().value(CANVAS_TAB_MINIMAP_KEY, type=bool) is False

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert not reopened.canvas_tab_minimap_check.isChecked()


def test_applying_the_minimap_switch_reaches_an_open_canvas(qtbot, minimap_unset):
    window = MainWindow()
    qtbot.addWidget(window)
    canvas_tab = window.new_canvas_tab()
    assert canvas_tab.tab_minimap

    dialog = PreferencesDialog(window)
    qtbot.addWidget(dialog)
    dialog.settings_changed.connect(window.apply_settings_to_open_canvases)
    dialog.canvas_tab_minimap_check.setChecked(False)
    dialog.apply_settings()

    assert not canvas_tab.tab_minimap
    qtbot.wait(1100)


def test_the_text_size_sits_with_the_theme_and_offers_every_step_as_a_percentage(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    combo = dialog.text_size_combo
    dialog.page_list.setCurrentRow(0)
    assert dialog.page_stack.currentWidget().isAncestorOf(combo)

    assert [combo.itemData(i) for i in range(combo.count())] == list(READING_TEXT_SCALE_STEPS)
    assert all(combo.itemText(i).startswith(str(combo.itemData(i))) for i in range(combo.count()))
    assert combo.currentData() == READING_TEXT_SCALE_DEFAULT


def test_the_text_size_shows_the_stored_size(qtbot):
    get_settings().setValue(READING_TEXT_SCALE_KEY, 175)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    assert dialog.text_size_combo.currentData() == 175


def test_a_new_text_size_offers_apply_and_applying_stores_it(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    combo = dialog.text_size_combo
    assert not dialog.apply_button.isEnabled()

    combo.setCurrentIndex(combo.findData(150))
    assert dialog.apply_button.isEnabled()

    dialog.apply_settings()

    assert get_reading_text_scale() == 150
    assert not dialog.apply_button.isEnabled()
