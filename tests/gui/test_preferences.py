import sys

import pytest
from PyQt6.QtCore import QMargins, QMimeData, QPointF, QSize, Qt, QUrl
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QImage, QPalette
from PyQt6.QtWidgets import QApplication

from tarot_canvas.models.ground import Ground
from tarot_canvas.settings import (
    ANIMATIONS_ENABLED_KEY,
    BACKGROUND_COLOR_DEFAULT,
    BACKGROUND_COLOR_KEY,
    BACKGROUND_IMAGE_KEY,
    BACKGROUND_STYLE_DEFAULT,
    BACKGROUND_STYLE_KEY,
    CANVAS_GUIDES_KEY,
    CANVAS_TAB_MINIMAP_KEY,
    CHECKERBOARD_COLOR_DEFAULT,
    CHECKERBOARD_COLOR_KEY,
    HARDWARE_ACCELERATION_KEY,
    MOTION_LEVEL_DEFAULT,
    MOTION_LEVEL_KEY,
    MOTION_LEVELS,
    PREFERENCES_PAGE_KEY,
    READING_TEXT_SCALE_DEFAULT,
    READING_TEXT_SCALE_KEY,
    READING_TEXT_SCALE_STEPS,
    SHOW_AVAILABLE_DECKS_KEY,
    SHOW_WELCOME_KEY,
    THEME_KEY,
    get_reading_text_scale,
    get_settings,
)
from tarot_canvas.ui.catalog.client import deck_catalog
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.widgets.places_sidebar import PlacesSidebar
from tarot_canvas.ui.windows import background_form, preferences_dialog
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
        dialog.motion_combo,
        dialog.background_form.bg_combo,
        dialog.show_available_decks_check,
        dialog.shortcuts_page.tree,
    ]
    if dialog.hardware_acceleration_check:
        controls.append(dialog.hardware_acceleration_check)
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


def test_the_dialog_opens_on_the_page_it_was_left_on(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.page_list.currentRow() == 0

    background = dialog.page_keys().index("background")
    dialog.page_list.setCurrentRow(background)
    dialog.reject()

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert reopened.page_list.currentRow() == background
    assert reopened.page_stack.currentIndex() == background
    assert reopened.page_title.text() == reopened.page_list.item(background).text()


def test_a_page_this_build_lacks_opens_the_first(qtbot):
    get_settings().setValue(PREFERENCES_PAGE_KEY, "no-such-page")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.page_list.currentRow() == 0


def test_each_type_shows_only_its_own_colour_row(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    form = dialog.background_form.rows

    for key, _label in background_form.BACKGROUND_STYLE_LABELS:
        dialog.background_form.bg_combo.setCurrentIndex(
            dialog.background_form.bg_combo.findData(key)
        )
        assert form.isRowVisible(dialog.background_form.solid_color_btn) is (key == "solid")
        assert form.isRowVisible(dialog.background_form.checkerboard_color_btn) is (
            key == "checkerboard"
        )
        assert form.isRowVisible(dialog.background_form.bg_combo)


def test_the_type_combo_keeps_its_width_as_rows_come_and_go(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.page_list.setCurrentRow(dialog.page_keys().index("background"))

    widths = set()
    for key, _label in background_form.BACKGROUND_STYLE_LABELS:
        dialog.background_form.bg_combo.setCurrentIndex(
            dialog.background_form.bg_combo.findData(key)
        )
        dialog.page_stack.currentWidget().layout().activate()
        widths.add(dialog.background_form.bg_combo.geometry().getRect())

    assert len(widths) == 1


def test_a_load_shows_the_stored_types_rows(qtbot):
    get_settings().setValue(BACKGROUND_STYLE_KEY, "checkerboard")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    form = dialog.background_form.rows
    assert form.isRowVisible(dialog.background_form.checkerboard_color_btn)
    assert not form.isRowVisible(dialog.background_form.solid_color_btn)

    dialog.restore_defaults()

    assert dialog.background_form.bg_combo.currentData() == BACKGROUND_STYLE_DEFAULT
    assert form.isRowVisible(dialog.background_form.solid_color_btn) is (
        BACKGROUND_STYLE_DEFAULT == "solid"
    )
    assert form.isRowVisible(dialog.background_form.checkerboard_color_btn) is (
        BACKGROUND_STYLE_DEFAULT == "checkerboard"
    )


def test_each_colour_button_edits_only_its_own_colour(qtbot, monkeypatch):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    picked = []
    answers = iter([QColor("#335544"), QColor("#aa2211")])
    monkeypatch.setattr(
        "tarot_canvas.ui.windows.background_form.QColorDialog.getColor",
        lambda initial, parent: picked.append(QColor(initial)) or next(answers),
    )

    dialog.background_form.checkerboard_color_btn.click()
    assert picked[-1] == QColor(CHECKERBOARD_COLOR_DEFAULT)
    assert dialog.background_form.checkerboard_color == QColor("#335544")
    assert dialog.background_form.bg_color == QColor(BACKGROUND_COLOR_DEFAULT)

    dialog.background_form.solid_color_btn.click()
    assert picked[-1] == QColor(BACKGROUND_COLOR_DEFAULT)
    assert dialog.background_form.bg_color == QColor("#aa2211")
    assert dialog.background_form.checkerboard_color == QColor("#335544")

    dialog.apply_settings()
    assert get_settings().value(CHECKERBOARD_COLOR_KEY) == "#335544"
    assert get_settings().value(BACKGROUND_COLOR_KEY) == "#aa2211"


def test_a_cancelled_colour_dialog_changes_nothing(qtbot, monkeypatch):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    monkeypatch.setattr(
        "tarot_canvas.ui.windows.background_form.QColorDialog.getColor",
        lambda initial, parent: QColor(),
    )

    dialog.background_form.solid_color_btn.click()
    dialog.background_form.checkerboard_color_btn.click()

    assert dialog.background_form.bg_color == QColor(BACKGROUND_COLOR_DEFAULT)
    assert dialog.background_form.checkerboard_color == QColor(CHECKERBOARD_COLOR_DEFAULT)
    assert not dialog.apply_button.isEnabled()


def test_the_checkerboard_colour_is_stored_and_shown_again(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.background_form.set_checkerboard_color(QColor("#335544"))
    assert dialog.apply_button.isEnabled()

    dialog.accept()

    assert get_settings().value(CHECKERBOARD_COLOR_KEY) == "#335544"
    assert get_settings().value(BACKGROUND_COLOR_KEY) == BACKGROUND_COLOR_DEFAULT
    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert reopened.background_form.checkerboard_color == QColor("#335544")


def test_apply_is_offered_only_while_the_form_differs_from_what_is_stored(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert not dialog.apply_button.isEnabled()

    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData("Off"))
    assert dialog.apply_button.isEnabled()

    dialog.motion_combo.setCurrentIndex(dialog.motion_combo.findData(MOTION_LEVEL_DEFAULT))
    assert not dialog.apply_button.isEnabled()

    dialog.background_form.set_bg_color(QColor("#ffffff"))
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
    settings.setValue(CANVAS_GUIDES_KEY, True)
    settings.setValue(SHOW_AVAILABLE_DECKS_KEY, False)
    settings.setValue(SHOW_WELCOME_KEY, False)
    settings.setValue(READING_TEXT_SCALE_KEY, 150)
    settings.setValue(HARDWARE_ACCELERATION_KEY, False)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    stored = {key: settings.value(key) for key in settings.allKeys()}

    dialog.restore_defaults()

    assert dialog.form_state()[:-1] == (
        "system",
        READING_TEXT_SCALE_DEFAULT,
        Ground(),
        (),
        MOTION_LEVEL_DEFAULT,
        True,
        False,
        True,
        True,
        True,
    )
    assert dialog.apply_button.isEnabled()
    assert {key: settings.value(key) for key in settings.allKeys()} == stored
    assert theme_kept.get_current_theme() is ThemeType.DARK


def test_ok_stores_keys_not_labels(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.background_form.bg_combo.setCurrentIndex(
        dialog.background_form.bg_combo.findData("solid")
    )
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
    assert dialog.background_form.bg_combo.currentData() == "gradient"

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
    assert dialog.background_form.bg_combo.currentData() == "checkerboard"

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
    dialog.background_form.bg_combo.setCurrentIndex(
        dialog.background_form.bg_combo.findData("solid")
    )
    dialog.apply_settings()

    settings = get_settings()
    assert settings.value(BACKGROUND_STYLE_KEY) == "solid"

    # The canvas tab's brush must reflect the new choice
    assert canvas_tab.view.backgroundBrush().color() == dialog.background_form.bg_color

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


def test_the_snap_switch_round_trips(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert not dialog.canvas_guides_check.isChecked()

    dialog.canvas_guides_check.setChecked(True)
    assert dialog.apply_button.isEnabled()
    dialog.apply_settings()
    assert get_settings().value(CANVAS_GUIDES_KEY, type=bool) is True

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert reopened.canvas_guides_check.isChecked()


def test_applying_the_snap_switch_reaches_an_open_canvas(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    canvas_tab = window.new_canvas_tab()
    assert not canvas_tab.snap_guides

    dialog = PreferencesDialog(window)
    qtbot.addWidget(dialog)
    dialog.settings_changed.connect(window.apply_settings_to_open_canvases)
    dialog.canvas_guides_check.setChecked(True)
    dialog.apply_settings()

    assert canvas_tab.snap_guides
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


def test_the_background_page_follows_the_canvas_page(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    keys = dialog.page_keys()

    assert keys[keys.index("canvas") + 1] == "background"


def test_the_advanced_page_is_linux_only(qtbot, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    linux = PreferencesDialog()
    qtbot.addWidget(linux)
    assert linux.page_keys()[-1] == "advanced"
    monkeypatch.setattr(sys, "platform", "darwin")
    mac = PreferencesDialog()
    qtbot.addWidget(mac)

    assert "advanced" not in mac.page_keys()
    assert mac.page_stack.count() == len(mac.page_keys())
    mac.restore_defaults()
    mac.apply_settings()
    assert get_settings().value(HARDWARE_ACCELERATION_KEY) is None


@pytest.fixture
def cleared(monkeypatch):
    calls = []
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(preferences_dialog, "clear_marker", lambda: calls.append(True))
    return calls


def test_turning_hardware_acceleration_off_is_stored_and_keeps_the_marker(qtbot, cleared):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    dialog.hardware_acceleration_check.setChecked(False)
    dialog.apply_settings()

    assert get_settings().value(HARDWARE_ACCELERATION_KEY, type=bool) is False
    assert cleared == []


def test_turning_hardware_acceleration_back_on_clears_the_marker(qtbot, cleared):
    get_settings().setValue(HARDWARE_ACCELERATION_KEY, False)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert not dialog.hardware_acceleration_check.isChecked()

    dialog.hardware_acceleration_check.setChecked(True)
    assert dialog.apply_button.isEnabled()
    dialog.apply_settings()

    assert get_settings().value(HARDWARE_ACCELERATION_KEY, type=bool) is True
    assert cleared == [True]


def write_background(base, name, colour="#c03030"):
    image = QImage(QSize(48, 32), QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    base.mkdir(parents=True, exist_ok=True)
    assert image.save(str(base / name))
    return base / name


def choose_type(dialog, key):
    dialog.background_form.bg_combo.setCurrentIndex(dialog.background_form.bg_combo.findData(key))
    dialog.background_form.bg_combo.activated.emit(dialog.background_form.bg_combo.currentIndex())


def test_the_image_type_shows_its_rows_and_the_fill_only_where_it_shows(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    form = dialog.background_form.rows
    image_rows = (
        dialog.background_form.positioning_combo,
        dialog.background_form.images_header,
        dialog.background_form.background_grid,
    )

    for key, _label in background_form.BACKGROUND_STYLE_LABELS:
        choose_type(dialog, key)
        for row in image_rows:
            assert form.isRowVisible(row) is (key == "image")

    choose_type(dialog, "image")
    for key, _label in background_form.POSITIONING_LABELS:
        dialog.background_form.positioning_combo.setCurrentIndex(
            dialog.background_form.positioning_combo.findData(key)
        )
        assert form.isRowVisible(dialog.background_form.fill_color_btn) is (
            key in ("fit", "center")
        )


def test_added_files_are_copied_selected_and_stored_on_apply(
    qtbot, tmp_path, backgrounds_base, monkeypatch
):
    picked = [
        str(write_background(tmp_path / "picked", "wood.png")),
        str(write_background(tmp_path / "picked", "felt.png")),
    ]
    monkeypatch.setattr(
        "tarot_canvas.ui.windows.background_form.QFileDialog.getOpenFileNames",
        lambda *args: (picked, ""),
    )
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    dialog.background_form.add_image_btn.click()

    assert sorted(path.name for path in backgrounds_base.iterdir()) == ["felt.png", "wood.png"]
    assert dialog.background_form.background_grid.names() == ["felt.png", "wood.png"]
    assert dialog.background_form.background_grid.selected_name() == "felt.png"
    assert dialog.background_form.bg_combo.currentData() == "image"
    assert dialog.apply_button.isEnabled()

    dialog.apply_settings()

    assert get_settings().value(BACKGROUND_STYLE_KEY) == "image"
    assert get_settings().value(BACKGROUND_IMAGE_KEY) == "felt.png"


def test_files_dropped_on_the_grid_are_added(qtbot, tmp_path, backgrounds_base):
    source = write_background(tmp_path, "cloth.png")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    grid = dialog.background_form.background_grid
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(source))])
    position = QPointF(grid.viewport().rect().center())
    actions = Qt.DropAction.CopyAction
    buttons, modifiers = Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier

    enter = QDragEnterEvent(position.toPoint(), actions, mime, buttons, modifiers)
    QApplication.sendEvent(grid.viewport(), enter)
    assert enter.isAccepted()
    QApplication.sendEvent(grid.viewport(), QDropEvent(position, actions, mime, buttons, modifiers))

    assert grid.names() == ["cloth.png"]
    assert grid.selected_name() == "cloth.png"


def test_choosing_image_with_none_selected_selects_the_first(qtbot, backgrounds_base):
    write_background(backgrounds_base, "b.png")
    write_background(backgrounds_base, "a.png")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.background_form.background_grid.selected_name() == ""

    choose_type(dialog, "image")

    assert dialog.background_form.background_grid.selected_name() == "a.png"


def test_the_stored_image_is_shown_selected(qtbot, backgrounds_base):
    for name in ("a.png", "b.png", "c.png"):
        write_background(backgrounds_base, name)
    get_settings().setValue(BACKGROUND_STYLE_KEY, "image")
    get_settings().setValue(BACKGROUND_IMAGE_KEY, "b.png")

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    assert dialog.background_form.background_grid.selected_name() == "b.png"
    assert not dialog.apply_button.isEnabled()


def test_an_undecodable_copy_gets_no_tile(qtbot, backgrounds_base):
    write_background(backgrounds_base, "good.png")
    (backgrounds_base / "bad.png").write_text("not an image")

    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    assert dialog.background_form.background_grid.names() == ["good.png"]


def test_removing_waits_for_apply_and_moves_the_selection_on(qtbot, backgrounds_base):
    for name in ("a.png", "b.png", "c.png"):
        write_background(backgrounds_base, name)
    get_settings().setValue(BACKGROUND_STYLE_KEY, "image")
    get_settings().setValue(BACKGROUND_IMAGE_KEY, "b.png")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    grid = dialog.background_form.background_grid

    grid.toggle_removal("b.png")

    assert grid.pending() == ("b.png",)
    assert grid.selected_name() == "c.png"
    assert (backgrounds_base / "b.png").exists()
    assert dialog.apply_button.isEnabled()

    dialog.apply_settings()

    assert not (backgrounds_base / "b.png").exists()
    assert grid.names() == ["a.png", "c.png"]
    assert get_settings().value(BACKGROUND_IMAGE_KEY) == "c.png"
    assert not dialog.apply_button.isEnabled()


def test_an_undone_removal_offers_no_apply(qtbot, backgrounds_base):
    write_background(backgrounds_base, "a.png")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    dialog.background_form.background_grid.toggle_removal("a.png")
    dialog.background_form.background_grid.toggle_removal("a.png")

    assert dialog.background_form.background_grid.pending() == ()
    assert not dialog.apply_button.isEnabled()


def test_cancel_removes_nothing(qtbot, backgrounds_base):
    write_background(backgrounds_base, "a.png")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    dialog.background_form.background_grid.toggle_removal("a.png")
    dialog.reject()

    assert (backgrounds_base / "a.png").exists()


def test_a_tiles_remove_button_marks_it_without_selecting_it(qtbot, backgrounds_base):
    write_background(backgrounds_base, "a.png")
    write_background(backgrounds_base, "b.png")
    get_settings().setValue(BACKGROUND_STYLE_KEY, "image")
    get_settings().setValue(BACKGROUND_IMAGE_KEY, "a.png")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.page_list.setCurrentRow(dialog.page_keys().index("background"))
    qtbot.waitExposed(dialog)
    grid = dialog.background_form.background_grid
    index = grid.model().index(1, 0)
    cell = grid.visualRect(index)
    (action, rect), *_ = grid.delegate.action_rects(cell, False)
    assert action == "remove"

    qtbot.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())

    assert grid.pending() == ("b.png",)
    assert grid.selected_name() == "a.png"


def test_the_background_types_are_offered_in_order(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    combo = dialog.background_form.bg_combo
    assert [combo.itemData(i) for i in range(combo.count())] == [
        "gradient",
        "swirl",
        "image",
        "checkerboard",
        "solid",
    ]


@pytest.fixture
def no_thumbnails(monkeypatch):
    from tarot_canvas.ui.windows import background_grid

    monkeypatch.setattr(background_grid, "_thumbnails", {})
    return background_grid


def tile_pixmap(grid, name):
    return grid.model_.item(grid.names().index(name)).data(Qt.ItemDataRole.DecorationRole)


def test_the_dialog_opens_before_a_thumbnail_is_decoded(
    qtbot, backgrounds_base, monkeypatch, no_thumbnails
):
    # A large PNG decodes in full whatever size is asked for: never on the GUI thread
    write_background(backgrounds_base, "big.png")
    decodes = []
    monkeypatch.setattr(
        no_thumbnails,
        "art_loader",
        lambda: type("L", (), {"request": lambda *a: decodes.append(a)}),
    )
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)

    grid = dialog.background_form.background_grid
    assert grid.names() == ["big.png"]
    assert tile_pixmap(grid, "big.png") is None
    assert grid.is_loading()
    assert len(decodes) == 1


def test_a_thumbnail_lands_cropped_and_a_reopen_takes_it_from_the_cache(
    qtbot, backgrounds_base, no_thumbnails
):
    write_background(backgrounds_base, "a.png", "#c03030")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    grid = dialog.background_form.background_grid
    qtbot.waitUntil(lambda: not grid.is_loading())

    pixmap = tile_pixmap(grid, "a.png")
    tile = grid.delegate.tile
    ratio = grid.devicePixelRatioF()
    assert pixmap.size() == QSize(round(tile.width() * ratio), round(tile.height() * ratio))
    assert pixmap.toImage().pixelColor(2, 2) == QColor("#c03030")

    reopened = PreferencesDialog()
    qtbot.addWidget(reopened)
    assert not reopened.background_form.background_grid.is_loading()
    assert (
        tile_pixmap(reopened.background_form.background_grid, "a.png").cacheKey()
        == pixmap.cacheKey()
    )


def test_an_edited_image_is_thumbnailed_again(qtbot, backgrounds_base, no_thumbnails):
    import os

    path = write_background(backgrounds_base, "a.png", "#c03030")
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: not dialog.background_form.background_grid.is_loading())

    write_background(backgrounds_base, "a.png", "#30c030")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    grid = dialog.background_form.background_grid
    grid.reload()
    assert grid.is_loading()
    qtbot.waitUntil(lambda: not grid.is_loading())
    assert tile_pixmap(grid, "a.png").toImage().pixelColor(2, 2) == QColor("#30c030")
