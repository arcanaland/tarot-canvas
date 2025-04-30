import sys
from PyQt6.QtWidgets import QApplication
from tarot_canvas.ui.main_window import MainWindow
from tarot_canvas.models.reference_deck import ReferenceDeck

def initialize_reference_deck():
    if not ReferenceDeck.is_reference_deck_present():
        print("Reference deck not found. Setting up...")
        try:
            ReferenceDeck.download_reference_deck()
        except Exception as e:
            print(f"Error setting up the reference deck: {e}")
            sys.exit(1)

def main():
    initialize_reference_deck()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

