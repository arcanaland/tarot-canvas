import pytest
from PyQt6.QtGui import QColor

from tarot_canvas.settings import BACKGROUND_STYLE_KEY, GROUND_HUE_KEY, get_settings
from tarot_canvas.ui import strings
from tarot_canvas.ui.canvas import ground, swirl
from tarot_canvas.ui.canvas.ground import GROUND_HUE_DEFAULT, GroundHue
from tarot_canvas.ui.tabs.canvas_tab import CanvasTab
from tarot_canvas.ui.windows import preferences_dialog
from tarot_canvas.ui.windows.preferences_dialog import PreferencesDialog

GREEN = GroundHue(
    swirl=(QColor("#205030"), QColor("#103020"), QColor("#60a070")),
    aura=(QColor("#204020"), QColor("#102010"), QColor("#081008")),
)


@pytest.fixture
def green(monkeypatch):
    """A second preset, named, after the default in swatch order"""
    monkeypatch.setitem(ground.GROUND_HUES, "test_green", GREEN)
    monkeypatch.setitem(strings.PREFERENCES, "hue_test_green", "Green")
    return "test_green"


def make_tab(qtbot):
    tab = CanvasTab()
    qtbot.addWidget(tab)
    tab.show()
    qtbot.waitExposed(tab)
    return tab


def stop_colours(tab):
    return [c for _p, c in tab.view.backgroundBrush().gradient().stops()]


def test_aura_draws_the_stored_hue(qtbot, green):
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "gradient")
    settings.setValue(GROUND_HUE_KEY, green)
    tab = make_tab(qtbot)
    assert stop_colours(tab) == list(GREEN.aura)
    assert tab.gilt is not None


def test_without_gl_the_swirl_falls_back_to_aura_in_the_same_hue(qtbot, monkeypatch, green):
    monkeypatch.setattr(swirl, "field", lambda: None)
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "swirl")
    settings.setValue(GROUND_HUE_KEY, green)
    tab = make_tab(qtbot)
    assert tab.view.swirl is None
    assert stop_colours(tab) == list(GREEN.aura)


class _Field:
    def __init__(self):
        self.values = None

    def render(self, t, size, values, centre, scale):
        from PyQt6.QtGui import QImage

        self.values = values
        image = QImage(size, QImage.Format.Format_RGB32)
        image.fill(values["colour_1"])
        return image


def test_the_swirl_renders_the_stored_hue_and_its_brush_is_colour_1(qtbot, monkeypatch, green):
    field = _Field()
    monkeypatch.setattr(swirl, "field", lambda: field)
    settings = get_settings()
    settings.setValue(BACKGROUND_STYLE_KEY, "swirl")
    settings.setValue(GROUND_HUE_KEY, green)
    tab = make_tab(qtbot)
    qtbot.waitUntil(lambda: field.values is not None)
    assert [field.values[f"colour_{n}"] for n in (1, 2, 3)] == list(GREEN.swirl)
    assert tab.view.backgroundBrush().color() == GREEN.swirl[0]

    # Back to the default, live, on the same SwirlGround
    settings.setValue(GROUND_HUE_KEY, GROUND_HUE_DEFAULT)
    ground_before = tab.view.swirl
    field.values = None
    tab.apply_background_settings()
    qtbot.waitUntil(lambda: field.values is not None)
    assert tab.view.swirl is ground_before
    assert field.values["colour_1"] == ground.GROUND_HUES[GROUND_HUE_DEFAULT].swirl[0]


def test_the_hue_row_shows_for_aura_and_swirl_only(qtbot):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    form = dialog.background_form
    for key, _label in preferences_dialog.BACKGROUND_STYLE_LABELS:
        dialog.bg_combo.setCurrentIndex(dialog.bg_combo.findData(key))
        assert form.isRowVisible(dialog.hue_row) is (key in ("gradient", "swirl"))


def test_each_swatch_is_named_and_one_is_checked(qtbot, green):
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert next(iter(dialog.hue_buttons)) == GROUND_HUE_DEFAULT
    assert list(dialog.hue_buttons)[-1] == green
    assert len(dialog.hue_buttons) == len(ground.GROUND_HUES)
    assert dialog.hue_buttons[green].toolTip() == "Green"
    assert dialog.hue_buttons[green].accessibleName() == "Green"
    assert dialog.selected_hue() == GROUND_HUE_DEFAULT
    assert sum(b.isChecked() for b in dialog.hue_buttons.values()) == 1


def test_a_swatch_offers_apply_stores_its_id_and_reaches_the_canvas(qtbot, green):
    get_settings().setValue(BACKGROUND_STYLE_KEY, "gradient")
    tab = make_tab(qtbot)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    dialog.settings_changed.connect(tab.apply_background_settings)
    assert not dialog.apply_button.isEnabled()

    dialog.hue_buttons[green].click()
    assert dialog.apply_button.isEnabled()
    dialog.apply_settings()

    assert get_settings().value(GROUND_HUE_KEY) == green
    assert stop_colours(tab) == list(GREEN.aura)
    assert not dialog.apply_button.isEnabled()


def test_the_stored_hue_is_shown_and_restore_defaults_goes_back(qtbot, green):
    get_settings().setValue(GROUND_HUE_KEY, green)
    dialog = PreferencesDialog()
    qtbot.addWidget(dialog)
    assert dialog.selected_hue() == green

    dialog.restore_defaults()
    assert dialog.selected_hue() == GROUND_HUE_DEFAULT
    assert get_settings().value(GROUND_HUE_KEY) == green
