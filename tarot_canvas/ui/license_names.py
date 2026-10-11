"""What a licence is called on screen, for the identifiers decks and sources write"""

LICENSE_NAMES = {
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
    return LICENSE_NAMES.get(value.strip(), value)
