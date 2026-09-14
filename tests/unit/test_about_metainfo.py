import tarot_canvas.about as about_module
from tarot_canvas.about import AboutData, Release, load_about_data, parse_metainfo


def _metainfo(releases: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<component type="desktop-application">
  <id>land.arcana.TarotCanvas</id>
  <releases>
{releases}
  </releases>
</component>"""


def _description(body: str) -> str:
    raw = _metainfo(
        f'<release version="1.0.0" date="2026-01-01"><description>{body}</description></release>'
    )
    return parse_metainfo(raw).releases[0].description


THREE_RELEASES = _metainfo(
    """
    <!--
    <release version="1.5.1" date="2026-09-xx" type="development">
      <description><p>Drafted in a comment.</p></description>
    </release>
    -->
    <release version="1.5.0" date="2026-09-13" type="development">
      <description><p>Next.</p></description>
    </release>
    <release version="1.4.1" date="2026-09-09" type="stable">
      <description><p>Now.</p></description>
    </release>
    <release version="1.4.0" date="2026-09-06">
    </release>
    """
)


def _versions(releases):
    return [release.version for release in releases]


# -- parsing ------------------------------------------------------------------


def test_releases_come_back_in_document_order():
    assert _versions(parse_metainfo(THREE_RELEASES).releases) == ["1.5.0", "1.4.1", "1.4.0"]


def test_a_commented_out_release_is_absent():
    assert "1.5.1" not in _versions(parse_metainfo(THREE_RELEASES).releases)


def test_release_fields():
    release = parse_metainfo(THREE_RELEASES).releases[1]

    assert release == Release("1.4.1", "2026-09-09", "stable", "<p>Now.</p>")


def test_a_missing_type_is_stable_and_a_missing_description_is_empty():
    release = parse_metainfo(THREE_RELEASES).releases[2]

    assert release.type == "stable"
    assert release.description == ""


def test_no_releases_element_gives_no_releases():
    assert parse_metainfo(_metainfo("")).releases == ()


# -- sanitising ---------------------------------------------------------------


def test_unknown_markup_is_flattened_to_its_text():
    assert _description("<p>a <b>bold</b> <em>x</em></p>") == "<p>a bold <em>x</em></p>"


def test_a_script_element_survives_only_as_escaped_text():
    description = _description("<p><script>alert('1' &lt; 2)</script></p>")

    assert "<script" not in description
    assert description == "<p>alert(&#x27;1&#x27; &lt; 2)</p>"


def test_escaped_text_stays_escaped():
    assert _description("<p>a &lt; b &amp; c</p>") == "<p>a &lt; b &amp; c</p>"


def test_attributes_are_dropped():
    assert _description('<p style="x" onclick="y">text</p>') == "<p>text</p>"


def test_nested_allowed_markup_survives_intact():
    body = "<ul><li><code>just run</code> and <em>then</em></li></ul><ol><li>two</li></ol>"

    assert _description(body) == body


def test_a_translated_paragraph_is_skipped():
    body = '<p>English</p><p xml:lang="de">Deutsch</p>'

    assert _description(body) == "<p>English</p>"


def test_the_untranslated_description_is_chosen():
    raw = _metainfo(
        '<release version="1.0.0" date="2026-01-01">'
        '<description xml:lang="de"><p>Deutsch</p></description>'
        "<description><p>English</p></description>"
        "</release>"
    )

    assert parse_metainfo(raw).releases[0].description == "<p>English</p>"


# -- loading the bundled file -------------------------------------------------


def test_malformed_metainfo_falls_back(monkeypatch):
    class Resource:
        def joinpath(self, name):
            return self

        def read_text(self, encoding):
            return "<component><releases>"

    monkeypatch.setattr(about_module, "files", lambda package: Resource())

    assert load_about_data() == AboutData()


def test_the_bundled_metainfo_has_releases():
    assert load_about_data().releases
