NOTES_TEXT = {
    "section_heading": "Personal Notes",
    "new_note_tooltip": "Create a new note.",
    "name_placeholder": "Name this note…",
    "stub_note": "(empty)",
    "view_name": "Notes",
    "search_placeholder": "Search notes…",
    "details_toggle_show": "Show details (Ctrl+I)",
    "details_toggle_hide": "Hide details (Ctrl+I)",
    "empty_nothing_written": "No notes created yet.",
    "empty_no_match": "Nothing found.",
    "no_notes_on_card": "Nothing for this card.",
    "open_card": "Open note",
    "new_note": "New Note",
    "create_note": "Create New Note",
    "rename": "Rename Note",
    "delete": "Delete Note",
    "export": "Export Note",
    "open": "Open",
    "empty_heading": "No notes yet.",
    "deleted_message": "Note deleted.",
    "undo": "Undo",
    "dismiss": "Dismiss",
    "note_menu_tooltip": "Manage note…",
}


# for keeping slop out (and maybe translation in the future)
def text(key):
    return NOTES_TEXT.get(key) or ""
