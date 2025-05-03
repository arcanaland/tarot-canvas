<img src="./packaging/icon.png"  align="right" height="60" />

# Tarot Canvas

A cross-platform desktop application for viewing and exploring tarot decks.

![image](https://github.com/user-attachments/assets/fd348809-6c76-428c-a094-df7ead6a5262)

## Features

- Explore tarot deck imagery, metadata and esoterica (corrospondences and other occult or divinatory information)
- Includes the traditional Rider-Waite-Smith deck and supports any deck following the [Tarot Deck Specification](https://github.com/arcanaland/specifications)
- Provides a playground canvas where you can place and arrange tarot cards from any deck 

## Installation

### From Source with Poetry

Assumes a Linux environment with KDE.

```bash
poetry install
poetry run tarot-canvas
```

## From Source with Flatpak

Requires `flatpak-builder` to be available.

```
just install-flatpak
flatpak run land.arcana.TarotCanvas
```

Once this project is sufficiently far along, it will be submitted to Flathub.
