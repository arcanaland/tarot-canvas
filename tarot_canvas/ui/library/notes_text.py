NOTES_TEXT = {
    "view_name": "Notes",
    "search_placeholder": "Search notes…",  # TODO(adam)
    "details_toggle_show": "Show details (Ctrl+I)",  # TODO(adam)
    "details_toggle_hide": "Hide details (Ctrl+I)",  # TODO(adam)
    "empty_nothing_written": "No notes created yet.",  # TODO(adam)
    "empty_no_match": "Nothing found.",
    "no_notes_on_card": "Nothing for this card.",
    "stub_note": "(empty)",
    "open_card": "Open note",
    "relative_date": "{date}",
}


def text(key):
    """The string for `key`, or "" while Adam hasn't written it."""
    return NOTES_TEXT.get(key) or ""
