NOTES_TEXT = {
    "section_heading": "Personal Notes",
    "new_note_tooltip": "Create a new note.",
    "name_placeholder": "Name this note…",
    "stub_note": "(empty)",
}


# for keeping slop out (and maybe translation in the future)
def text(key):
    return NOTES_TEXT.get(key) or ""
