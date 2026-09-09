from tarot_canvas.ui.widgets.deck_header import (
    DETAIL_FIELDS,
    detail_rows,
    format_date,
    format_value,
)


def test_reference_style_fields_are_all_exposed(minimal_deck):
    assert minimal_deck.get_name() == "Minimal Test Deck"
    assert minimal_deck.get_version() == "1.0.0"
    for accessor in (
        "get_author",
        "get_license",
        "get_attribution",
        "get_publisher",
        "get_website",
        "get_deck_id",
        "get_schema_version",
        "get_created_date",
        "get_updated_date",
    ):
        assert getattr(minimal_deck, accessor)() is None, accessor
    assert minimal_deck.get_tags() == ()


def test_metadata_fields_returns_a_copy(minimal_deck):
    fields = minimal_deck.get_metadata_fields()
    fields["name"] = "mutated"
    assert minimal_deck.get_name() == "Minimal Test Deck"


def test_tags_survive_as_a_tuple_of_strings(minimal_deck):
    minimal_deck._metadata["deck"]["tags"] = ["classic", "", "reference"]
    assert minimal_deck.get_tags() == ("classic", "reference")


def test_blank_strings_read_as_absent(minimal_deck):
    minimal_deck._metadata["deck"]["license"] = ""
    assert minimal_deck.get_license() is None


def test_format_value_renders_scalars_and_lists():
    assert format_value("CC0") == "CC0"
    assert format_value(["a", "b"]) == "a, b"
    assert format_value(0.569) == "0.569"
    assert format_value(True) == "Yes"


def test_format_value_drops_empties_and_sub_tables():
    assert format_value(None) is None
    assert format_value("   ") is None
    assert format_value([]) is None
    assert format_value({"cards": ["major_arcana.00"]}) is None


def test_detail_rows_follow_the_declared_order():
    fields = {
        "id": "rws",
        "attribution": "Pamela Colman Smith",
        "license": "CC0",
        "name": "Rider-Waite-Smith",
    }
    assert [label for label, _, _ in detail_rows(fields)] == [
        "License",
        "Attribution",
        "Identifier",
    ]


def test_detail_rows_omit_what_the_collapsed_rows_already_show():
    keys = [key for _, _, key in detail_rows({"name": "N", "author": "A"})]
    assert keys == []


def test_the_description_leads_the_form_and_the_version_is_in_it():
    keys = [key for _, _, key in detail_rows({"version": "1.1", "description": "d"})]
    assert keys == ["description", "version"]


def test_dates_are_rendered_in_the_readers_locale():
    rows = dict((key, value) for _, value, key in detail_rows({"created_date": "1909-12-01"}))
    assert rows["created_date"] != "1909-12-01"
    assert "1909" in rows["created_date"]
    assert "December" in rows["created_date"] or "12" in rows["created_date"]


def test_a_date_qt_cannot_parse_is_passed_through_as_written(qapp):
    assert format_date("1909") == "1909"
    assert format_date("sometime in 1909") == "sometime in 1909"
    assert format_date("2025-05-04") != "2025-05-04"


def test_the_formatted_date_carries_no_weekday(qapp):
    assert "day," not in format_date("1909-12-01")


def test_unlabelled_keys_are_not_rendered():
    rows = detail_rows({"license": "CC0", "aspect_ratio": 0.569, "future_key": "x"})
    assert rows == [("License", "CC0", "license")]


def test_schema_2_0_deck_fields_are_shown_or_suppressed_deliberately():
    rows = detail_rows(
        {
            "artist": "Jane Doe",
            "copyright": "Copyright (c)  Jane Doe 2026",
            "published_date": "2020",
            "identifier": "org.example/deck/example-tarot",
            "packager": "John Doe",
            "pips": "scenic",
            "redistribution": "full",
            "license_files": ["LICENSE"],
        }
    )
    labels = [label for label, _, _ in rows]
    assert labels == ["Copyright", "Published"]


def test_every_declared_field_has_a_human_label():
    assert all(label and label != key for key, label in DETAIL_FIELDS)
