"""Frame-time benchmarks for the canvas.

Each workload replays a fixed motion script against a real CanvasTab and times every
frame: the Python motion step, then Qt's paint of the dirtied viewport. Time advances
by a fixed dt rather than the wall clock, so every run draws the same poses.
"""
