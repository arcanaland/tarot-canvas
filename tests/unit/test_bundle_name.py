import sys

import pytest

from tarot_canvas.utils.bundle_name import bundle_name, set_bundle_name


def test_off_macos_is_a_no_op():
    set_bundle_name("Tarot Canvas", platform="linux")


@pytest.mark.skipif(sys.platform != "darwin", reason="Cocoa only")
def test_sets_the_main_bundles_name():
    set_bundle_name("Tarot Canvas")
    assert bundle_name() == "Tarot Canvas"
