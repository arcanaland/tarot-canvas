import os
import zipfile
import requests
from xdg_base_dirs import xdg_data_home


class ReferenceDeck:
    REFERENCE_DECK_URL = "https://github.com/arcanaland/reference-decks/releases/download/rider-waite-smith%2Fv1.0/rider-waite-smith-1.0.zip"
    REFERENCE_DECK_DIR = "reference-decks"
    REFERENCE_DECK_NAME = "rider-waite-smith"

    @staticmethod
    def get_reference_deck_path():
        return xdg_data_home() / "tarot-canvas" / ReferenceDeck.REFERENCE_DECK_DIR

    @staticmethod
    def is_reference_deck_present():
        reference_deck_path = os.path.join(
            ReferenceDeck.get_reference_deck_path(),
            ReferenceDeck.REFERENCE_DECK_NAME
        )
        return os.path.exists(reference_deck_path)

    @staticmethod
    def download_reference_deck():
        reference_deck_path = ReferenceDeck.get_reference_deck_path()
        os.makedirs(reference_deck_path, exist_ok=True)

        zip_file_path = os.path.join(reference_deck_path, "rider-waite-smith.zip")
        print(f"Downloading reference deck to {zip_file_path}...")

        response = requests.get(ReferenceDeck.REFERENCE_DECK_URL, stream=True)
        if response.status_code == 200:
            with open(zip_file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    f.write(chunk)
            print("Download complete.")
        else:
            raise Exception(f"Failed to download the reference deck. Status code: {response.status_code}")

        print(f"Extracting reference deck to {reference_deck_path}...")
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            zip_ref.extractall(reference_deck_path)

        os.remove(zip_file_path)

