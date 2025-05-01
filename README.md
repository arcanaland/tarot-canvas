<img src="./packaging/icon.png"  align="right" height="60" />

# Tarot Canvas

A cross-platform desktop application for viewing and exploring tarot decks.
![image](https://github.com/user-attachments/assets/c859ad76-2d29-4828-9559-ea2c6695774e)


## Features

- Explore tarot deck imagery and esoterica
- Support for multiple image formats (SVG, raster, ANSI)
- A Canvas view that acts as a physical space to interact with cards

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
