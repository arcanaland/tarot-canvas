"""Printing results, saving them, and comparing two saved sets."""

import json

SCHEMA = 1

HEADER = (
    f"{'workload':<11} {'viewport':<8} {'cards':>5}  "
    f"{'frame p50':>9} {'p99':>6} {'max':>6}  {'motion':>6} {'paint':>6}  "
    f"{'>16.7':>6} {'>8.3':>6}  {'cov':>5}"
)


def describe(meta):
    machine = meta["machine"]
    config = meta["config"]
    lines = [
        f"platform {meta['platform']}  dpr {meta['dpr']:g}  viewport {meta['viewport_size'][0]}x{meta['viewport_size'][1]}"
        f"  frames {config['frames']} x{config['runs']} runs (+{config['warmup']} warmup)",
        f"qt {machine['qt']}  python {machine['python']}  cpu {machine['cpu']}  governor {machine['governor']}",
    ]
    if meta.get("gl_renderer"):
        lines.append(f"gl {meta['gl_renderer']}  msaa {config['msaa']}")
    if machine.get("commit"):
        lines.append(f"commit {machine['commit']}{' (dirty)' if machine.get('dirty') else ''}")
    return "\n".join(lines)


def row(result):
    s = result["summary"]
    frame = s["frame"]
    over60, over120 = s["over"]
    line = (
        f"{result['workload']:<11} {result['viewport']:<8} {result['cards']:>5}  "
        f"{frame['p50']:>7.2f}ms {frame['p99']:>6.2f} {frame['max']:>6.2f}  "
        f"{s['motion']['p50']:>6.2f} {s['paint']['p50']:>6.2f}  "
        f"{over60:>6.1%} {over120:>6.1%}  {s['cov']:>5.1%}"
    )
    if s["cov"] > 0.05:
        line += "  noisy"
    return line


def save(path, meta, results):
    with open(path, "w") as out:
        json.dump({"schema": SCHEMA, "meta": meta, "results": results}, out)


def load(path):
    with open(path) as source:
        data = json.load(source)
    if data.get("schema") != SCHEMA:
        raise ValueError(f"{path}: schema {data.get('schema')}, expected {SCHEMA}")
    return data


def _key(result):
    return (result["workload"], result["viewport"], result["cards"])


def compare(base_path, new_path):
    """Lines comparing the frame times of every cell present in both files."""
    base, new = load(base_path), load(new_path)
    before = {_key(r): r["summary"] for r in base["results"]}
    lines = [
        f"base {base['meta']['machine'].get('commit')}  new {new['meta']['machine'].get('commit')}",
        f"{'workload':<11} {'viewport':<8} {'cards':>5}  {'p50 base':>8} {'new':>7} {'Δ':>7}  "
        f"{'p99 base':>8} {'new':>7} {'Δ':>7}",
    ]
    for result in new["results"]:
        old = before.get(_key(result))
        if old is None:
            continue
        now = result["summary"]
        # Within the runs' own disagreement is not a change
        noise = 2 * max(old["cov"], now["cov"])

        def delta(stat, old=old, now=now, noise=noise):
            change = now["frame"][stat] / old["frame"][stat] - 1
            return f"{change:>+6.1%}{'' if abs(change) > noise else '~'}"

        lines.append(
            f"{result['workload']:<11} {result['viewport']:<8} {result['cards']:>5}  "
            f"{old['frame']['p50']:>8.2f} {now['frame']['p50']:>7.2f} {delta('p50'):>7}  "
            f"{old['frame']['p99']:>8.2f} {now['frame']['p99']:>7.2f} {delta('p99'):>7}"
        )
    lines.append("~ within 2x the runs' coefficient of variation")
    return "\n".join(lines)
