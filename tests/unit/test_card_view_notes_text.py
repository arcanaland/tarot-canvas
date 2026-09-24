"""Every string a person reads is Adam's, or is visibly a placeholder for his."""

from tarot_canvas.ui.notes_text import NOTES_TEXT

OPEN_TAG = "<clankertext>"
CLOSE_TAG = "</clankertext>"

# The keys whose strings Adam wrote. A key joins this set when he replaces its
# placeholder, and not before.
WRITTEN_BY_ADAM = {
    "section_heading",
    "new_note_tooltip",
    "name_placeholder",
    "stub_note",
    "view_name",
    "search_placeholder",
    "details_toggle_show",
    "details_toggle_hide",
    "empty_nothing_written",
    "empty_no_match",
    "no_notes_on_card",
    "open_card",
    "new_note",
    "create_note",
    "rename",
    "delete",
    "export",
}


def untagged(strings, written):
    return sorted(
        key
        for key, value in strings.items()
        if key not in written
        and value
        and not (value.startswith(OPEN_TAG) and value.endswith(CLOSE_TAG))
    )


def test_every_string_not_written_by_adam_is_a_tagged_placeholder():
    assert untagged(NOTES_TEXT, WRITTEN_BY_ADAM) == []


def test_an_untagged_new_string_is_caught():
    strings = {**NOTES_TEXT, "new_key": "Finished-looking copy"}

    assert untagged(strings, WRITTEN_BY_ADAM) == ["new_key"]


def test_a_tag_that_does_not_wrap_the_whole_string_is_caught():
    strings = {"half": f"{OPEN_TAG}Undo{CLOSE_TAG} this", "open": f"Undo {OPEN_TAG}"}

    assert untagged(strings, set()) == ["half", "open"]


def test_the_placeholders_are_not_empty_inside_their_tags():
    placeholders = [v for k, v in NOTES_TEXT.items() if k not in WRITTEN_BY_ADAM and v]

    assert all(v.removeprefix(OPEN_TAG).removesuffix(CLOSE_TAG).strip() for v in placeholders)
