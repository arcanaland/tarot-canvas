import tomllib
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
METAINFO = REPO / "tarot_canvas" / "resources" / "land.arcana.TarotCanvas.appdata.xml"
DESKTOP = REPO / "packaging" / "land.arcana.TarotCanvas.desktop"
PYPROJECT = REPO / "pyproject.toml"


def _metainfo():
    return ET.parse(METAINFO).getroot()


def _desktop_entry():
    entries = {}
    for line in DESKTOP.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith(("#", "[")):
            key, _, value = line.partition("=")
            entries[key.strip()] = value.strip()
    return entries


def _pyproject():
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_metainfo_is_in_the_package():
    assert METAINFO.exists()


def test_taglines_agree():
    summary = _metainfo().findtext("summary").strip()

    assert _desktop_entry()["Comment"] == summary
    assert _pyproject()["project"]["description"] == summary


def test_version_agrees_between_pyproject_and_version_module():
    from tarot_canvas._version import __version__

    assert _pyproject()["project"]["version"] == __version__
