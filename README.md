<img src="./packaging/icon.png"  align="right" height="60" />

# Tarot Canvas

A digital home for your personal tarot collection on Linux.

![Main window of Tarot Canvas showing the Wheel of Fortune card](./packaging/screenshots/main-window.webp)

## Features

- Explore tarot deck imagery, metadata and esoterica.</li>
- Place and arrange tarot cards from any deck on a virtual canvas.</li>
- Create and add your own decks by following a standard [tarot deck format](./docs/FAQs.md).


## Installation

The preferred installation method is via Flatpak from Flathub:

<a href='https://flathub.org/en/apps/land.arcana.TarotCanvas'><img width='240' alt='Download on Flathub' src='https://flathub.org/assets/badges/flathub-badge-en.png'/></a>

```bash
flatpak install flathub land.arcana.TarotCanvas
```


### From Source

Requires `just` and `flatpak`.

```
just flatpak deps
just flatpak install
flatpak run land.arcana.TarotCanvas
```

## AI Policy

Tarot Canvas does not include any AI generated art or display strings and will never present AI-generated text or images to its users. It is an explicit design goal to never include this kind of garbage into this application.

For code, configuration, packaging and other assets intended for non-user-facing automatable tasks, LLMs are used in a narrow scope. See [Arcana Land's AI Policy](https://github.com/arcanaland/arcanaland/blob/main/AI-POLICY.md) for more detail.
