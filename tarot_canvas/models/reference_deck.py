import os
import zipfile
import requests
import shutil
from tarot_canvas.utils.path_helper import get_data_directory


class ReferenceDeck:
    REFERENCE_DECK_URL = "https://github.com/arcanaland/reference-decks/releases/download/rider-waite-smith%2Fv1.1/rider-waite-smith-1.1.zip"
    REFERENCE_DECK_DIR = "reference-decks"
    REFERENCE_DECK_NAME = "rider-waite-smith"

    @staticmethod
    def get_reference_deck_path():
        return get_data_directory("tarot-canvas") / ReferenceDeck.REFERENCE_DECK_DIR / ReferenceDeck.REFERENCE_DECK_NAME

    @staticmethod
    def is_reference_deck_present():
        return os.path.exists(ReferenceDeck.get_reference_deck_path())

    @staticmethod
    def download_reference_deck(progress_callback=None):
        parent_dir = get_data_directory("tarot-canvas") / ReferenceDeck.REFERENCE_DECK_DIR
        reference_deck_path = parent_dir / ReferenceDeck.REFERENCE_DECK_NAME
        
        # Create parent directory
        os.makedirs(parent_dir, exist_ok=True)
        
        # Remove existing directory if it exists (to avoid nested directories)
        if os.path.exists(reference_deck_path):
            shutil.rmtree(reference_deck_path)
        
        # Temporary extraction directory
        temp_extract_dir = parent_dir / "temp_extract"
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
        os.makedirs(temp_extract_dir, exist_ok=True)
        
        zip_file_path = os.path.join(parent_dir, "rider-waite-smith.zip")
        
        if progress_callback:
            progress_callback(0, "Starting download...")
        
        # Get file size for progress calculation
        try:
            response = requests.head(ReferenceDeck.REFERENCE_DECK_URL)
            total_size = int(response.headers.get('content-length', 0))
        except Exception:
            total_size = 0  # If we can't get size, we'll show indeterminate progress

        # Download the file
        response = requests.get(ReferenceDeck.REFERENCE_DECK_URL, stream=True)
        if response.status_code == 200:
            downloaded = 0
            with open(zip_file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=4096):
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Update progress if callback provided
                    if progress_callback and total_size > 0:
                        percent = int(downloaded * 50 / total_size)  # 0-50% for download
                        progress_callback(percent, "Downloading deck...")
            
            if progress_callback:
                progress_callback(50, "Download complete. Extracting...")
        else:
            raise Exception(f"Failed to download the reference deck. Status code: {response.status_code}")

        # Extract the zip file to a temporary directory first
        with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
            # Get total files for extraction progress
            total_files = len(zip_ref.namelist())
            extracted = 0
            
            # Extract to temp directory
            for file in zip_ref.namelist():
                zip_ref.extract(file, temp_extract_dir)
                extracted += 1
                
                # Update progress if callback provided
                if progress_callback and total_files > 0:
                    percent = 50 + int(extracted * 50 / total_files)  # 50-100% for extraction
                    progress_callback(percent, "Extracting files...")

        # Now move the correct directory to the final location
        # Find the rider-waite-smith directory within the extracted content
        extracted_deck_dir = os.path.join(temp_extract_dir, "rider-waite-smith")
        if os.path.exists(extracted_deck_dir):
            # Move the content to the final destination
            shutil.move(extracted_deck_dir, parent_dir)
        else:
            # Just rename the temp directory to the final name
            shutil.move(temp_extract_dir, reference_deck_path)

        # Clean up
        os.remove(zip_file_path)
        if os.path.exists(temp_extract_dir):
            shutil.rmtree(temp_extract_dir)
        
        if progress_callback:
            progress_callback(100, "Setup complete")

