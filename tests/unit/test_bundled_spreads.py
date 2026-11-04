import pytest

from tarot_canvas.models import spreads
from tarot_canvas.utils.path_helper import BUNDLED_SPREADS_PATH

# A build with no built-ins has no folder, and nothing to check
ROOT = BUNDLED_SPREADS_PATH if BUNDLED_SPREADS_PATH.is_dir() else None
FOLDERS = sorted(path for path in ROOT.iterdir() if path.is_dir()) if ROOT else []


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda folder: folder.name)
def test_each_included_spread_loads_with_a_name_and_a_position(folder):
    spread = spreads.load(folder)

    assert spread.name.strip()
    assert spread.positions


def test_every_included_folder_is_scanned(monkeypatch):
    monkeypatch.setattr(spreads, "included_base", lambda: BUNDLED_SPREADS_PATH)

    assert [folder for folder, _ in spreads.scan_included()] == FOLDERS
