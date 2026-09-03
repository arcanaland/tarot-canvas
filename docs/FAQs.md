# Frequently Asked Questions

## Making Your Own Tarot Deck

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

[!](https://github.com/user-attachments/assets/35b3c96c-4757-404a-b08f-015c8af62df1)
