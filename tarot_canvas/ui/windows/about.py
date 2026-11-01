"""The about dialog."""

from __future__ import annotations

import html
from importlib.resources import files

from PyQt6.QtCore import QDate, QEvent, Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QIcon, QPalette
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from tarot_canvas.about import AboutData, Person, Release, load_about_data
from tarot_canvas.ui import typography
from tarot_canvas.ui.strings import ABOUT
from tarot_canvas.utils.dates import relative_date_from_iso

ICON_PATH = files("tarot_canvas.resources.icons").joinpath("icon.png")

ICON_SIZE = 64

DEFAULT_SIZE = (560, 480)

LICENSE_URLS = {
    "MIT": "https://opensource.org/license/mit",
}

MAIL_ICON_NAMES = ("mail-message-new", "mail-send", "mail-message")

# Space above each release after the first, in px
RELEASE_SPACING = 24


def app_icon(app_id: str) -> QIcon:
    """The theme's icon for the app, else the one bundled with it."""
    icon = QIcon.fromTheme(app_id)
    if icon.isNull():
        icon = QIcon(str(ICON_PATH))
    return icon


def _link(url: str, label: str | None = None) -> str:
    return f'<a href="{url}">{label or url}</a>'


def _release_date(iso: str, today: QDate | None = None) -> str:
    """How long ago an ISO date was.."""
    return relative_date_from_iso(iso, today)


class AboutDialog(QDialog):
    # Absent when there are no releases
    whats_new: QTextBrowser | None = None

    def __init__(self, parent=None, about: AboutData | None = None):
        super().__init__(parent)
        self.setWindowTitle(ABOUT["title"])
        self.setMinimumSize(*DEFAULT_SIZE)
        self.resize(*DEFAULT_SIZE)

        self.about = about if about is not None else load_about_data()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(self._build_header(), 0)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_about_tab(), ABOUT["tab_about"])
        if self.about.releases:
            self.tabs.addTab(self._build_whats_new_tab(), ABOUT["tab_whats_new"])
        self.tabs.addTab(self._build_authors_tab(), ABOUT["tab_authors"])
        layout.addWidget(self.tabs, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self.whats_new is not None:
            self.whats_new.setHtml(self._releases_html())

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

        name_label = typography.apply(QLabel(self.about.name), typography.Role.HEADING_1)
        text.addWidget(name_label)

        self.version_label = QLabel(ABOUT["version"].format(version=self.about.version))
        typography.apply(self.version_label, typography.Role.HEADING_2)
        self.version_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text.addWidget(self.version_label)
        text.addStretch()

        row.addLayout(text, 1)
        return header

    def _app_icon(self) -> QIcon:
        return app_icon(self.about.app_id)

    # -- tabs -----------------------------------------------------------------

    def _build_about_tab(self) -> QWidget:
        license_url = LICENSE_URLS.get(self.about.license)
        license_text = ABOUT["license"].format(license=self.about.license)

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

    def _build_whats_new_tab(self) -> QWidget:
        page, layout = self._page()

        self.whats_new = QTextBrowser()
        self.whats_new.setFrameShape(QFrame.Shape.NoFrame)
        self.whats_new.setOpenExternalLinks(True)
        # Sit on the tab's background, flush with its margins, like the labels on the other tabs
        self.whats_new.viewport().setAutoFillBackground(False)
        self.whats_new.document().setDocumentMargin(0)
        self.whats_new.setHtml(self._releases_html())

        layout.addWidget(self.whats_new)
        return page

    def _releases_html(self) -> str:
        # The subtitle colour of _detail_row
        detail = self.palette().color(QPalette.ColorRole.PlaceholderText).name()
        return "".join(
            self._release_html(release, detail, RELEASE_SPACING if index else 0)
            for index, release in enumerate(self.about.releases)
        )

    @staticmethod
    def _release_html(release: Release, detail_colour: str, top_margin: int) -> str:
        return (
            f'<p style="margin-top:{top_margin}px; margin-bottom:0">'
            f"<b>{html.escape(release.version)}</b><br>"
            f'<span style="color:{detail_colour}">{html.escape(_release_date(release.date))}</span>'
            f"</p>{release.description}"
        )

    def _build_authors_tab(self) -> QWidget:
        page, layout = self._page()

        if self.about.bugtracker:
            layout.addWidget(
                self._body_label(ABOUT["report_bugs"].format(link=_link(self.about.bugtracker)))
            )
        if self.about.faq:
            layout.addWidget(
                self._body_label(ABOUT["help"].format(link=_link(self.about.faq, ABOUT["faq"])))
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

        title_label = typography.apply(QLabel(title), typography.Role.HEADING_4)
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
        button.setToolTip(ABOUT["email_tooltip"].format(name=person.name, email=person.email))
        button.setAccessibleName(ABOUT["email_name"].format(name=person.name))
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
