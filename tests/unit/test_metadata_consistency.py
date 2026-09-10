"""Guard the two metadata fields that cannot be derived from the metainfo XML.

`Comment=` in the desktop entry and `description` in `pyproject.toml` are read by
tooling that cannot parse our AppStream file, so they stay hand-written. Everything
else the about dialog shows comes from the metainfo (see `tarot_canvas/about.py`);
these two get a detector instead, which fails in the PR diff rather than at release
time. RFC-031.

Stdlib only -- no Qt, so it runs even when the GUI harness is skipped.
"""

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
    """It moved out of packaging/ so the app can read the file it ships."""
    assert METAINFO.exists()


def test_taglines_agree():
    summary = _metainfo().findtext("summary").strip()

    assert _desktop_entry()["Comment"] == summary
    assert _pyproject()["project"]["description"] == summary


def test_maintainer_address_agrees():
    contact = _metainfo().findtext("update_contact").strip()

    authors = _pyproject()["project"]["authors"]
    assert [author["email"] for author in authors] == [contact]


def test_developer_name_agrees():
    developer = _metainfo().findtext("developer/name").strip()

    authors = _pyproject()["project"]["authors"]
    assert [author["name"] for author in authors] == [developer]


def test_project_license_agrees():
    assert _pyproject()["project"]["license"] == _metainfo().findtext("project_license").strip()


def test_version_agrees_between_pyproject_and_version_module():
    """`release.sh` refuses to tag unless these agree; assert it in the diff too."""
    from tarot_canvas._version import __version__

    assert _pyproject()["project"]["version"] == __version__
