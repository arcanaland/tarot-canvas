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

<img width="1958" height="1382" alt="deck1" src="https://github.com/user-attachments/assets/8ac38498-a75a-4001-afc7-fbdc645d7592" />

For this example, I will be using images from Kathryn Isabelle Lawrence's [ascii-tarot](https://github.com/lawreka/ascii-tarot).

Place major arcana images in a folder called `major_arcana` and name them as a two-digit number. For example, The Fool:

<img height="500" alt="00" src="https://github.com/user-attachments/assets/d2936f1a-a5f7-4444-94a4-0f6ee5f9909a" />

Place it in `major_arcana/00.png`.

<img width="1958" height="1382" alt="deck2" src="https://github.com/user-attachments/assets/a3691cff-238b-4e23-8abc-98054ee994e3" />

Another example of The World:

<img height="500" alt="21" src="https://github.com/user-attachments/assets/5e4400e3-1ca8-4802-961c-5c29fa92a982" />

Place it in `major_arcana/21.png`.

<img width="1958" height="1382" alt="deck3" src="https://github.com/user-attachments/assets/9d2d6ce4-edcb-4722-973c-13cfb57c0f95" />

For the minor arcana, create a folder named `minor_arcana` with subfolders `wands`, `cups`, `swords`, and `pentacles`. For example:

<img width="2114" height="1622" alt="deck4" src="https://github.com/user-attachments/assets/b32ab530-60d7-4053-89d0-0b9aa0a223bd" />

Follow the example of `minor_arcana/cups/ace.png` and `minor_arcana/swords/three.png` for the rest of the cards.

> [!NOTE]
> The full [Tarot Deck Specification](https://github.com/arcanaland/specifications/blob/deck%2Fv1.0/DECK.md) is available and is currently at version 1. A major revision for [version 2 draft](https://github.com/arcanaland/specifications/blob/deck-v2/DECK.md) is currently underway.


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
