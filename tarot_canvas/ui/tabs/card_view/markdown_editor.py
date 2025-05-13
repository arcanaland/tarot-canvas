from PyQt6.QtWidgets import QPlainTextEdit, QCompleter
from PyQt6.QtGui import QTextCursor, QColor, QSyntaxHighlighter, QTextCharFormat, QFont
from PyQt6.QtCore import Qt, QRegularExpression, pyqtSignal, QStringListModel

class MarkdownHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for the Markdown format"""
    
    def __init__(self, document):
        super().__init__(document)
        
        self.highlighting_rules = []
        
        # Header format (# Header)
        header_format = QTextCharFormat()
        header_format.setFontWeight(QFont.Weight.Bold)
        header_format.setForeground(QColor("#569CD6"))  # Blue
        self.highlighting_rules.append((
            QRegularExpression(r"^#+ .*$"),
            header_format
        ))
        
        # Bold format (**bold**)
        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Weight.Bold)
        self.highlighting_rules.append((
            QRegularExpression(r"\*\*.*?\*\*"),
            bold_format
        ))
        
        # Italic format (*italic*)
        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        self.highlighting_rules.append((
            QRegularExpression(r"\*[^\*]+\*"),
            italic_format
        ))
        
        # List items (- item)
        list_format = QTextCharFormat()
        list_format.setForeground(QColor("#CE9178"))  # Orange
        self.highlighting_rules.append((
            QRegularExpression(r"^\s*[\-\*] .*$"),
            list_format
        ))
        
        # Links and references
        link_format = QTextCharFormat()
        link_format.setForeground(QColor("#4EC9B0"))  # Teal
        # Markdown links [text](url)
        self.highlighting_rules.append((
            QRegularExpression(r"\[.*?\]\(.*?\)"),
            link_format
        ))
        # Internal wiki-style links [[reference]]
        self.highlighting_rules.append((
            QRegularExpression(r"\[\[.*?\]\]"),
            link_format
        ))
    
    def highlightBlock(self, text):
        for pattern, format in self.highlighting_rules:
            matches = pattern.globalMatch(text)
            while matches.hasNext():
                match = matches.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), format)

class MarkdownEditor(QPlainTextEdit):
    """Enhanced markdown editor with auto-completion and formatting helpers"""
    
    linkClicked = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_tab = parent
        
        # Set up font and line wrapping
        font = QFont("Consolas, 'DejaVu Sans Mono', monospace", 10)
        self.setFont(font)
        #self.setWordWrapMode(QPlainTextEdit.rdWrapMode.WidgetWidth)
        self.setPlaceholderText("Write your notes here using Markdown...\n\n# Heading\n\n**Bold text**\n\n- List item\n\n[[Link to card or note]]")
        
        # Syntax highlighting
        self.highlighter = MarkdownHighlighter(self.document())
        
        # Tab width
        self.setTabStopDistance(40)  # 4 spaces
        
        # Auto-completion
        self.completer = None
        self.setup_completer()
        
        # Track link detection
        self.last_link_position = None
    
    def setup_completer(self):
        """Set up auto-completion for wiki links"""
        self.completer = QCompleter(self)
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.setMaxVisibleItems(10)
        
        # Hide initially
        self.completer.popup().hide()
        
        # Connect signals
        self.completer.activated.connect(self.insert_completion)
        
        # Empty model initially
        self.completer.setModel(QStringListModel([]))
    
    def set_completion_items(self, items):
        """Set the list of items for auto-completion"""
        if not items:
            items = []
        model = QStringListModel(items)
        self.completer.setModel(model)
    
    def keyPressEvent(self, event):
        """Handle key press events for auto-completion and formatting"""
        if self.completer and self.completer.popup().isVisible():
            # Keys that are used by the completer
            if event.key() in (Qt.Key.Key_Enter, Qt.Key.Key_Return, Qt.Key.Key_Escape, 
                              Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                event.ignore()
                return
                
        # Auto-insert closing brackets and formatting marks
        if event.key() == Qt.Key.Key_BracketLeft and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            # If the user types '[' check if it's a second consecutive one for a wiki link
            cursor = self.textCursor()
            pos = cursor.position()
            if pos > 0 and self.toPlainText()[pos-1] == '[':
                # Double bracket detected, insert closing brackets too
                super().keyPressEvent(event)
                self.insertPlainText("]]")
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 2)
                self.setTextCursor(cursor)
                return
        elif event.key() == Qt.Key.Key_ParenLeft:
            # Auto-close parentheses
            super().keyPressEvent(event)
            self.insertPlainText(")")
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor)
            self.setTextCursor(cursor)
            return
        elif event.key() == Qt.Key.Key_8 and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            # If the user types '*', check if it's for bold
            cursor = self.textCursor()
            if cursor.hasSelection():
                text = cursor.selectedText()
                cursor.removeSelectedText()
                self.insertPlainText(f"**{text}**")
                return
        
        # Check for auto-completion trigger
        if event.key() == Qt.Key.Key_BracketLeft and not self.completer.popup().isVisible():
            cursor = self.textCursor()
            pos = cursor.position()
            if pos > 0 and self.toPlainText()[pos-1] == '[':
                # Start of a wiki link, show completion
                self.start_link_completion()
            
        # Regular key processing
        super().keyPressEvent(event)
        
        # Check after processing for wiki link completion
        cursor = self.textCursor()
        text_before_cursor = self.toPlainText()[:cursor.position()]
        if "[[" in text_before_cursor and "]]" not in text_before_cursor[-2:]:
            # We're inside a wiki link, show/update completion
            self.update_link_completion()
        else:
            # Not in a wiki link anymore
            self.completer.popup().hide()
    
    def mousePressEvent(self, event):
        """Handle mouse clicks for link detection"""
        super().mousePressEvent(event)
        
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = self.cursorForPosition(event.pos())
            self.check_link_at_cursor(cursor)
    
    def check_link_at_cursor(self, cursor):
        """Check if the cursor is over a link and emit a signal if so"""
        text = self.toPlainText()
        pos = cursor.position()
        
        # Check for wiki links [[link]]
        link_start = text.rfind("[[", 0, pos)
        if link_start != -1:
            link_end = text.find("]]", link_start)
            if link_end != -1 and pos <= link_end:
                # We're inside a wiki link
                link_text = text[link_start+2:link_end]
                self.linkClicked.emit(link_text)
                return True
        
        # Check for markdown links [text](link)
        link_text_start = text.rfind("[", 0, pos)
        if link_text_start != -1:
            link_text_end = text.find("]", link_text_start)
            if link_text_end != -1 and pos <= link_text_end:
                # We're inside link text
                link_url_start = text.find("(", link_text_end)
                if link_url_start != -1:
                    link_url_end = text.find(")", link_url_start)
                    if link_url_end != -1:
                        link_url = text[link_url_start+1:link_url_end]
                        self.linkClicked.emit(link_url)
                        return True
                        
        return False
    
    def start_link_completion(self):
        """Start the auto-completion for a wiki link"""
        # Get all items from parent
        if hasattr(self.parent_tab, 'get_link_suggestions'):
            items = self.parent_tab.get_link_suggestions()
            self.set_completion_items(items)
            
            # Show the completer
            rect = self.cursorRect()
            rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 
                         self.completer.popup().verticalScrollBar().sizeHint().width())
            self.completer.complete(rect)
    
    def update_link_completion(self):
        """Update the auto-completion popup based on current text"""
        cursor = self.textCursor()
        text = self.toPlainText()
        pos = cursor.position()
        
        # Find the start of the current link
        link_start = text.rfind("[[", 0, pos)
        if link_start == -1:
            self.completer.popup().hide()
            return
            
        # Get the partial text typed so far
        partial_text = text[link_start+2:pos]
        
        # Update the completer to filter based on the partial text
        self.completer.setCompletionPrefix(partial_text)
        
        # Reposition and show the completer
        if self.completer.completionCount() > 0:
            rect = self.cursorRect()
            rect.setWidth(self.completer.popup().sizeHintForColumn(0) + 
                         self.completer.popup().verticalScrollBar().sizeHint().width())
            self.completer.complete(rect)
        else:
            self.completer.popup().hide()
    
    def insert_completion(self, completion):
        """Insert the selected completion text"""
        cursor = self.textCursor()
        text = self.toPlainText()
        pos = cursor.position()
        
        # Find the start of the current link
        link_start = text.rfind("[[", 0, pos)
        if link_start == -1:
            return
            
        # Replace the partial text with the completion
        cursor.setPosition(link_start + 2)
        cursor.setPosition(pos, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()
        cursor.insertText(completion)
        self.setTextCursor(cursor)
        
        # Add closing brackets if needed
        if "]]" not in text[pos:pos+10]:
            self.insertPlainText("]]")