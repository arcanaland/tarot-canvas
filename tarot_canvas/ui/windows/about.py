"""The about dialog."""

from __future__ import annotations

import platform
from importlib.resources import files

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont, QIcon, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import AboutData, Person, load_about_data

ICON_PATH = files("tarot_canvas.resources.icons").joinpath("icon.png")

ICON_SIZE = 64

DEFAULT_SIZE = (560, 480)

LICENSE_URLS = {
    "MIT": "https://opensource.org/license/mit",
}

MAIL_ICON_NAMES = ("mail-message-new", "mail-send", "mail-message")


def _link(url: str, label: str | None = None) -> str:
    return f'<a href="{url}">{label or url}</a>'


class AboutDialog(QDialog):
    def __init__(self, parent=None, about: AboutData | None = None):
        super().__init__(parent)
        self.setWindowTitle("About Tarot Canvas")
        self.setMinimumSize(*DEFAULT_SIZE)
        self.resize(*DEFAULT_SIZE)

        self.about = about if about is not None else load_about_data()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self._build_header(), 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_about_tab(), "About")
        self.tabs.addTab(self._build_components_tab(), "Components")
        self.tabs.addTab(self._build_authors_tab(), "Authors")
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # -- header ---------------------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        row = QHBoxLayout(header)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(16)

        icon_label = QLabel()
        icon_label.setPixmap(self._app_icon().pixmap(ICON_SIZE, ICON_SIZE))
        icon_label.setFixedSize(ICON_SIZE, ICON_SIZE)
        row.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(0)
        text.addStretch()

        name_label = QLabel(self.about.name)
        name_font = QFont(name_label.font())
        name_font.setPointSizeF(name_font.pointSizeF() * 1.9)
        name_label.setFont(name_font)
        text.addWidget(name_label)

        self.version_label = QLabel(f"Version {self.about.version}")
        version_font = QFont(self.version_label.font())
        version_font.setPointSizeF(version_font.pointSizeF() * 1.2)
        self.version_label.setFont(version_font)
        self.version_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(self.version_label)
        text.addStretch()

        row.addLayout(text, 1)
        return header

    def _app_icon(self) -> QIcon:
        icon = QIcon.fromTheme(self.about.app_id)
        if icon.isNull():
            icon = QIcon(str(ICON_PATH))
        return icon

    # -- tabs -----------------------------------------------------------------

    def _build_about_tab(self) -> QWidget:
        license_url = LICENSE_URLS.get(self.about.license)
        license_text = f"{self.about.license} License"

        page, layout = self._page()
        layout.addWidget(self._body_label(self.about.summary))
        layout.addWidget(self._body_label(self.about.copyright))
        layout.addSpacing(4)
        layout.addWidget(
            self._body_label(_link(license_url, license_text) if license_url else license_text)
        )
        if self.about.homepage:
            layout.addWidget(self._body_label(_link(self.about.homepage)))
        layout.addStretch()
        return page

    def _build_components_tab(self) -> QWidget:
        page, layout = self._page()
        self._add_rows(
            layout,
            [
                self._detail_row("Qt", QT_VERSION_STR),
                self._detail_row("PyQt6", PYQT_VERSION_STR),
                self._detail_row("Python", platform.python_version()),
            ],
        )
        layout.addStretch()
        return page

    def _build_authors_tab(self) -> QWidget:
        page, layout = self._page()

        if self.about.bugtracker:
            layout.addWidget(
                self._body_label(f"Please use {_link(self.about.bugtracker)} to report bugs.")
            )
        if self.about.faq:
            layout.addWidget(
                self._body_label(
                    "If you have questions or need help, please visit "
                    f"{_link(self.about.faq, 'the Frequently Asked Questions')}."
                )
            )

        layout.addSpacing(8)
        self._add_rows(layout, [self._author_row(person) for person in self.about.authors])
        layout.addStretch()
        return page

    # -- the shared row idiom -------------------------------------------------

    def _author_row(self, person: Person) -> QWidget:
        return self._detail_row(person.name, person.role, self._mail_button(person))

    def _detail_row(self, title: str, subtitle: str, trailing: QWidget | None = None) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 6, 0, 6)

        text = QVBoxLayout()
        text.setSpacing(0)

        title_label = QLabel(title)
        title_font = QFont(title_label.font())
        title_font.setBold(True)
        title_label.setFont(title_font)
        text.addWidget(title_label)

        subtitle_label = self._body_label(subtitle)
        subtitle_label.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        text.addWidget(subtitle_label)

        layout.addLayout(text, 1)
        if trailing is not None:
            layout.addWidget(trailing, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    @staticmethod
    def _add_rows(layout: QVBoxLayout, rows: list[QWidget]) -> None:
        for index, row in enumerate(rows):
            if index:
                separator = QFrame()
                separator.setFrameShape(QFrame.Shape.HLine)
                separator.setFrameShadow(QFrame.Shadow.Sunken)
                layout.addWidget(separator)
            layout.addWidget(row)

    def _mail_button(self, person: Person) -> QToolButton | None:
        if not person.email:
            return None

        button = QToolButton()
        button.setAutoRaise(True)
        icon = self._mail_icon()
        if icon.isNull():
            button.setText("✉")
        else:
            button.setIcon(icon)
        button.setToolTip(f"Email {person.name} at {person.email}")
        button.setAccessibleName(f"Email {person.name}")
        button.clicked.connect(
            lambda _checked=False, email=person.email: QDesktopServices.openUrl(
                QUrl(f"mailto:{email}")
            )
        )
        return button

    @staticmethod
    def _mail_icon() -> QIcon:
        for name in MAIL_ICON_NAMES:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                return icon
        return QIcon()

    # -- helpers --------------------------------------------------------------

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        return page, layout

    @staticmethod
    def _body_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setOpenExternalLinks(True)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        return label
