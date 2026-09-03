# Frequently Asked Questions

## Making Your Own Tarot Deck

Creating a Tarot deck consists of putting your card images into a certain folder structure with a TOML file at the top.

This section will walk-through creating a tarot deck step-by-step using KDE Plasma.

Open Dolphin and navigate to `~/.var/app/land.arcana.TarotCanvas/data/tarot/decks`. Create a directory called `my-tarot-deck` (or name it whatever).

The create a new TOML file called `deck.toml` and fill it out:

```toml
[deck]
id = "my-tarot-deck"
name = "My Tarot Deck"
version = "1.0"
author = "Jane Doe"
schema_version = "1.0"
```

// deck1.webp

For this example, I will be using images from Kathryn Isabelle Lawrence's [ascii-tarot](https://github.com/lawreka/ascii-tarot).

Place major arcana images in a folder called `major_arcana` and name them as a two-digit number. For example, The Fool:

// fool.webp

Place it in `major_arcana/00.png`.

// deck2.webp

Another example of The World:

// world.webp

Place it in `major_arcana/21.png`.

// deck3.webp

For the minor arcana, create a folder named `minor_arcana` with subfolders `wands`, `cups`, `swords`, and `pentacles`. For example:

// deck4.webp

> [!NOTE]
> Version 1 of the Tarot Deck Specification is availble at [Arcana Land](https://github.com/arcanaland/specifications/blob/deck%2Fv1.0/DECK.md). A [version 2 draft](https://github.com/arcanaland/specifications/blob/deck-v2/DECK.md) is currently in development.


## Adding Your Own Esoterica

Tarot Canvas currently only supports a very narrow set of esoterica notes.

Essentially, you can create a "passage" per-card by manually adding a file with the following format:

```toml
[meta]
id = "my-custom-esoterica"
name = "My Custom Esoterica"
author = "Jane Doe"


[passages.major_arcana.00]
text = "These are my permanent notes for The Fool."

# ... the rest of the Major Arcana ...

[passages.major_arcana.21]
text = "These are my permanent notes for The World."

# ... now the Minor Arcana ...


[passages.minor_arcana.wands.ace]
text = "These are my permanent notes for the Ace of Wands."

# ...

[passages.minor_arcana.cups.ten]
text = "These are my permanent notes for the Ten of Cups."
```

Save this file as `~/.var/app/land.arcana.TarotCanvas/data/tarot/esoterica/references/my_file.toml`.

![Screenshot of the above esoterica file for The Fool](https://github.com/user-attachments/assets/35b3c96c-4757-404a-b08f-015c8af62df1)

> [!NOTE]
> The official [Esoterica Specification](https://github.com/arcanaland/specifications/blob/deck-v2/ESOTERICA.md) is still under development. Once it is finalized, support will be added to Tarot Canvas and the default corpus containing astrological, alchemical and esoteric knowledge ([McElroy esoterica pack](https://github.com/arcanaland/esoterica/releases/tag/mcelroy%2Fv0.5)) will be included out of the box.
