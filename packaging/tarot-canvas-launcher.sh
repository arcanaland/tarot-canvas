#!/bin/bash

mkdir -p "$HOME/.var/app/land.arcana.TarotCanvas/data/tarot-canvas"
mkdir -p "$HOME/.var/app/land.arcana.TarotCanvas/data/tarot/decks"

exec python3 -m tarot_canvas.main "$@"