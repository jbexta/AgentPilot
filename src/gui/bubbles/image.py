from PySide6.QtCore import QUrl
from PySide6.QtGui import Qt, QTextCursor, QTextDocument, QImage

from src.gui.bubbles import get_json_value, MessageBubble


class ImageBubble(MessageBubble):
    def __init__(self, parent, message):
        super().__init__(
            parent=parent,
            message=message,
        )
        self.image = None
        self.zoomed = False

    def setMarkdownText(self, text):
        self.text = text
        filepath = get_json_value(text, 'filepath')
        url = get_json_value(text, 'url')

        if not url and filepath:
            try:
                self.image = QImage(filepath)
                if self.image.isNull():
                    raise Exception("Invalid image")

                self.update_image_display()
            except Exception as e:
                print(f"Error reading image file: {e}")
                self.setPlainText(f"Error loading image: {filepath}")
        else:
            self.setPlainText(f"No valid image path or URL provided")

    def update_image_display(self):
        if self.image:
            self.document().clear()

            w, h = self.image.width(), self.image.height()
            size = max(w, h) if self.zoomed else 250
            scaled_image = self.image.scaled(
                size, size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

            doc = self.document()
            doc.addResource(QTextDocument.ImageResource, QUrl("image"), scaled_image)

            cursor = QTextCursor(doc)
            cursor.insertImage("image")

            self.updateGeometry()
        else:
            self.setPlainText(f"Error loading image: {get_json_value(self.text, 'filepath', 'Unknown')}")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.zoomed = not self.zoomed
            self.update_image_display()
