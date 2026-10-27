# Canvas benchmarks

Frame times for the canvas tab with motion.

```
just bench list                          # workloads
just bench run ambient --cards 1,16,64   # raster, offscreen, no window
just bench headless drag --cards 32      # raster and GL in a windowless compositor
just bench sweep ambient                 # one workload over 1..64 cards
just bench baseline before.json          # everything, saved
just bench compare before.json after.json
```
