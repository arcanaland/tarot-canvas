# Canvas benchmarks

Frame times for the canvas tab under scripted motion.

```
just bench list                          # workloads
just bench run ambient --cards 1,16,64   # raster, offscreen, no window
just bench headless drag --cards 32      # raster and GL in a windowless compositor
just bench sweep ambient                 # one workload over 1..64 cards
just bench baseline before.json          # everything, saved
just bench compare before.json after.json
```

## What a frame is

Each workload (`bench/workloads.py`) is a script: the cards are laid out from a fixed
seed, and every frame moves something (a drag path, the camera) and steps the cards'
motion exactly as `MotionClock` would. The difference is that time advances by a fixed
1/60 s instead of the wall clock, so every run draws the same poses and two runs can be
compared frame for frame.

A frame is timed in two parts:

- **motion**: the Python step. It covers springs, drift, `QTransform` composition and
  `setTransform`/`setPos`, and the scene index updates those cause.
- **paint**: pumping the event loop until Qt has repainted what the step dirtied. On
  GL this also includes `glFinish`, because GL calls return before the GPU has done
  anything.

Frames run back to back with vsync off, so a frame's time is its cost, not the display's
refresh interval. This is qmlbench's frame-count mode, or QCPainterBench's
`QSG_NO_VSYNC=1`. With vsync on, every GL frame reads about 16.7 ms whatever it cost.

## Reading the table

```
workload    viewport cards  frame p50    p99    max  motion  paint   >16.7   >8.3    cov
```

- **p50** is the typical frame. **p99 and max** are the hitches you can see. An average
  hides them, which is why the table shows no mean (the JSON keeps one).
- **>16.7 and >8.3** are the fractions of frames that would miss a vsync at 60 Hz and
  120 Hz. These are the numbers that decide whether motion looks smooth.
- **cov** is the coefficient of variation of the run means. Above 5% the row is marked
  `noisy`, and a difference that small between two rows is not a result.
- `compare` marks a change `~` when it is within twice the runs' own variation.

## Platforms

- `offscreen` (default for `run`) needs no display, and CI runs the workloads there as a
  smoke test (`tests/gui/test_bench.py`). It cannot show a `QOpenGLWidget`, so it is
  raster only. `--dpr 2` simulates a HiDPI screen.
- `headless` runs the bench as the only client of `kwin_wayland --virtual`. That gives a
  real Wayland surface with GPU GL and puts nothing on your screen. Set
  `BENCH_COMPOSITOR` to use another compositor.
- The GL viewport exists only here. The app itself still paints with raster.

`--snapshot DIR` saves every cell's last frame. A benchmark that draws nothing is very
fast, so look at the snapshots whenever a number seems too good.

## Keeping numbers honest

- Compare results from the same machine, on AC power, with the same governor. The header
  and JSON record the CPU, governor, Qt and commit, so check them before comparing.
- Close heavy applications. Raster paint is multithreaded and competes for cores.
- Use `--art DIR` with a real deck before trusting a conclusion. The synthetic art is
  sized like a reference deck's h1200 art, but it is not real art.
- To see where motion time goes, profile a run:
  `py-spy record -o bench.svg -- python -m bench ambient --cards 32`.

## Adding a workload

Add a `Workload` to `WORKLOADS`: a `start(canvas)` whose result is passed to every
`step(canvas, state, t)`. Keep it a pure function of `t`, so runs stay repeatable.
