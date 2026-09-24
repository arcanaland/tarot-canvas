NOTES_TEXT = {
    "section_heading": "Personal Notes",
    "new_note_tooltip": "Create a new note.",
    "name_placeholder": "Name this note…",
    "stub_note": "(empty)",
    "view_name": "Notes",
    "search_placeholder": "Search notes…",  # TODO(adam)
    "details_toggle_show": "Show details (Ctrl+I)",  # TODO(adam)
    "details_toggle_hide": "Hide details (Ctrl+I)",  # TODO(adam)
    "empty_nothing_written": "No notes created yet.",  # TODO(adam)
    "empty_no_match": "Nothing found.",
    "no_notes_on_card": "Nothing for this card.",
    "open_card": "Open note",
}


# for keeping slop out (and maybe translation in the future)
def text(key):
    return NOTES_TEXT.get(key) or ""
