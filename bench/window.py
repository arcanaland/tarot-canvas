"""What a GL canvas does to the window it joins: python -m bench.window

Each variant runs in a fresh process under the current (real) Qt platform:
  raster  a raster canvas tab is added to a shown window (the control)
  late    a GL canvas tab is added to a shown window, as the app does
  eager   the window holds a 1 px QOpenGLWidget before it is first shown
"""

import argparse
import json
import os
import subprocess
import sys
import time

VARIANTS = ("raster", "late", "eager")
SETTLE_MS = 1000
CARDS = 32


def rss_mib():
    with open("/proc/self/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return None


def gpu_mib():
    """This process's DRM client memory (amdgpu, i915 and xe report it), or None."""
    total, clients = 0.0, set()
    for fd in os.listdir("/proc/self/fdinfo"):
        try:
            with open(f"/proc/self/fdinfo/{fd}") as f:
                fields = dict(line.split(":", 1) for line in f if ":" in line)
        except OSError:
            continue
        client = fields.get("drm-client-id", "").strip()
        if not client or client in clients:
            continue
        clients.add(client)
        for key, value in fields.items():
            if key.startswith("drm-memory-"):
                number, *unit = value.split()
                total += int(number) * {"KiB": 1 / 1024, "MiB": 1, "GiB": 1024}.get(unit[0], 0)
    return total if clients else None


def probe(variant):
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtGui import QColor, QPixmap
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    from PyQt6.QtWidgets import (
        QApplication,
        QGraphicsScene,
        QGraphicsView,
        QMainWindow,
        QTabWidget,
        QWidget,
    )

    app = QApplication([sys.argv[0]])

    def pump(ms):
        deadline = time.perf_counter() + ms / 1000
        while time.perf_counter() < deadline:
            app.processEvents()
            time.sleep(0.002)

    class Destroyed(QObject):
        count = 0

        def eventFilter(self, watched, event):
            if event.type() == QEvent.Type.PlatformSurface and (
                event.surfaceEventType() == event.SurfaceEventType.SurfaceAboutToBeDestroyed
            ):
                self.count += 1
            return False

    window = QMainWindow()
    tabs = QTabWidget()
    window.setCentralWidget(tabs)
    tabs.addTab(QWidget(), "Welcome")
    if variant == "eager":
        QOpenGLWidget(window).setGeometry(0, 0, 1, 1)
    window.resize(1280, 800)
    window.show()
    pump(SETTLE_MS)

    handle = window.windowHandle()
    destroyed = Destroyed()
    handle.installEventFilter(destroyed)
    out = {"variant": variant, "platform": app.platformName()}
    out["start"] = {"rss": rss_mib(), "gpu": gpu_mib(), "surface": handle.surfaceType().name}

    scene = QGraphicsScene()
    for i in range(CARDS):
        pixmap = QPixmap(300, 520)
        pixmap.fill(QColor.fromHsv((i * 37) % 360, 160, 200))
        scene.addPixmap(pixmap).setPos((i % 8) * 160, (i // 8) * 180)
    view = QGraphicsView(scene)
    first_frame = []
    if variant != "raster":
        gl = QOpenGLWidget()
        gl.frameSwapped.connect(lambda: first_frame or first_frame.append(time.perf_counter()))
        view.setViewport(gl)
    added = time.perf_counter()
    tabs.setCurrentIndex(tabs.addTab(view, "Canvas"))
    pump(SETTLE_MS)
    out["canvas"] = {
        "rss": rss_mib(),
        "gpu": gpu_mib(),
        "surface": window.windowHandle().surfaceType().name,
        "recreated": window.windowHandle() is not handle or destroyed.count > 0,
        "first_frame_ms": (first_frame[0] - added) * 1000 if first_frame else None,
    }

    tabs.removeTab(tabs.indexOf(view))
    view.deleteLater()
    pump(SETTLE_MS)
    out["closed"] = {
        "rss": rss_mib(),
        "gpu": gpu_mib(),
        "surface": window.windowHandle().surfaceType().name,
    }
    return out


def _mib(value):
    return "-" if value is None else f"{value:.0f}"


def _delta(start, stage, key):
    if stage[key] is None:
        return None
    return stage[key] - (start[key] or 0)


def table(results):
    lines = [
        f"{'variant':<8} {'platform':<8} {'start':>10} {'+canvas':>10} {'+closed':>10}  "
        f"{'recreated':<9} {'surface after close':<20} first frame",
        f"{'':<8} {'':<8} {'RSS/GPU':>10} {'RSS/GPU':>10} {'RSS/GPU':>10}  (MiB)",
    ]
    for r in results:
        start, canvas, closed = r["start"], r["canvas"], r["closed"]

        first = canvas["first_frame_ms"]
        lines.append(
            f"{r['variant']:<8} {r['platform']:<8} "
            f"{_mib(start['rss']) + '/' + _mib(start['gpu']):>10} "
            f"{_mib(_delta(start, canvas, 'rss')) + '/' + _mib(_delta(start, canvas, 'gpu')):>10} "
            f"{_mib(_delta(start, closed, 'rss')) + '/' + _mib(_delta(start, closed, 'gpu')):>10}  "
            f"{'yes' if canvas['recreated'] else 'no':<9} {closed['surface']:<20} "
            f"{'-' if first is None else f'{first:.0f} ms'}"
        )
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m bench.window", description=__doc__.splitlines()[0])
    p.add_argument("--variant", choices=VARIANTS, help="run one variant here and print JSON")
    p.add_argument("--json", help="also save the results")
    args = p.parse_args(argv)
    if args.variant:
        print(json.dumps(probe(args.variant)))
        return 0

    results = []
    for variant in VARIANTS:
        done = subprocess.run(
            [sys.executable, "-m", "bench.window", "--variant", variant],
            capture_output=True,
            text=True,
        )
        if done.returncode != 0:
            print(f"bench.window: {variant} failed:\n{done.stderr}", file=sys.stderr)
            return 1
        results.append(json.loads(done.stdout.splitlines()[-1]))
    print(table(results))
    if args.json:
        with open(args.json, "w") as f:
            json.dump(results, f, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
