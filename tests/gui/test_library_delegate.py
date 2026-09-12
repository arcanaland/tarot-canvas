import pytest
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPalette
from PyQt6.QtWidgets import QStyle, QStyleOptionViewItem

from tarot_canvas.ui.library import deck_delegate, units
from tarot_canvas.ui.library.catalog_client import deck_catalog
from tarot_canvas.ui.library.cover_cache import CoverCache
from tarot_canvas.ui.library.deck_delegate import DeckDelegate
from tarot_canvas.ui.library.deck_downloads import deck_downloads
from tarot_canvas.ui.library.deck_model import DeckListModel
from tarot_canvas.utils.package_download import DownloadFailure, FailureKind
from tests.unit.test_library_model import catalog_entry, fake_deck

CARD_SIZES = [(600, 1024), (1140, 1140), (2420, 1400)]


def write_card(tmp_path, width, height, colour="red"):
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor(colour))
    path = tmp_path / f"card-{width}x{height}.png"
    assert image.save(str(path))
    return str(path)


def option_for(delegate, qapp, rect=None):
    option = QStyleOptionViewItem()
    option.font = qapp.font()
    option.palette = qapp.palette()
    option.rect = rect or QRect(0, 0, *_hint(delegate, qapp))
    option.state = QStyle.StateFlag.State_Enabled
    return option


def _hint(delegate, qapp):
    probe = QStyleOptionViewItem()
    probe.font = qapp.font()
    probe.rect = QRect(0, 0, 1, 1)
    size = delegate.sizeHint(probe, None)
    return size.width(), size.height()


# -- geometry ------------------------------------------------------------


@pytest.mark.parametrize("density", units.DENSITIES)
def test_layout_stacks_cover_title_subtitle_without_overlap(qapp, density):
    delegate = DeckDelegate(density=density)
    option = option_for(delegate, qapp)
    layout = delegate._layout(option)

    assert layout.cover.bottom() < layout.title.top()
    assert layout.title.bottom() < layout.subtitle.top()
    assert layout.subtitle.bottom() <= option.rect.bottom()
    assert layout.cover.height() == delegate.cover_size().height()


@pytest.mark.parametrize("density", units.DENSITIES)
def test_size_hint_reserves_a_fixed_cell_so_rows_never_drift(qapp, density):
    """Every cell is the same height whatever its cover or title, which is what
    keeps metadata lines aligned across a row."""
    delegate = DeckDelegate(density=density)
    width, height = _hint(delegate, qapp)
    assert width == delegate.cover_size().width() + 2 * units.LARGE_SPACING
    assert height > delegate.cover_size().height()


def test_density_changes_the_cell_size(qapp):
    delegate = DeckDelegate(density=units.DENSITY_SMALL)
    small = _hint(delegate, qapp)
    assert delegate.set_density(units.DENSITY_LARGE)
    assert _hint(delegate, qapp)[0] > small[0]
    assert not delegate.set_density(units.DENSITY_LARGE)


def test_unknown_density_falls_back_to_medium(qapp):
    delegate = DeckDelegate(density=units.DENSITY_SMALL)
    delegate.set_density("enormous")
    assert delegate.density == units.DENSITY_MEDIUM


def test_cover_well_is_two_by_three():
    for density in units.DENSITIES:
        width, height = units.cover_size(density)
        assert height / width == pytest.approx(1.5)


# -- cover cache ---------------------------------------------------------


@pytest.mark.parametrize(("width", "height"), CARD_SIZES)
def test_cover_is_scaled_into_the_well_preserving_aspect(tmp_path, qapp, width, height):
    well = QSize(*units.cover_size(units.DENSITY_MEDIUM))
    pixmap = CoverCache().get(write_card(tmp_path, width, height), well)

    assert pixmap is not None
    assert pixmap.width() <= well.width() and pixmap.height() <= well.height()
    assert pixmap.width() / pixmap.height() == pytest.approx(width / height, rel=0.02)


def test_cover_decodes_at_device_pixels_on_hidpi(tmp_path, qapp):
    """The same bug class as the HiDPI clipping already fixed in card view."""
    well = QSize(*units.cover_size(units.DENSITY_MEDIUM))
    path = write_card(tmp_path, 1200, 1800)

    normal = CoverCache().get(path, well, 1.0)
    retina = CoverCache().get(path, well, 2.0)

    assert retina.devicePixelRatio() == 2.0
    assert retina.width() == pytest.approx(normal.width() * 2, abs=2)
    # Logical size is unchanged
    assert retina.width() / retina.devicePixelRatio() == pytest.approx(normal.width(), abs=1)


def test_cover_never_fully_decodes_an_oversized_source(tmp_path, qapp):
    well = QSize(*units.cover_size(units.DENSITY_MEDIUM))
    pixmap = CoverCache().get(write_card(tmp_path, 1600, 2400), well)
    assert pixmap.height() <= well.height()


def test_missing_and_broken_covers_are_cached_as_none(tmp_path, qapp):
    cache = CoverCache()
    broken = tmp_path / "not-an-image.png"
    broken.write_text("nope")
    assert cache.get(str(broken), QSize(144, 216)) is None
    assert cache.get(str(tmp_path / "absent.png"), QSize(144, 216)) is None
    assert cache.get(None, QSize(144, 216)) is None


def test_cache_returns_the_same_pixmap_for_a_repeat_request(tmp_path, qapp):
    cache = CoverCache()
    path = write_card(tmp_path, 600, 900)
    well = QSize(144, 216)
    assert cache.get(path, well) is cache.get(path, well)


# -- painting ------------------------------------------------------------


def render(delegate, qapp, index, palette, state=QStyle.StateFlag.State_Enabled):
    option = option_for(delegate, qapp)
    option.palette = palette
    option.state = state
    image = QImage(option.rect.size(), QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    delegate.paint(painter, option, index)
    painter.end()
    return image


def colours_in(image):
    return {image.pixel(x, y) for x in range(image.width()) for y in range(image.height())}


def model_with_cover(tmp_path, colour="red"):
    deck = fake_deck("Rider-Waite-Smith", author="P. C. Smith", majors=22, minors=56)
    path = write_card(tmp_path, 600, 900, colour)
    deck.get_cards_by_type = lambda t: (
        [{"type": t, "number": 0, "image": path}] if t == "major_arcana" else [{"type": t}] * 56
    )
    return DeckListModel([deck])


def test_selection_is_painted_in_the_palette_highlight(qapp, tmp_path):
    delegate = DeckDelegate()
    model = model_with_cover(tmp_path)
    palette = QPalette(qapp.palette())
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#00ff00"))

    unselected = render(delegate, qapp, model.index(0, 0), palette)
    selected = render(
        delegate,
        qapp,
        model.index(0, 0),
        palette,
        QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected,
    )

    assert QColor("#00ff00").rgb() in colours_in(selected)
    assert QColor("#00ff00").rgb() not in colours_in(unselected)


def test_hover_is_painted_but_weaker_than_selection(qapp, tmp_path):
    delegate = DeckDelegate()
    model = model_with_cover(tmp_path)
    palette = QPalette(qapp.palette())
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#00ff00"))

    hovered = render(
        delegate,
        qapp,
        model.index(0, 0),
        palette,
        QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_MouseOver,
    )
    selected = render(
        delegate,
        qapp,
        model.index(0, 0),
        palette,
        QStyle.StateFlag.State_Enabled | QStyle.StateFlag.State_Selected,
    )
    plain = render(delegate, qapp, model.index(0, 0), palette)

    # Sample a corner, which only the state background ever paints.
    corner = (2, 2)
    assert plain.pixelColor(*corner).alpha() == 0
    assert selected.pixelColor(*corner).alpha() == 255
    assert 0 < hovered.pixelColor(*corner).alpha() < 255, "hover must be a tint, not solid"


def test_the_cell_follows_the_colour_scheme(qapp, tmp_path):
    delegate = DeckDelegate()
    model = model_with_cover(tmp_path)

    light = QPalette(qapp.palette())
    light.setColor(QPalette.ColorRole.Text, QColor("#000000"))
    light.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))

    dark = QPalette(qapp.palette())
    dark.setColor(QPalette.ColorRole.Text, QColor("#ffffff"))
    dark.setColor(QPalette.ColorRole.Base, QColor("#1b1b1b"))

    assert render(delegate, qapp, model.index(0, 0), light) != render(
        delegate, qapp, model.index(0, 0), dark
    )


def test_a_deck_without_art_still_paints_a_full_height_well(qapp):
    """A missing cover must not break row alignment."""
    delegate = DeckDelegate()
    model = DeckListModel([fake_deck("Artless", images=False)])
    image = render(delegate, qapp, model.index(0, 0), qapp.palette())

    painted = [
        y
        for y in range(image.height())
        for x in range(image.width())
        if image.pixelColor(x, y).alpha() > 0
    ]
    assert painted, "placeholder well was not painted"
    option = option_for(delegate, qapp)
    layout = delegate._layout(option)
    assert min(painted) <= layout.cover.top() + 1


# -- ghosts --------------------------------------------------------------

GHOST = catalog_entry("aquatic-tarot")


@pytest.fixture
def ghost_calls(monkeypatch):
    calls = []

    def record(painter, rect, pixmap, **kwargs):
        calls.append({"rect": QRect(rect), "pixmap": pixmap, **kwargs})

    monkeypatch.setattr(deck_delegate, "paint_ghost_cover", record)
    return calls


def ghost_model():
    """An installed deck at row 0, the ghost at row 1. Keep the model bound while
    its indexes are used: a freed model leaves them dangling, and data() segfaults."""
    return DeckListModel([fake_deck("Installed", images=False)], entries=[GHOST])


def test_an_available_ghost_is_dimmed_with_the_download_emblem(qapp, ghost_calls):
    model = ghost_model()
    render(DeckDelegate(), qapp, model.index(1, 0), qapp.palette())

    (call,) = ghost_calls
    assert call["progress"] is None
    assert call["failed"] is False
    assert isinstance(call["emblem"], QIcon)
    assert call["pixmap"].isNull()  # no cover yet: bar and emblem go in the well


def test_a_downloading_ghost_paints_its_progress(qapp, ghost_calls, fake_downloads):
    deck_downloads().start(GHOST)
    fake_downloads[0].progress.emit(40, 100)
    model = ghost_model()
    render(DeckDelegate(), qapp, model.index(1, 0), qapp.palette())

    (call,) = ghost_calls
    assert call["progress"] == pytest.approx(0.4)
    assert call["failed"] is False


def test_a_failed_ghost_paints_the_error(qapp, ghost_calls, fake_downloads):
    deck_downloads().start(GHOST)
    fake_downloads[0].failed.emit(DownloadFailure(FailureKind.NETWORK, "offline"))
    model = ghost_model()
    render(DeckDelegate(), qapp, model.index(1, 0), qapp.palette())

    (call,) = ghost_calls
    assert call["failed"] is True
    assert call["progress"] is None


def test_a_ghost_with_a_cover_hands_over_the_art_where_it_would_sit(
    qapp, tmp_path, monkeypatch, ghost_calls
):
    path = write_card(tmp_path, 600, 900)
    monkeypatch.setattr(deck_catalog(), "cover_path", lambda entry: path)
    delegate = DeckDelegate()
    model = ghost_model()
    render(delegate, qapp, model.index(1, 0), qapp.palette())

    (call,) = ghost_calls
    assert not call["pixmap"].isNull()
    assert call["rect"].size() == call["pixmap"].deviceIndependentSize().toSize()
    assert call["rect"].bottom() == delegate._layout(option_for(delegate, qapp)).cover.bottom()


def test_an_installed_deck_never_paints_as_a_ghost(qapp, tmp_path, ghost_calls):
    with_art = model_with_cover(tmp_path)
    render(DeckDelegate(), qapp, with_art.index(0, 0), qapp.palette())
    beside_a_ghost = ghost_model()
    render(DeckDelegate(), qapp, beside_a_ghost.index(0, 0), qapp.palette())
    assert ghost_calls == []


def test_a_ghost_row_paints_for_real(qapp, fake_downloads):
    """No patching: the ghost path through a Python paint() must not crash."""
    deck_downloads().start(GHOST)
    fake_downloads[0].progress.emit(50, 100)
    model = ghost_model()
    image = render(DeckDelegate(), qapp, model.index(1, 0), qapp.palette())
    assert not image.isNull()
