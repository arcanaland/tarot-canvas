from tarot_canvas.models import spreads, staged_delete
from tarot_canvas.models.spreads import Spread


def stored(base, name):
    folder = base / name
    folder.mkdir(parents=True)
    spreads.save(folder, Spread(name=name))
    return folder


def test_a_staged_folder_is_gone_from_scan_and_restores_whole(tmp_path):
    folder = stored(tmp_path, "1000")

    staged = staged_delete.stage(folder)

    assert not folder.exists()
    assert spreads.scan(tmp_path) == []

    staged_delete.restore(staged, folder)

    assert [path for path, _ in spreads.scan(tmp_path)] == [folder]


def test_committing_removes_a_folder_or_a_file(tmp_path):
    staged_folder = staged_delete.stage(stored(tmp_path, "1000"))
    note = tmp_path / "note.md"
    note.write_text("x")
    staged_note = staged_delete.stage(str(note))

    staged_delete.commit(staged_folder)
    staged_delete.commit(staged_note)

    assert list(tmp_path.iterdir()) == []


def test_offsets_are_in_units_from_the_middle_of_the_bounding_box():
    assert spreads.offsets_from_middle([(0, 0), (400, 100), (100, 300)], 200) == [
        (-1.0, -0.75),
        (1.0, -0.25),
        (-0.5, 0.75),
    ]


def test_no_centres_have_no_offsets():
    assert spreads.offsets_from_middle([], 200) == []
