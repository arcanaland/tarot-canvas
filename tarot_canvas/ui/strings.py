"""Every string the app shows"""

# Menus, the command palette and shortcuts
COMMANDS = {
    # File
    "new_canvas": "New &Canvas",
    "new_spread": "New Spread",
    "new_library": "New &Library View",
    "new_card_view": "New C&ard View",
    "open_deck": "&Open Deck…",
    "close_tab": "Close &Tab",
    "quit": "&Exit",
    # Tab bar context menu
    "rename_tab": "Rename tab…",
    "close_this_tab": "Close tab",
    # Edit
    "cut": "Cut",
    "copy_card": "&Copy Card",
    "paste_card": "&Paste Card",
    "delete": "Delete",
    "select_all": "Select All",
    "deselect": "Deselect",
    "find": "Find…",
    # View
    "card_explorer": "&Card Explorer",
    "fullscreen": "&Fullscreen",
    # Go
    "go_previous": "&Previous Card",
    "go_next": "&Next Card",
    "go_first": "&First Card",
    "go_last": "&Last Card",
    "go_random": "&Random Card",
    "go_previous_deck": "Previous &Deck",
    "go_next_deck": "Ne&xt Deck",
    "find_card": "Find &Card…",
    # Tabs by position
    "tab_n": "Switch to Tab {n}",
    # Canvas
    "summon_card": "Summon Card",
    "add_slot": "Add Card Slot",
    "save_spread": "Save Spread",
    "flip_card": "Flip Card (Reversed)",
    "rotate_card": "Rotate Card",
    "turn_card": "Rotate Card by 15°",
    "turn_card_fine": "Rotate Card by 1°",
    "wheel": "Wheel",
    "delete_card": "Delete Card",
    "bring_to_front": "Bring to Front",
    "send_to_back": "Send to Back",
    "align_cards": "Align Cards",
    "save_layout_as_spread": "Save Layout as Spread",
    "fit_all": "Home view",
    "fullscreen_canvas": "Fullscreen Canvas",
    "cancel_selection": "Cancel Selection",
    # Card view
    "card_toggle_details": "Toggle Card Details",
    "card_cancel": "Leave Fullscreen",
    "card_image_toggle_details": "Toggle Card Details (Art)",
    # Library
    "library_toggle_details": "Toggle Deck Details",
}

# The Preferences dialog
PREFERENCES = {
    "configure": "&Configuration",
    "appearance": "Appearance",
    "text_size": "Font size:",
    "canvas": "Canvas",
    "background": "Background",
    "background_type": "Type:",
    "background_colour_label": "Color:",
    "library": "Library",
    "shortcuts": "Shortcuts",
    "advanced": "Advanced",
    "hardware_acceleration": "Use hardware acceleration",
    "hardware_acceleration_note": "Restart application to take effect.",
    "shortcuts_action": "Action",
    "shortcuts_primary": "Shortcut",
    "shortcuts_alternate": "Alternate",
    "shortcuts_global": "Global",
    "shortcuts_canvas": "Canvas",
    "shortcuts_card": "Card",
    "shortcuts_notes": "Notes",
    "shortcuts_library": "Library",
    "shortcuts_search": "Search…",
    "shortcuts_taken": "Key is bound to {command}.",
    "shortcuts_bare": "{key} can't be a global shortcut.",
    "background_colour": "",
    "canvas_tabs": "Tab icon:",
    "canvas_tab_minimap": "Show a minimap of cards",
    "canvas_guides": "Snapping:",
    "canvas_guides_snap": "Enable card snapping",
    "zoom_in": "Zoom &In",
    "zoom_out": "Zoom &Out",
    "reset_zoom": "&Reset Zoom",
    "title": "Preferences",
    "theme": "Theme:",
    "theme_system": "System",
    "theme_light": "Light",
    "theme_dark": "Dark",
    "background_checkerboard": "Checkerboard",
    "background_gradient": "Gradient",
    "background_swirl": "Dreamy Swirls",
    "background_solid": "Solid Color",
    "canvas_motion": "Canvas Motion:",
    "motion_off": "None",
    "motion_reactive": "Response only",
    "motion_full": "Full",
    "library_label": "Library:",
    "show_available_decks": "Show available decks",
}

# Notes, in a card view and in the Library
NOTES = {
    "section_heading": "Personal Notes",
    "new_note_tooltip": "Create a new note.",
    "name_placeholder": "Name this note…",
    "stub_note": "(empty)",
    "view_name": "Notes",
    "search_placeholder": "Search notes…",
    "details_toggle_show": "Show details",
    "details_toggle_hide": "Hide details",
    "empty_nothing_written": "No notes created yet.",
    "empty_no_match": "Nothing found.",
    "no_notes_on_card": "Nothing for this card.",
    "open_card": "Open note",
    "new_note": "New Note",
    "create_note": "Create New Note",
    "rename": "Rename Note",
    "delete": "Delete Note",
    "export": "Export Note",
    "open": "Open",
    "empty_heading": "No notes yet.",
    "deleted_message": "Note deleted.",
    "undo": "Undo",
    "dismiss": "Dismiss",
    "note_menu_tooltip": "Manage note…",
    "editor_placeholder": "Write your notes here using Markdown...\n\n# Heading\n\n**Bold text**\n\n- List item\n\n[[Link to card or note]]",
    "back_tooltip": "Back to note list",
    "save_tooltip": "Save note (Ctrl+S)",
    "export_filter": "Markdown Files (*.md);;All Files (*)",
    "error": "Error",
    "load_failed": "Could not load note: {error}",
    "rename_failed": "Could not rename note: {error}",
    "mkdir_failed": "Failed to create notes directory: {error}",
    "delete_failed": "Could not delete note: {error}",
    "restore_failed": "Could not restore note: {error}",
    "export_failed": "Could not export note: {error}",
    "save_failed": "Could not save note: {error}",
}


# for keeping slop out (and maybe translation in the future)
def notes_text(key):
    return NOTES.get(key) or ""


# Esoterica, in a card view and in the Library
ESOTERICA = {
    # Between the values of an array, such as keywords
    "joiner": " · ",
    # Passages
    "theme": "Theme",
    "light": "Light",
    "shadow": "Shadow",
    "personality": "Personality",
    "approach": "Approach",
    "story": "Story",
    "x_mythical_spiritual": "Myth and Spirituality",
    "questions": "Questions to ask",
    "affirmation": "Affirmation",
    "x_note": "Note",
    "advice.relationships": "Relationships",
    "advice.work": "Work",
    "advice.spirituality": "Spirituality",
    "advice.personal_growth": "Personal growth",
    "x_marseille_image": "",
    "advice.fortune_telling": "A Potential Future",
    "advice.timing": "A Potential Time",
    "x_suit_cards": "The suit's cards",
    # Correspondences
    "number": "Number",
    "numerology": "Numerology",
    "x_numerology": "",
    "element": "Element",
    "elemental_dignity": "Elemental dignity",
    "x_elemental_dignity": "",
    "planet": "Planet",
    "zodiac": "Zodiac",
    "decan": "Decan",
    "astrology": "Astrology",
    "season": "Season",
    "direction": "Direction",
    "color": "Color",
    "archetype": "Archetype",
    "hebrew_letter": "Hebrew",
    "hebrew_letter_meaning": "",
    "hebrew_letter_value": "",
    "x_hebrew_letter_alt": "",
    # Families of rows
    "family.advice": "Advice",
    "family.symbols": "Symbols",
    "family.divinatory": "Divination",
    "family.correspondences": "Correspondences",
    "family.groups": "Groups",
    # A fold's header: its label and how many rows it holds
    "count": "{label} {count}",
    "show_menu": "Filter",
    "show_menu_tooltip": "Filter by category",
    # Groups; {suit} is the deck's word for the suit, {name} a source's own group
    "group.suits": "For the {suit}",
    "group.ranks": "For this rank",
    "group.classes.pip": "For the pips",
    "group.classes.court": "For the court",
    "group.arcana.major": "For the major arcana",
    "group.arcana.minor": "For the minor arcana",
    "group.all": "For every card",
    "group.custom": "{name}",
    # Under a source's byline, when its text for this card is from another canonical ID.
    # {card} is the deck's name for that card and {card_id} its ID; the patterns are named
    # by the pattern.* keys below
    "reseated": (
        "Text originally from {card} ({card_id}) because this is a {deck_pattern} deck "
        "and the text is for {source_pattern}"
    ),
    "pattern.land.arcana/pattern/rider-waite-smith": "Rider-Waite-Smith",
    "pattern.land.arcana/pattern/tarot-de-marseille": "Marseille",
    "pattern.land.arcana/pattern/thoth": "Thoth",
    # The Library's view of every source. An empty string hides what it labels
    "library.view_name": "Esoterica",
    "library.search_placeholder": "Search esoterica…",
    "library.empty": "Nothing found",
    "library.empty_no_match": "Nothing found",
    "library.details_toggle_show": "Show details",
    "library.details_toggle_hide": "Hide details",
    "library.checkbox_tooltip": "",
    # The list's sections
    "library.section.installed": "Installed",
    "library.section.not_read": "Unreadable",
    # Why a file is under not read
    "library.reason.no_identifier": "No identifier",
    "library.reason.older_format": "Unsupported format",
    "library.reason.unsupported_schema": "Unsupported schema version",
    "library.reason.duplicate_in_root": "Duplicate identifier",
    # The details pane's form, beside the deck pane's own Version: and License:
    "library.form.pattern": "Tarot Pattern:",
    "library.form.about": "About:",
    "library.form.copyright": "Copyright",
    "library.form.identifier": "Identifier",
    # A skipped file's path; no read source shows one
    "library.form.file": "File:",
    # The closed group of what a source's author needs
    "library.source_file_heading": "File Details",
    "library.form.shadows": "Shadows:",
    "library.form.groups": "Groups:",
    # [meta.work], the work a source draws on, in a group of its own
    "library.work_heading": "Work of",
    # The grid's first row, as the deck view and the card explorer head the majors
    "library.coverage.major": "Major Arcana",
    # The work group's heading when the source names its relation to the work
    "library.relation.transcribes": "Transcription of",
    "library.relation.abridges": "Abridges",
    "library.relation.annotates": "Annotates",
    "library.form.work_name": "Title:",
    "library.form.work_author": "Author:",
    "library.form.work_published": "Published:",
    "library.form.work_isbn": "ISBN:",
    "library.form.work_url": "URL:",
}

# A registered key and its x_ spelling share one label
_SPELLINGS = {
    "numerology": "x_numerology",
    "x_numerology": "numerology",
    "elemental_dignity": "x_elemental_dignity",
    "x_elemental_dignity": "elemental_dignity",
}


def label_for(key):
    """The label for an entry, family or group key; empty hides what it labels."""
    return ESOTERICA.get(key) or ESOTERICA.get(_SPELLINGS.get(key), "") or ""


# What the library says about catalog downloads
DOWNLOAD = {
    "installed_toast": "Installed {name}",
    "failed: network": "Network error",
    "failed: http": "Transport error",
    "failed: integrity": "Checksum doesn't match",
    "failed: container": "Zip container is busted",
    "failed: destination exists": "Directory with same name already exists",
    "failed: filesystem": "Internal filesystem error",
    "failed: cancelled": "Cancelled",
}


def failure_text(failure):
    return DOWNLOAD[f"failed: {failure.kind.value}"]


# The deck view's view switch
DECK_VIEW = {
    "sections_name": "Sections",
    "sections_tooltip": "Show cards by arcana",
    "tableau_name": "Tableau",
    "tableau_tooltip": "Show cards in tableau",
    "view_bar_name": "View",
    "find_card": "Find card…",
    "new_canvas_from_selection": "Create New Canvas From Selection",
    "cover_size": "Cover size",
    "open_card": "&Open Card",
    "open_cards": "&Open Cards",
    "copy_card": "&Copy Card",
    "copy_cards": "&Copy Cards",
    "major_arcana": "Major Arcana",
    "note": "Note: {reason}",
    # The header
    "buy": "Buy Deck",
    "yes": "Yes",
    "no": "No",
    "cover_of": "Cover of {name}",
    "no_cover": "No cover",
    "details": "Details",
    "details_tooltip": "Show the rest of this deck's metadata",
    "card_count": "{count} cards",
    "hide_metadata": "Hide deck metadata",
    "show_metadata": "Show deck metadata",
    # The header's rows, by key in deck.toml's [deck]
    "field.description": "Description",
    "field.license": "License",
    "field.copyright": "Copyright",
    "field.attribution": "Attribution",
    "field.publisher": "Publisher",
    "field.website": "Website",
    "field.links.homepage": "Homepage",
    "field.links.artist": "Artist",
    "field.links.buy": "Buy",
    "field.links.source": "Source",
    "field.created_date": "Created",
    "field.updated_date": "Updated",
    "field.published_date": "Published",
    "field.tags": "Tags",
    "field.id": "Identifier",
    "field.version": "Version",
    "field.schema_version": "Schema version",
}

# The canvas
CANVAS = {
    "open_card": "Open Card",
    "rotate_tooltip": "Rotate Card",
    "swap_deck": "Swap from Deck",
    "tab_name": "Canvas",
    "leave_fullscreen": "Leave fullscreen (Esc)",
    "fullscreen_tooltip": "Fullscreen canvas",
    # The toolbar
    "section_cards": "Cards",
    "section_arrange": "Arrange",
    "section_view": "View",
    "summon_tooltip": "Summon a random card",
    "flip_tooltip": "Flip card",
    "delete_tooltip": "Remove selected card",
    "paste": "Paste",
    "paste_tooltip": "Paste card",
    "bring_to_front_tooltip": "Bring card to front",
    "send_to_back_tooltip": "Send card to back",
    "align_tooltip": "Align selected cards",
    "zoom_in_tooltip": "Zoom in",
    "zoom_out_tooltip": "Zoom out",
    "fit_tooltip": "Fit cards",
    # The align menu
    "align_horizontal": "Horizontal Align",
    "align_left": "Left Edges",
    "align_centers": "Centers",
    "align_right": "Right Edges",
    "align_vertical": "Vertical Align",
    "align_top": "Top Edges",
    "align_bottom": "Bottom Edges",
    "distribute_horizontal": "Distribute Horizontally",
    "distribute_vertical": "Distribute Vertically",
    "arrange_arc": "Arrange in Circle",
    # The arc popover
    "arc_bend": "Bend:",
    "arc_turn": "Rotation:",
    "arc_direction": "Direction:",
    "arc_cards": "Orientation:",
    "arc_spacing": "Gap:",
    "arc_clockwise": "Clockwise",
    "arc_anticlockwise": "Counter clockwise",
    "arc_upright": "Upright",
    "arc_follow": "Turned",
    "arc_degrees": "{degrees} degrees",
    "arc_gap": "{gap} card-widths",
    # A move's undo text
    "move_card": "Move {name}",
    "card_fallback": "Card",
}


SPREADS = {
    "untitled": "Untitled spread",
    # The toolbar
    "section_slots": "Slots",
    "add_slot_tooltip": "Add card slot",
    "save_tooltip": "Save this spread",
    "pane_tooltip": "Toggle details",
    # The title band
    "details_show": "Show Details",
    "details_hide": "Hide Details",
    "name_title": "Name",
    "name_hint": "Name this spread…",
    "description_title": "Description",
    "description_hint": "Optional: how to read this spread",
    "description_expand": "Expand description",
    "description_collapse": "Hide description",
    "source_url_hint": "Webpage for this spread",
    "source_author_hint": "Who created this spread",
    "source_note_hint": "Free-form notes",
    "source_url_title": "URL",
    "source_author_title": "Author",
    "source_note_title": "Note",
    "add_source": "Add Source",
    "source_took": "{taken} from {source}",
    "source_year": "{source} ({year})",
    "took_positions": "positions",
    "took_layout": "layout",
    "took_words": "wording",
    "took_list_separator": ", ",  # for i18n
    "took_last_pair": "{rest} and {last}",
    "remove_source": "Remove Source",
    "slots_title": "Card Slots",
    "slots_empty": "No cards yet",
    # The pane
    "label_hint": "Label",
    "meaning_hint": "Optional: what does a card in this slot mean?",
    "slot_row": "{number}. {label}",
    # The pane's menu
    "menu_tooltip": "Spread options",
    "edit": "Edit",
    "duplicate": "Duplicate Spread",
    "revert": "Revert to Saved",
    "open_folder": "Open in File Explorer",
    "revert_title": "Revert Spread",
    "revert_text": 'Discard your changes to "{name}" and revert back to the saved version?',
    # A slot's menu
    "edit_label": "Edit Label…",
    "edit_meaning": "Edit Meaning…",
    "number": "Number",
    "move_earlier": "Move up",
    "move_later": "Move down",
    # The tab
    "unsaved_tab": "{title} *",
    "rename_title": "Rename Spread",
    "rename_prompt": "Enter name:",
    "close_unsaved_title": "Close Spread",
    "close_unsaved_text": 'The spread "{name}" has been modified. Do you want to save your changes or discard them?',
    # Failures
    "save_failed": "Failed to save spread",
    "open_failed": "Cannot open spread",
    "open_folder_failed": "Cannot open folder",
    "delete_failed": "Cannot delete spread",
    "restore_failed": "Cannot restore spread",
    # The canvas's toolbar
    "save_layout_tooltip": "Save this layout as a new spread",
    # The Library's view
    "view_name": "Spreads",
    "search_placeholder": "Search spreads…",
    "empty": "No spreads yet",
    "empty_no_match": "Nothing found",
    "details_toggle_show": "Show details",
    "details_toggle_hide": "Hide details",
    "slot_count": "{count} cards",
    "slot_count_one": "single card",
    "section_mine": "Your Spreads",
    "section_included": "Installed",
    "sort_tooltip": "Sort spreads",
    "sort_newest": "Newest",
    "sort_edited": "Recently modified",
    "delete": "Delete Spread",
    "deleted_message": "Spread deleted",
}

# The first-run dialog, and the command line
SETUP = {
    "title": "First-time Setup",
    "welcome": "Welcome to Tarot Canvas!",
    "description": "Before we start, we need to download the Rider-Waite-Smith tarot deck.",
    "preparing": "Preparing to download...",
    "retry": "Retry Download",
    "starting": "Starting download...",
    "downloading": "Downloading deck...",
    "extracting_start": "Download complete. Extracting...",
    "extracting": "Extracting files...",
    "done": "Setup complete",
    "complete": "Download complete! Starting application...",
    "failed": "Download failed: {error}",
    "error": "Error",
    "load_failed": "Failed to load the reference deck after downloading. The application will now exit.",
    "load_error": "Error loading reference deck: {error}\nThe application will now exit.",
    "uri_help": "Open a specific card by URI",
}

# The window, its menus and the welcome tab
MAIN_WINDOW = {
    "app_name": "Tarot Canvas",
    "menu_file": "&File",
    "menu_edit": "&Edit",
    "menu_view": "&View",
    "menu_go": "&Go",
    "menu_tools": "&Tools",
    "menu_settings": "&Settings",
    "menu_theme": "&Theme",
    "menu_help": "&Help",
    "log_viewer": "&Log Viewer",
    "theme_system": "&System Default",
    "theme_light": "&Light",
    "theme_dark": "&Dark",
    "faq": "&Frequently Asked Questions",
    "report_bug": "&Report Bug",
    "about": "&About Tarot Canvas",
    "new_reading_from_spread": "New Reading",
    "new_tab_tooltip": "New tab",
    "search_tooltip": "Search Cards",
    "welcome_tab": "Welcome",
    "welcome_heading": "Welcome to Tarot Canvas!",
    "welcome_prompt": "Select a card on the left or choose an option below:",
    "welcome_new_reading": "New Reading",
    "welcome_new_canvas": "New Canvas",
    "welcome_open_deck": "Open Standard Deck",
    "welcome_library": "Deck Library",
    "welcome_random_card": "Pick Random Card",
    "canvas_tab": "Canvas",
    "canvas_tab_numbered": "Canvas ({n})",
    "rename_canvas": "Rename Canvas",
    "rename_canvas_prompt": "Enter a new name for this canvas:",
    "select_deck": "Select Tarot Deck Directory",
    "invalid_deck": "Invalid Deck Directory",
    "invalid_deck_detail": (
        "The selected directory does not contain a deck.toml file.\n"
        "Please select a valid tarot deck directory."
    ),
    "deck_load_failed": "Could not open deck: {error}",
    "deck_not_found": "Deck Not Found",
    "deck_not_found_detail": "The reference deck could not be loaded.",
}

# A card view
CARD_VIEW = {
    "tab_fallback": "Card View",
    "tab_overview": "Overview",
    "tab_esoterica": "Esoterica",
    "tab_notes": "Notes",
    "no_card": "No deck or card available",
    "no_card_info": "No card information available",
    "no_image": "No image available",
    "copied": "Copied {name}",
    "leave_fullscreen": "Leave fullscreen (Esc)",
    "exit_fullscreen_hint": "Press Esc to exit fullscreen",
    "hide_details": "Hide card details",
    "show_details": "Show card details",
    # The bar over the art
    "other_decks_tooltip": "Show this card from another deck ([ and ])",
    "copy": "Copy",
    "copy_tooltip": "Copy card",
    "zoom": "Zoom",
    "zoom_in": "Zoom In",
    "zoom_out": "Zoom Out",
    "fit": "Fit",
    "actual_size": "Actual Size\tDouble-click",
    "fullscreen": "Fullscreen",
    "details": "Details",
    # The card preview
    "major_arcana": "Major Arcana",
    "preview_no_image": "No Image",
    "preview_image_error": "Image Error",
    # The Esoterica tab with nothing to show; {faq} is a URL
    "esoterica_heading": "Esoterica",
    "esoterica_explanation": (
        "Per-card meanings, associations and symbolism will show up here. See the "
        '<a href="{faq}">Frequently Asked Questions</a> for how to add your own.'
    ),
    "esoterica_no_content": "No esoteric content available for this card.",
    "esoterica_help_tooltip": "About Esoterica",
    "esoterica_help_name": "About Esoterica",
}

# The Library's decks
LIBRARY = {
    "tab_title": "Library",
    "decks_view": "Decks",
    "search_decks": "Search decks…",
    "sort_tooltip": "Sort decks",
    "sort_name": "Name",
    "sort_author": "Author",
    "sort_count": "Card count",
    "sort_recent": "Recently opened",
    "cover_size": "Cover size",
    "open_deck": "Open Deck…",
    "hide_details": "Hide deck details",
    "show_details": "Show deck details",
    "empty_no_match": "No decks match your search.",
    "empty_no_decks": "No decks installed yet. Use Add Deck… to install one.",
    "unknown_author": "Unknown",
    "majors_only": "majors only",
    "majors_short": "majors",
    # The details pane; the esoterica view's pane shares the first two
    "form_version": "Version:",
    "form_license": "License:",
    "form_size": "Size:",
    "form_cards": "Cards:",
    "open": "Open",
    "download": "Download",
    "cancel": "Cancel",
    "try_again": "Try Again",
}

# The About dialog; {link} is an HTML link
ABOUT = {
    "title": "About Tarot Canvas",
    "tab_about": "About",
    "tab_whats_new": "What's New",
    "tab_authors": "Authors",
    "version": "Version {version}",
    "license": "{license} License",
    "report_bugs": "Please use {link} to report bugs.",
    "help": "If you have questions or need help, please visit the {link}.",
    "faq": "Frequently Asked Questions",
    "maintainer": "Maintainer",
    "email_tooltip": "Email {name} at {email}",
    "email_name": "Email {name}",
}

# The log viewer
LOG_VIEWER = {
    "title": "Log Viewer",
    "minimum_level": "Minimum Level:",
    "level_debug": "Debug",
    "level_info": "Info",
    "level_warning": "Warning",
    "level_error": "Error",
    "level_critical": "Critical",
    "auto_scroll": "Auto-scroll",
    "search": "Search:",
    "refresh": "Refresh",
    "load_error": "Error loading log file: {error}",
    "line_error": "Error processing log line: {error}",
}

# A reading dealt from a spread
READINGS = {
    "open": "Start Reading",
    "open_with": "Start Reading With",
    "browse_spreads": "Browse Spreads…",
    "question_hint": "Question or topic…",
    "deal": "Begin Reading",
    "begin": "Finish",
    "turn_all": "Reveal All",
    "turn_next": "Reveal Next",
    "reversals": "Reversals",
    "reversals_with": "With reversals",
    "reversals_without": "Without reversals",
    "card_reversed": "{card} (reversed)",
    "date_and_time": "{date} · {time}",
    "short_deal": ("No more cards (dealt all {dealt})"),
}

# The command palette
PALETTE = {
    "title": "Find Card",
    "search": "Search for cards...",
    "hint": "Press Enter to {action}",
    "add_to_canvas": "Add to Canvas",
    "open_card_view": "Open Card View",
    "open": "Open",
}

# The card explorer
EXPLORER = {
    "title": "Card Explorer",
    "hide": "Hide Card Explorer",
    "header": "Cards",
    "major_arcana": "Major Arcana",
    "open_card": "&Open Card",
    "copy_card": "&Copy Card",
}

# How long ago something was
DATES = {
    "today": "Today",
    "yesterday": "Yesterday",
    "days_ago": "{days} days ago",
    "week_ago": "1 week ago",
    "weeks_ago": "{weeks} weeks ago",
}

# What a licence is called on screen, for the identifiers decks and sources write
LICENSES = {
    "LicenseRef-McElroy-Uncopyright": "Uncopyright",
    "LicenseRef-AllRightsReserved": "All Rights Reserved",
    "CC0-1.0": "CC0 1.0 Universal",
    "CC-BY-4.0": "CC BY 4.0",
    "CC-BY-SA-4.0": "CC BY-SA 4.0",
    "CC-BY-NC-SA-3.0": "CC BY-NC-SA 3.0",
}


def license_name(value):
    """The name for a licence identifier, or the value itself; None stays None"""
    if value is None:
        return None
    return LICENSES.get(value.strip(), value)
