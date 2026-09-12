import hashlib

import pytest
from PyQt6.QtCore import QUrl

from tarot_canvas.utils.package_download import FailureKind, PackageDownload
from tests.unit.test_deck_container import build, conformant


@pytest.fixture
def places(tmp_path):
    root = tmp_path / "tarot" / "decks"
    root.mkdir(parents=True)
    return root, tmp_path / "tarot" / ".staging"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(container, dest, staging, size=None, digest=None):
    return PackageDownload(
        QUrl.fromLocalFile(str(container)),
        container.stat().st_size if size is None else size,
        sha256(container) if digest is None else digest,
        dest,
        staging,
    )


def run_to_failure(qtbot, job):
    with qtbot.waitSignal(job.failed, timeout=5000) as blocker:
        job.start()
    assert not job.is_running()
    assert not job.part_path.exists()
    return blocker.args[0]


def test_success_installs_and_reports_the_path(qtbot, tmp_path, places):
    root, staging = places
    container = conformant(tmp_path)
    job = download(container, root / "test", staging)
    progress = []
    job.progress.connect(lambda received, total: progress.append((received, total)))

    with qtbot.waitSignal(job.succeeded, timeout=5000) as blocker:
        job.start()
        assert job.is_running()

    assert blocker.args == [str(root / "test")]
    assert (root / "test" / "deck.toml").is_file()
    assert not job.part_path.exists()
    assert list(staging.iterdir()) == []
    assert progress and progress[-1] == (container.stat().st_size,) * 2
    assert not job.is_running()


def test_a_wrong_sha256_is_an_integrity_failure(qtbot, tmp_path, places):
    root, staging = places
    job = download(conformant(tmp_path), root / "x", staging, digest="0" * 64)

    assert run_to_failure(qtbot, job).kind == FailureKind.INTEGRITY
    assert not (root / "x").exists()


@pytest.mark.parametrize("delta", [-1, +1], ids=["declared-smaller", "declared-larger"])
def test_a_wrong_size_is_an_integrity_failure(qtbot, tmp_path, places, delta):
    root, staging = places
    container = conformant(tmp_path)
    job = download(container, root / "x", staging, size=container.stat().st_size + delta)

    assert run_to_failure(qtbot, job).kind == FailureKind.INTEGRITY
    assert not (root / "x").exists()


def test_a_missing_file_is_a_network_failure(qtbot, tmp_path, places):
    root, staging = places
    missing = tmp_path / "nowhere.tarotdeck"
    job = PackageDownload(QUrl.fromLocalFile(str(missing)), 10, "0" * 64, root / "x", staging)

    assert run_to_failure(qtbot, job).kind == FailureKind.NETWORK


def test_a_rejected_container_is_a_container_failure(qtbot, tmp_path, places):
    root, staging = places
    wrapped = build(tmp_path, [("x/deck.toml", b"[deck]\n")], mimetype=False)
    job = download(wrapped, root / "x", staging)

    failure = run_to_failure(qtbot, job)
    assert failure.kind == FailureKind.CONTAINER
    assert "wrapping directory" in failure.detail
    assert list(staging.iterdir()) == []
    assert list(root.iterdir()) == []


def test_an_existing_dest_is_refused_before_downloading(qtbot, tmp_path, places):
    root, staging = places
    (root / "x").mkdir()
    (root / "x" / "keep").write_bytes(b"mine")
    job = download(conformant(tmp_path), root / "x", staging)
    progress = []
    job.progress.connect(lambda *args: progress.append(args))

    assert run_to_failure(qtbot, job).kind == FailureKind.DESTINATION_EXISTS
    assert progress == []
    assert (root / "x" / "keep").read_bytes() == b"mine"


def test_cancel_reports_cancelled_and_leaves_no_part(qtbot, tmp_path, places):
    root, staging = places
    job = download(conformant(tmp_path), root / "x", staging)

    with qtbot.waitSignal(job.failed, timeout=5000) as blocker:
        job.start()
        job.cancel()

    assert blocker.args[0].kind == FailureKind.CANCELLED
    assert not job.part_path.exists()
    assert not (root / "x").exists()


def test_a_finished_download_can_be_started_again(qtbot, tmp_path, places):
    """What a retry after failure does."""
    root, staging = places
    container = conformant(tmp_path)
    job = download(container, root / "x", staging)
    with qtbot.waitSignal(job.failed, timeout=5000):
        job.start()
        job.cancel()

    with qtbot.waitSignal(job.succeeded, timeout=5000):
        job.start()
    assert (root / "x" / "deck.toml").is_file()
