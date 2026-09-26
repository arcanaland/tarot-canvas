"""python -m bench [WORKLOAD ...] [options] | python -m bench compare BASE NEW"""

import argparse
import sys
from pathlib import Path

from bench.env import BenchError, isolate_home, machine, select_platform, unthrottle

VIEWPORTS = ("raster", "gl")


def _counts(text):
    return [int(part) for part in text.split(",")]


def _viewports(text):
    kinds = text.split(",")
    for kind in kinds:
        if kind not in VIEWPORTS:
            raise argparse.ArgumentTypeError(f"viewport must be one of {', '.join(VIEWPORTS)}")
    return kinds


def _size(text):
    width, height = text.lower().split("x")
    return int(width), int(height)


def parser():
    from bench.workloads import WORKLOADS

    listing = "\n".join(f"  {w.name:<11} {w.description}" for w in WORKLOADS)
    p = argparse.ArgumentParser(
        prog="python -m bench",
        description="Frame times of the canvas under scripted motion.",
        epilog=f"workloads:\n{listing}\n\n"
        "Compare two saved results with: python -m bench compare BASE.json NEW.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("workloads", nargs="*", help="workloads to run (default: all)")
    p.add_argument("--list", action="store_true", help="print workload names and exit")
    p.add_argument("--cards", type=_counts, default=[16], help="card counts, e.g. 1,8,32")
    p.add_argument("--viewport", type=_viewports, default=["raster"], help="raster,gl")
    p.add_argument("--frames", type=int, default=600, help="timed frames per run")
    p.add_argument("--warmup", type=int, default=120, help="untimed frames before each run")
    p.add_argument("--runs", type=int, default=5, help="runs per cell")
    p.add_argument("--size", type=_size, default=(1600, 1000), help="tab size, WxH")
    p.add_argument("--art", type=Path, help="a directory of card art (default: synthetic)")
    p.add_argument("--msaa", type=int, default=0, help="GL multisample count")
    p.add_argument("--dpr", type=float, default=1.0, help="device pixel ratio (offscreen only)")
    p.add_argument(
        "--platform",
        default="offscreen",
        help="Qt platform plugin; gl needs a real one such as wayland",
    )
    p.add_argument("--json", type=Path, help="also save full results, raw frames included")
    p.add_argument("--snapshot", type=Path, help="save each cell's last frame here, to eyeball")
    return p


def bench(args):
    from bench.workloads import WORKLOADS, find_workload

    chosen = []
    for name in args.workloads or [w.name for w in WORKLOADS]:
        workload = find_workload(name)
        if workload is None:
            raise BenchError(f"no workload named '{name}'; try --list")
        chosen.append(workload)

    scratch = isolate_home()
    select_platform(args.platform, args.dpr, scratch)
    unthrottle(args.msaa)

    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QApplication

    app = QApplication([sys.argv[0]])  # noqa: F841 - held for the run

    from bench.canvas import BenchCanvas, art_in, synthetic_art
    from bench.frames import run, summarize
    from bench.report import HEADER, describe, row, save

    art = art_in(args.art) if args.art else synthetic_art(scratch / "art")
    config = {
        "frames": args.frames,
        "warmup": args.warmup,
        "runs": args.runs,
        "size": list(args.size),
        "msaa": args.msaa,
        "art": str(args.art) if args.art else "synthetic",
    }
    meta = None
    results = []
    for kind in args.viewport:
        canvas = BenchCanvas(kind, QSize(*args.size), art)
        if meta is None:
            meta = {
                "machine": machine(),
                "config": config,
                "platform": QApplication.platformName(),
                "dpr": canvas.device_pixel_ratio,
                "viewport_size": canvas.viewport_size,
                "gl_renderer": None,
            }
            print(describe(meta))
            print()
            print(HEADER)
        if canvas.gl_renderer:
            meta["gl_renderer"] = canvas.gl_renderer
            if "llvmpipe" in canvas.gl_renderer.lower():
                print(f"warning: software GL ({canvas.gl_renderer})", file=sys.stderr)
        for workload in chosen:
            for count in args.cards:
                runs = [
                    run(canvas, workload, count, args.frames, args.warmup) for _ in range(args.runs)
                ]
                result = {
                    "workload": workload.name,
                    "viewport": kind,
                    "cards": count,
                    "summary": summarize(runs),
                    "frames": [{"motion_ms": r.motion_ms, "paint_ms": r.paint_ms} for r in runs],
                }
                results.append(result)
                print(row(result), flush=True)
                if args.snapshot:
                    args.snapshot.mkdir(parents=True, exist_ok=True)
                    canvas.snapshot(args.snapshot / f"{workload.name}-{kind}-{count}.png")
        canvas.close()

    if args.json:
        save(args.json, meta, results)
        print(f"\nwrote {args.json}")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv[:1] == ["compare"]:
            from bench.report import compare

            if len(argv) != 3:
                print("usage: python -m bench compare BASE.json NEW.json", file=sys.stderr)
                return 2
            print(compare(argv[1], argv[2]))
            return 0

        args = parser().parse_args(argv)
        if args.list:
            from bench.workloads import WORKLOADS

            print("\n".join(w.name for w in WORKLOADS))
            return 0
        bench(args)
        return 0
    except BenchError as e:
        print(f"bench: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
