"""What the library's notes view says.

Every constant here is Adam's to write. An empty one hides the element it labels,
so the view ships legible with nothing in it rather than with a machine's words.
The two view names come from the RFC's answered questions and the mockup he took
wholesale, which is why they are the only ones filled in.
"""

NOTES_TEXT = {
    "view_name": "Notes",
    "search_placeholder": "",  # TODO(adam)
    "details_toggle_show": "",  # TODO(adam)
    "details_toggle_hide": "",  # TODO(adam)
    "empty_nothing_written": "",  # TODO(adam)
    "empty_no_match": "",  # TODO(adam)
    "card_id_label": "",  # TODO(adam)
    "notes_group_label": "",  # TODO(adam)
    "no_notes_on_card": "",  # TODO(adam)
    "stub_note": "",  # TODO(adam)
    "open_card": "",  # TODO(adam)
    "relative_date": "",  # TODO(adam)
}


def text(key):
    """The string for `key`, or "" while Adam hasn't written it."""
    return NOTES_TEXT.get(key) or ""
