from tarot_canvas.models.deck_types import DeckLink, DeckMetadata
from tarot_canvas.ui.library.decks.header import (
    DETAIL_FIELDS,
    buy_link,
    detail_rows,
    format_date,
    format_value,
)

EXAMPLE_TAROT_LINKS = (
    DeckLink("homepage", "https://example-tarot.com"),
    DeckLink("artist", "https://example.org"),
    DeckLink("buy", "https://example.com/shop"),
    DeckLink("source", "https://github.com/example/example-tarot"),
)


def rows(name="N", **fields):
    return detail_rows(DeckMetadata(name=name, **fields))


def test_the_minimal_deck_leaves_its_optional_fields_empty(minimal_deck):
    metadata = minimal_deck.metadata
    assert metadata.name == "Minimal Test Deck"
    assert metadata.version == "1.0.0"
    for field in (
        "artist",
        "license",
        "attribution",
        "publisher",
        "website",
        "created_date",
        "updated_date",
    ):
        assert getattr(metadata, field) is None, field
    assert metadata.schema_version == "2.0"
    assert metadata.tags == ()


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
        "attribution": "Pamela Colman Smith",
        "license": "CC0",
        "name": "Rider-Waite-Smith",
    }
    assert [label for label, _, _ in rows(**fields)] == ["License", "Attribution"]


def test_detail_rows_omit_what_the_collapsed_rows_already_show():
    keys = [key for _, _, key in rows(name="N", artist="A")]
    assert keys == []


def test_the_description_leads_the_form_and_the_version_is_in_it():
    keys = [key for _, _, key in rows(version="1.1", description="d")]
    assert keys == ["description", "version"]


def test_dates_are_rendered_in_the_readers_locale():
    shown = dict((key, value) for _, value, key in rows(created_date="1909-12-01"))
    assert shown["created_date"] != "1909-12-01"
    assert "1909" in shown["created_date"]
    assert "December" in shown["created_date"] or "12" in shown["created_date"]


def test_a_date_qt_cannot_parse_is_passed_through_as_written(qapp):
    assert format_date("1909") == "1909"
    assert format_date("sometime in 1909") == "sometime in 1909"
    assert format_date("2025-05-04") != "2025-05-04"


def test_the_formatted_date_carries_no_weekday(qapp):
    assert "day," not in format_date("1909-12-01")


def test_unlabelled_keys_are_not_rendered():
    assert rows(license="CC0", identifier="me/x", pattern="me/p") == [("License", "CC0", "license")]


def test_schema_2_0_deck_fields_are_shown_or_suppressed_deliberately():
    shown = rows(
        artist="Jane Doe",
        copyright="Copyright (c)  Jane Doe 2026",
        published_date="2020",
        identifier="org.example/deck/example-tarot",
    )
    labels = [label for label, _, _ in shown]
    assert labels == ["Copyright", "Published"]


def test_every_declared_field_has_a_human_label():
    assert all(label and label != key for key, label in DETAIL_FIELDS)


def test_each_link_rel_is_a_row_showing_its_address():
    shown = rows(license="MIT", links=EXAMPLE_TAROT_LINKS, published_date="2020")
    assert [(label, text) for label, text, _ in shown] == [
        ("License", "MIT"),
        ("Homepage", "example-tarot.com"),
        ("Artist", "example.org"),
        ("Buy", "example.com/shop"),
        ("Source", "github.com/example/example-tarot"),
        ("Published", "2020"),
    ]


def test_links_sharing_a_rel_share_a_row():
    links = (
        DeckLink("buy", "https://a.example"),
        DeckLink("buy", "https://b.example/"),
    )
    assert rows(links=links) == [("Buy", "a.example\nb.example", "links.buy")]


def test_a_publisher_link_joins_the_publisher_row():
    fields = {
        "publisher": "Example Press",
        "links": (DeckLink("publisher", "https://example.com"),),
    }
    assert rows(**fields) == [("Publisher", "Example Press\nexample.com", "publisher")]


def test_an_unregistered_rel_is_not_a_row():
    links = (
        DeckLink("x-shop", "https://example.com/x"),
        DeckLink("buy", "https://example.com/shop"),
    )
    assert [key for _, _, key in rows(links=links)] == ["links.buy"]


def test_the_buy_link_is_the_first_declared():
    links = (
        DeckLink("homepage", "https://h.example"),
        DeckLink("buy", "https://one.example", "Buy from the artist"),
        DeckLink("buy", "https://two.example"),
    )
    assert buy_link(DeckMetadata(name="N", links=links)) == (
        "https://one.example",
        "Buy from the artist",
    )
    assert buy_link(DeckMetadata(name="N")) is None
