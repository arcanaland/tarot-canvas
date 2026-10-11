import pytest
from PyQt6.QtCore import QItemSelectionModel, Qt
from PyQt6.QtGui import QGuiApplication, QIcon, QPalette
from PyQt6.QtWidgets import QStyleOptionViewItem

from tarot_canvas.models.coverage import CellState
from tarot_canvas.models.esoterica import EsotericaManager
from tarot_canvas.models.esoterica_events import esoterica_events
from tarot_canvas.settings import get_esoterica_disabled, set_esoterica_disabled
from tarot_canvas.ui import esoterica_text
from tarot_canvas.ui.esoterica_text import label_for
from tarot_canvas.ui.library import source_row_delegate
from tarot_canvas.ui.library.deck_model import SubtitleRole
from tarot_canvas.ui.library.esoterica_list_model import (
    CountRole,
    IdentifierRole,
    KindRole,
    RowKind,
)
from tarot_canvas.ui.library.esoterica_page import EsotericaPage
from tarot_canvas.ui.library.source_row_delegate import GENERIC_ICON, type_icon
from tarot_canvas.ui.license_names import license_name
from tests.unit.test_esoterica import every_card, write

FOOL = '[card."major_arcana.00".passages]\ntext = "The Fool."\n'


def source(name, author=None, license="CC0-1.0", extra=""):
    meta = f'[meta]\nname = "{name}"\nlicense = "{license}"\n'
    if author:
        meta += f'author = "{author}"\n'
    return meta + extra + FOOL


@pytest.fixture
def roots(tmp_path):
    return [tmp_path / "user", tmp_path / "bundled"]


@pytest.fixture
def manager(roots):
    user, bundled = roots
    write(user, "zeta.toml", source("zeta notes", "Zed"), identifier="me/zeta")
    write(
        user,
        "alpha.toml",
        source("Alpha Book", "Ann", extra='type = "book"\n'),
        identifier="me/alpha",
    )
    write(user, "anonymous.toml", FOOL, identifier=None)
    write(user, "a-old.toml", '[meta]\nid = "old"\n\n[passages]\ntext = "Old."\n')
    write(bundled, "alpha.toml", source("Alpha Book"), identifier="me/alpha")
    return EsotericaManager(roots)


@pytest.fixture
def page(qtbot, manager):
    page = EsotericaPage(manager)
    qtbot.addWidget(page)
    page.resize(800, 400)
    page.show()
    qtbot.waitExposed(page)
    return page


def rows(page):
    model = page.list_model
    return [
        (model.index(row, 0).data(KindRole), model.index(row, 0).data())
        for row in range(model.rowCount())
    ]


def row_of(page, name):
    model = page.list_model
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        if index.data() == name:
            return index
    raise AssertionError(f"no row {name!r}")


def option_for(page, index):
    view = page.list_view
    option = QStyleOptionViewItem()
    view.initViewItemOption(option)
    option.rect = view.visualRect(index)
    return option


def checkbox_centre(page, index):
    return page.row_delegate._layout(option_for(page, index), index).checkbox.center()


def click_checkbox(qtbot, page, name):
    index = row_of(page, name)
    qtbot.mouseClick(
        page.list_view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=checkbox_centre(page, index),
    )


# -- rows and sections ----------------------------------------------------


def test_installed_sources_sort_by_name_and_skipped_files_follow_by_path(page):
    installed = label_for("library.section.installed")
    not_read = label_for("library.section.not_read")

    assert rows(page) == [
        (RowKind.SECTION, installed),
        (RowKind.SOURCE, "Alpha Book"),
        (RowKind.SOURCE, "zeta notes"),
        (RowKind.SECTION, not_read),
        (RowKind.NOT_READ, "a-old.toml"),
        (RowKind.NOT_READ, "anonymous.toml"),
    ]


def test_a_section_with_no_rows_has_no_heading(qtbot, roots):
    write(roots[0], "only.toml", source("Only"), identifier="me/only")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)

    assert [kind for kind, _ in rows(page)] == [RowKind.SECTION, RowKind.SOURCE]


def test_the_second_line_is_author_and_license_skipping_what_is_absent(page, roots):
    joiner = label_for("joiner")

    cc0 = license_name("CC0-1.0")
    assert row_of(page, "zeta notes").data(SubtitleRole) == f"Zed{joiner}{cc0}"
    # The bundled copy, with no author, is shadowed; the user's copy has one
    assert row_of(page, "Alpha Book").data(SubtitleRole) == f"Ann{joiner}{cc0}"


def test_an_unknown_license_shows_as_written(qtbot, roots):
    write(roots[0], "odd.toml", source("Odd", license="Ask me first"), identifier="me/odd")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)

    assert row_of(page, "Odd").data(SubtitleRole) == "Ask me first"
    page.select("me/odd")
    assert page.details_pane.license_label.text() == "Ask me first"


def test_a_skipped_file_shows_its_reason(page):
    reason = label_for("library.reason.no_identifier")

    assert row_of(page, "anonymous.toml").data(SubtitleRole) == reason


def test_the_count_is_the_cards_the_reader_shows(qtbot, roots):
    write(roots[0], "all.toml", every_card('text = "A."'), identifier="me/all")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)

    assert row_of(page, "all").data(CountRole) == 78


def test_a_section_row_cannot_be_selected(qtbot, page):
    heading = page.list_model.index(0, 0)
    qtbot.mouseClick(
        page.list_view.viewport(),
        Qt.MouseButton.LeftButton,
        pos=page.list_view.visualRect(heading).center(),
    )

    assert heading not in page.list_view.selectionModel().selectedIndexes()
    assert page.list_view.currentIndex() != heading


def test_search_matches_name_author_and_identifier(page):
    page.set_search("ALPHA")
    assert [name for kind, name in rows(page) if kind == RowKind.SOURCE] == ["Alpha Book"]

    page.set_search("zed")
    assert [name for kind, name in rows(page) if kind == RowKind.SOURCE] == ["zeta notes"]

    page.set_search("me/zeta")
    assert [name for kind, name in rows(page) if kind == RowKind.SOURCE] == ["zeta notes"]
    # Neither skipped file matches, so their section goes too
    assert [kind for kind, _ in rows(page)] == [RowKind.SECTION, RowKind.SOURCE]


def test_the_strip_hides_before_the_name_elides(page):
    index = row_of(page, "Alpha Book")
    option = option_for(page, index)
    delegate = page.row_delegate

    wide = delegate._layout(option, index)
    assert not wide.strip.isNull()

    option.rect.setWidth(wide.title.left() + 150)
    narrow = delegate._layout(option, index)
    assert narrow.strip.isNull()
    assert not narrow.checkbox.isNull()


# -- the checkbox ----------------------------------------------------------


def test_unchecking_a_row_turns_its_source_off_and_says_so(qtbot, page):
    with qtbot.waitSignal(esoterica_events().sources_changed, timeout=1000):
        click_checkbox(qtbot, page, "zeta notes")

    assert get_esoterica_disabled() == ["me/zeta"]
    assert row_of(page, "zeta notes").data(Qt.ItemDataRole.CheckStateRole) == (
        Qt.CheckState.Unchecked
    )

    with qtbot.waitSignal(esoterica_events().sources_changed, timeout=1000):
        click_checkbox(qtbot, page, "zeta notes")

    assert get_esoterica_disabled() == []
    assert row_of(page, "zeta notes").data(Qt.ItemDataRole.CheckStateRole) == (
        Qt.CheckState.Checked
    )


def test_space_toggles_the_current_row(qtbot, page):
    index = row_of(page, "Alpha Book")
    page.list_view.setFocus()
    page.list_view.selectionModel().setCurrentIndex(
        index, QItemSelectionModel.SelectionFlag.ClearAndSelect
    )

    qtbot.keyClick(page.list_view, Qt.Key.Key_Space)

    assert get_esoterica_disabled() == ["me/alpha"]


def test_a_toggle_keeps_identifiers_it_did_not_read(qtbot, page):
    set_esoterica_disabled(["x/from-another-machine"])

    click_checkbox(qtbot, page, "zeta notes")

    assert get_esoterica_disabled() == ["x/from-another-machine", "me/zeta"]


def test_a_toggle_reads_no_file_again(qtbot, page, manager, monkeypatch):
    monkeypatch.setattr(manager, "reload", lambda: pytest.fail("reloaded on a toggle"))

    click_checkbox(qtbot, page, "zeta notes")

    assert manager.has_enabled_sources()


def test_a_skipped_file_has_no_checkbox(page):
    index = row_of(page, "anonymous.toml")
    layout = page.row_delegate._layout(option_for(page, index), index)

    assert layout.checkbox.isNull()
    assert layout.strip.isNull()
    assert layout.count.isNull()
    assert index.data(Qt.ItemDataRole.CheckStateRole) is None
    assert not page.list_model.flags(index) & Qt.ItemFlag.ItemIsUserCheckable


def test_a_change_elsewhere_keeps_the_selection(qtbot, page):
    page.select("me/zeta")

    set_esoterica_disabled(["me/alpha"])

    assert page.list_view.currentIndex().data(IdentifierRole) == "me/zeta"
    assert page.details_pane.details().identifier == "me/zeta"


# -- type icons ------------------------------------------------------------


@pytest.fixture
def generic_icons(monkeypatch):
    """The paths type_icon draws the app's own icon from"""
    seen = []

    def recording(path):
        seen.append(path)
        return QIcon()

    monkeypatch.setattr(source_row_delegate, "tinted_icon", recording)
    return seen


@pytest.mark.parametrize("source_type", [None, "reference.book", "x_lecture", "x-lecture", 3])
def test_an_absent_or_unknown_type_gets_the_apps_icon(qapp, source_type, generic_icons):
    type_icon(source_type)

    assert generic_icons == [GENERIC_ICON]


def test_a_known_type_gets_its_theme_icon(qapp, generic_icons, monkeypatch):
    monkeypatch.setattr(source_row_delegate.QIcon, "hasThemeIcon", staticmethod(lambda _: True))

    type_icon("book")

    assert generic_icons == []


def test_a_theme_icon_the_theme_lacks_draws_nothing(qapp, monkeypatch):
    monkeypatch.setitem(source_row_delegate.SOURCE_TYPE_ICONS, "book", "no-such-icon-anywhere")

    assert type_icon("book") is None


def test_with_no_type_icons_every_source_gets_the_apps_icon(qapp, generic_icons, monkeypatch):
    monkeypatch.setattr(source_row_delegate, "SOURCE_TYPE_ICONS", {})

    type_icon("book")

    assert generic_icons == [GENERIC_ICON]


def test_the_apps_icon_takes_the_text_colour_of_a_dark_scheme(qapp, theme_palette):
    """As a monochrome theme icon does, rather than staying black"""
    previous = QGuiApplication.palette()
    palette = QPalette(theme_palette)
    palette.setColor(QPalette.ColorRole.Text, theme_palette.color(QPalette.ColorRole.WindowText))
    QGuiApplication.setPalette(palette)
    try:
        image = type_icon(None).pixmap(64, 64).toImage()
    finally:
        QGuiApplication.setPalette(previous)

    opaque = [
        image.pixelColor(x, y)
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    ]
    assert opaque
    assert {colour.rgb() for colour in opaque} == {palette.color(QPalette.ColorRole.Text).rgb()}


# -- the details pane -------------------------------------------------------

ANNOTATES = """[meta]
name = "Notes on a Book"
author = "The Note Taker"
license = "CC-BY-4.0"
relation = "annotates"
version = "3"
copyright = "(c) The Note Taker"

[meta.work]
name = "A Book"
author = "The Book's Author"
published_date = "1980"
isbn = "0-00-000000-0"
"""


def pane_texts(pane, exclude=None):
    from PyQt6.QtWidgets import QLabel

    labels = pane.findChildren(QLabel)
    excluded = set(exclude.findChildren(QLabel)) if exclude is not None else set()
    return [label.text() for label in labels if label not in excluded and label.isVisibleTo(pane)]


def test_the_works_author_appears_only_in_the_work_group(qtbot, roots):
    write(roots[0], "notes.toml", ANNOTATES + FOOL, identifier="me/notes")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    pane = page.details_pane

    page.select("me/notes")

    assert pane.author_label.text() == "The Note Taker"
    assert pane.work_group.isVisibleTo(pane)
    assert pane.work_author_label.text() == "The Book's Author"
    assert pane.work_name_label.text() == "A Book"
    assert "The Book's Author" not in pane_texts(pane, exclude=pane.work_group)


def test_a_source_with_no_work_has_no_work_group(page):
    page.select("me/zeta")

    assert not page.details_pane.work_group.isVisibleTo(page.details_pane)


def test_the_pane_shows_the_copy_it_shadows(page, roots):
    _, bundled = roots
    page.select("me/alpha")
    pane = page.details_pane

    assert pane.identifier_label.text() == "me/alpha"
    assert pane.shadows_label.text() == str(bundled / "alpha.toml")
    # One card of 78: the grid, not the complete line
    assert pane.coverage_grid.isVisibleTo(pane)
    assert not pane.coverage_complete_label.isVisibleTo(pane)
    assert pane.coverage_grid.states()[0] == CellState.FILLED


def test_a_skipped_files_pane_shows_its_reason(page, roots):
    page.select(roots[0] / "anonymous.toml")
    pane = page.details_pane

    assert pane.heading_label.text() == "anonymous.toml"
    assert pane.author_label.text() == label_for("library.reason.no_identifier")
    assert not pane.coverage_grid.isVisibleTo(pane)
    assert not pane.coverage_complete_label.isVisibleTo(pane)
    assert not pane.identifier_label.isVisibleTo(pane)


def test_a_skipped_file_shows_its_path_and_no_source_file_group(page, roots):
    pane = page.details_pane
    pane.set_source_file_open(True)

    page.select(roots[0] / "anonymous.toml")

    assert pane.file_label.isVisibleTo(pane)
    assert pane.file_label.text() == str(roots[0] / "anonymous.toml")
    assert not pane.source_file_button.isVisibleTo(pane)
    assert not pane.source_file_group.isVisibleTo(pane)


def test_a_read_source_shows_no_path_outside_the_source_file_group(page, roots):
    page.select("me/alpha")
    pane = page.details_pane

    assert not pane.file_label.isVisibleTo(pane)
    assert not any(str(roots[0]) in text for text in pane_texts(pane))


def test_the_source_file_group_starts_closed_and_stays_as_left(page):
    pane = page.details_pane
    page.select("me/alpha")

    assert pane.source_file_button.isVisibleTo(pane)
    assert not pane.identifier_label.isVisibleTo(pane)

    pane.source_file_button.click()
    assert pane.identifier_label.isVisibleTo(pane)

    page.select("me/zeta")
    assert pane.source_file_open()
    assert pane.identifier_label.text() == "me/zeta"
    assert pane.identifier_label.isVisibleTo(pane)

    pane.source_file_button.click()
    page.select("me/alpha")
    assert not pane.identifier_label.isVisibleTo(pane)


def test_an_empty_source_file_heading_hides_the_group(qtbot, roots, monkeypatch):
    monkeypatch.setitem(esoterica_text.ESOTERICA_TEXT, "library.source_file_heading", "")
    write(roots[0], "notes.toml", ANNOTATES + FOOL, identifier="me/notes")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    pane = page.details_pane
    pane.set_source_file_open(True)

    page.select("me/notes")

    assert not pane.source_file_button.isVisibleTo(pane)
    assert not pane.source_file_group.isVisibleTo(pane)


@pytest.mark.parametrize(
    ("relation", "key"),
    [
        ("annotates", "library.relation.annotates"),
        ("transcribes", "library.relation.transcribes"),
        ("x_responds_to", "library.work_heading"),
        (None, "library.work_heading"),
    ],
)
def test_the_work_group_is_headed_by_its_relation(qtbot, roots, relation, key):
    text = ANNOTATES.replace('relation = "annotates"\n', "")
    if relation is not None:
        text = text.replace("[meta]\n", f'[meta]\nrelation = "{relation}"\n', 1)
    write(roots[0], "notes.toml", text + FOOL, identifier="me/notes")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)

    page.select("me/notes")

    assert page.details_pane.work_heading.text() == label_for(key)


RELATED = """related = [
  { rel = "pattern", target = "land.arcana/pattern/rider-waite-smith" },
  { rel = "about", target = "com.example/deck/one", title = "Deck One" },
  { rel = "about", target = "com.example/deck/untitled" },
  { rel = "about", target = "land.arcana/pattern/thoth" },
]
"""


def test_pattern_and_about_come_from_related(qtbot, roots):
    write(roots[0], "r.toml", source("R", extra=RELATED), identifier="me/r")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    pane = page.details_pane

    page.select("me/r")

    assert pane.pattern_label.text() == label_for("pattern.land.arcana/pattern/rider-waite-smith")
    assert pane.about_label.text() == label_for("joiner").join(
        ["Deck One", label_for("pattern.land.arcana/pattern/thoth")]
    )


@pytest.mark.parametrize(
    "related",
    [
        'related = "land.arcana/pattern/thoth"\n',
        "related = [1, []]\n",
        'related = [{ rel = "pattern", target = 3 }, { rel = 1, target = "x" }]\n',
        'related = [{ rel = "pattern", target = "com.example/pattern/unknown" }]\n',
    ],
)
def test_a_malformed_or_unknown_related_shows_nothing(qtbot, roots, related):
    write(roots[0], "r.toml", source("R", extra=related), identifier="me/r")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    pane = page.details_pane

    page.select("me/r")

    assert not pane.pattern_label.isVisibleTo(pane)
    assert not pane.about_label.isVisibleTo(pane)


def test_the_pane_lists_the_groups_a_source_writes_under(qtbot, roots):
    groups = '[group.suits.wands.passages]\ntext = "Fire."\n[group.all.passages]\ntext = "All."\n'
    write(roots[0], "g.toml", source("G") + groups, identifier="me/g")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)

    page.select("me/g")

    assert page.details_pane.groups_label.text() == label_for("joiner").join(["suits.wands", "all"])


def test_an_empty_form_label_hides_its_row(qtbot, roots, monkeypatch):
    monkeypatch.setitem(esoterica_text.ESOTERICA_TEXT, "library.form.copyright", "")
    write(roots[0], "notes.toml", ANNOTATES + FOOL, identifier="me/notes")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)

    page.select("me/notes")

    assert not page.details_pane.copyright_label.isVisibleTo(page.details_pane)
    assert page.details_pane.license_label.isVisibleTo(page.details_pane)


def test_placeholders_render_as_written(qtbot, page):
    """A tagged label must show its tag, not swallow it as markup"""
    page.select("me/alpha")
    pane = page.details_pane
    name = pane.form.labelForField(pane.pattern_label)

    assert name.textFormat() == Qt.TextFormat.PlainText


def test_the_pane_stacks_its_columns_when_narrow(page, qtbot):
    from PyQt6.QtWidgets import QBoxLayout

    pane = page.details_pane
    page.select("me/zeta")
    pane.show()
    qtbot.waitExposed(pane)

    pane.resize(pane.TWO_COLUMN_MIN_WIDTH + 100, 300)
    qtbot.waitUntil(lambda: pane.columns.direction() == QBoxLayout.Direction.LeftToRight)
    pane.resize(pane.TWO_COLUMN_MIN_WIDTH - 100, 300)
    qtbot.waitUntil(lambda: pane.columns.direction() == QBoxLayout.Direction.TopToBottom)


def test_every_form_lets_its_fields_take_the_panes_width(page):
    """Breeze keeps fields at their size hint, which cuts a wrapped value to one line"""
    from PyQt6.QtWidgets import QFormLayout

    pane = page.details_pane
    for form in (pane.form, pane.work_form, pane.source_file_form):
        assert form.fieldGrowthPolicy() == QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow


def test_keys_and_paths_are_monospace(page):
    from PyQt6.QtGui import QFontDatabase

    fixed = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont).family()
    pane = page.details_pane
    for label in (pane.identifier_label, pane.groups_label, pane.shadows_label, pane.file_label):
        assert label.font().family() == fixed
    assert pane.license_label.font().family() != fixed


def every_card_source(name):
    return source(name).replace(FOOL, "") + every_card('text = "A passage."')


def test_a_source_that_covers_every_card_says_so_instead_of_a_grid(qtbot, roots):
    write(roots[0], "all.toml", every_card_source("All"), identifier="me/all")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    pane = page.details_pane

    page.select("me/all")

    assert pane.coverage_complete_label.isVisibleTo(pane)
    assert pane.coverage_complete_label.text() == label_for("library.coverage_complete")
    assert not pane.coverage_grid.isVisibleTo(pane)


def test_with_no_complete_line_a_complete_source_shows_its_grid(qtbot, roots, monkeypatch):
    monkeypatch.setitem(esoterica_text.ESOTERICA_TEXT, "library.coverage_complete", "")
    write(roots[0], "all.toml", every_card_source("All"), identifier="me/all")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    pane = page.details_pane

    page.select("me/all")

    assert not pane.coverage_complete_label.isVisibleTo(pane)
    assert pane.coverage_grid.isVisibleTo(pane)


def test_the_grid_is_labelled_by_run_and_takes_height_for_its_width(page):
    grid = page.details_pane.coverage_grid

    assert grid.labels() == (
        label_for("library.coverage.major"),
        "Wands",
        "Cups",
        "Swords",
        "Pentacles",
    )
    assert grid.heightForWidth(400) > 0
    assert grid.heightForWidth(20) == 0


TWO_OF_CUPS = "minor_arcana.cups.two"


@pytest.fixture
def grid_page(qtbot, roots):
    one_card = (
        '[meta]\nname = "One"\nlicense = "CC0-1.0"\n'
        f'[card."{TWO_OF_CUPS}".passages]\ntext = "Two."\n'
        '[card."major_arcana.01".x_unshown]\nnote = "Not a passage."\n'
    )
    write(roots[0], "one.toml", one_card, identifier="me/one")
    page = EsotericaPage(EsotericaManager(roots))
    qtbot.addWidget(page)
    page.resize(900, 600)
    page.show()
    qtbot.waitExposed(page)
    page.select("me/one")
    grid = page.details_pane.coverage_grid
    grid.show()
    qtbot.waitUntil(lambda: grid.width() > 0 and grid.height() > 0)
    return page


def cell_centre(grid, card_id):
    from tarot_canvas.models.card_ids import CANONICAL_CARD_IDS
    from tarot_canvas.ui.library.coverage_strip import grid_cell_rects

    rects = grid_cell_rects(grid.rect(), grid._label_width())
    return rects[CANONICAL_CARD_IDS.index(card_id)].center().toPoint()


def test_clicking_a_covered_cell_asks_for_its_card(qtbot, grid_page):
    grid = grid_page.details_pane.coverage_grid

    with qtbot.waitSignal(grid_page.card_activated) as caught:
        qtbot.mouseClick(grid, Qt.MouseButton.LeftButton, pos=cell_centre(grid, TWO_OF_CUPS))

    assert caught.args == [TWO_OF_CUPS]


@pytest.mark.parametrize("card_id", ["major_arcana.00", "major_arcana.01"])
def test_an_empty_or_faint_cell_is_not_a_link(qtbot, grid_page, card_id):
    grid = grid_page.details_pane.coverage_grid
    assert grid.cell_at(cell_centre(grid, card_id)) is not None

    with qtbot.assertNotEmitted(grid_page.card_activated):
        qtbot.mouseClick(grid, Qt.MouseButton.LeftButton, pos=cell_centre(grid, card_id))
    assert grid.link_at(cell_centre(grid, card_id)) is None


def test_hovering_a_covered_cell_shows_a_link_cursor(qtbot, grid_page):
    grid = grid_page.details_pane.coverage_grid

    # Sent, not QTest.mouseMove: offscreen, a move with no button held doesn't reach the widget
    move(grid, cell_centre(grid, TWO_OF_CUPS))
    assert grid.cursor().shape() == Qt.CursorShape.PointingHandCursor

    move(grid, cell_centre(grid, "major_arcana.00"))
    assert grid.cursor().shape() == Qt.CursorShape.ArrowCursor


def move(widget, pos):
    from PyQt6.QtCore import QEvent, QPointF
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QApplication

    local = QPointF(pos)
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        local,
        QPointF(widget.mapToGlobal(pos)),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(widget, event)


def test_a_cell_is_named_by_the_pages_deck(qtbot, roots, minimal_deck):
    page = EsotericaPage(EsotericaManager(roots), deck=minimal_deck)
    qtbot.addWidget(page)

    name = page.details_pane.coverage_grid.card_name("major_arcana.00")

    assert name == minimal_deck.get_card_by_id("major_arcana.00")["name"]


def test_a_section_heading_is_shorter_than_a_source_row(page):
    view = page.list_view
    model = page.list_model
    heights = {}
    for row in range(model.rowCount()):
        index = model.index(row, 0)
        heights.setdefault(index.data(KindRole), view.visualRect(index).height())

    assert 0 < heights[RowKind.SECTION] < heights[RowKind.SOURCE]
