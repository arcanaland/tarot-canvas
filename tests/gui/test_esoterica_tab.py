from types import SimpleNamespace

import pytest
from PyQt6.QtWidgets import QLabel

from tarot_canvas.models.esoterica import Passage
from tarot_canvas.ui.tabs.card_view import esoterica_tab
from tarot_canvas.ui.tabs.card_view.esoterica_tab import EsotericaTab, PassageWidget

CARD = {"name": "The Star", "id": "major_arcana.17", "type": "major_arcana", "number": 17}


@pytest.fixture
def stub_manager(monkeypatch):
    """Nothing in this file may touch the user's esoterica directory."""

    def _apply(passages):
        manager = SimpleNamespace(get_passages_for_card=lambda _card_id: passages)
        monkeypatch.setattr(esoterica_tab, "get_esoterica_manager", lambda: manager)

    return _apply


def labels(widget):
    return [label.text() for label in widget.findChildren(QLabel)]


def make_widget(qtbot, passage):
    widget = PassageWidget(passage)
    qtbot.addWidget(widget)
    return widget


def test_markup_in_a_passage_is_shown_rather_than_rendered(qtbot):
    widget = make_widget(qtbot, Passage("Notes", None, '<img src="http://evil/x.png">'))

    assert "&lt;img" in labels(widget)[-1]


def test_paragraph_breaks_still_become_markup(qtbot):
    widget = make_widget(qtbot, Passage("Notes", None, "First.\n\nSecond.\nSame paragraph."))

    assert labels(widget)[-1] == "First.<p>Second.<br>Same paragraph."


def test_a_source_with_no_author_gets_no_author_line(qtbot):
    widget = make_widget(qtbot, Passage("my-notes", None, "Body."))

    assert labels(widget) == ["my-notes", "Body."]


def test_a_declared_author_is_credited(qtbot):
    widget = make_widget(qtbot, Passage("Tarot for Change", "Jessica Dore", "Body."))

    assert labels(widget) == ["Tarot for Change", "by Jessica Dore", "Body."]


def test_two_sources_render_as_two_widgets_rather_than_merging(qtbot, stub_manager):
    stub_manager([Passage("A", None, "One."), Passage("B", None, "Two.")])

    tab = EsotericaTab(CARD)
    qtbot.addWidget(tab)

    assert [w.findChildren(QLabel)[0].text() for w in tab.passage_widgets] == ["A", "B"]


def test_a_card_with_nothing_written_about_it_says_so(qtbot, stub_manager):
    stub_manager([])

    tab = EsotericaTab(CARD)
    qtbot.addWidget(tab)

    assert tab.passage_widgets == []
    assert not tab.no_content_label.isHidden()
