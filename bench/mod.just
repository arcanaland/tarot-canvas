# Canvas frame-time benchmarks. `just bench run --help` for every option.

set working-directory := '..'
set positional-arguments

# A nested, windowless compositor, so GL has a real surface and nothing appears on screen
compositor := env('BENCH_COMPOSITOR', 'kwin_wayland --virtual --no-lockscreen --no-global-shortcuts --width 2560 --height 1600')

[private]
default:
  @just --list bench

[doc('Workload names.')]
[group('bench')]
list:
  uv run python -m bench --list

[doc('Raster only, on the offscreen platform, e.g. `just bench run ambient --cards 1,16,64`.')]
[group('bench')]
run *args:
  uv run python -m bench "$@"

[doc('Raster and GL inside a headless compositor, e.g. `just bench headless drag --cards 32`.')]
[group('bench')]
[script('bash')]
headless *args:
  set -euo pipefail
  out=$(mktemp -d)
  trap 'rm -rf "$out"' EXIT
  printf -v forwarded '%q ' "$@"
  cat >"$out/session.sh" <<EOF
  uv run python -m bench --platform wayland --viewport raster,gl $forwarded >$out/stdout 2>$out/stderr
  echo \$? >$out/status
  EOF
  WAYLAND_DISPLAY= {{compositor}} --socket tarot-canvas-bench --exit-with-session "bash $out/session.sh" \
    >"$out/compositor.log" 2>&1 || true
  cat "$out/stdout"
  grep -v -e ' - INFO - ' -e ' - WARNING - ' "$out/stderr" >&2 || true
  if [ ! -s "$out/status" ]; then
    echo "bench: the compositor exited before the bench did:" >&2
    tail -20 "$out/compositor.log" >&2
    exit 1
  fi
  exit "$(cat "$out/status")"

[doc('One workload over a range of card counts, raster against GL.')]
[group('bench')]
sweep workload="ambient" cards="1,4,16,32,64" *args:
  just bench headless {{workload}} --cards {{cards}} {{args}}

[doc('Save every workload to a JSON file for `just bench compare`.')]
[group('bench')]
baseline out="bench-baseline.json" *args:
  just bench headless --cards 4,16,32 --json {{out}} {{args}}

[doc('Frame-time change from one saved result to another.')]
[group('bench')]
compare base new:
  uv run python -m bench compare {{base}} {{new}}
