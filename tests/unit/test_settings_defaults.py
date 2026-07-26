import re

from tarot_canvas.ui.tabs import canvas_tab
from tarot_canvas.ui.windows import preferences_dialog


def test_background_style_default_agrees():
    dialog_default = re.search(
        r'settings\.value\("appearance/background_style", "([^"]+)"',
        _source(preferences_dialog),
    ).group(1)

    canvas_default = re.search(
        r'settings\.value\("appearance/background_style", "([^"]+)"',
        _source(canvas_tab),
    ).group(1)

    assert dialog_default == canvas_default


def _source(module):
    with open(module.__file__) as f:
        return f.read()
