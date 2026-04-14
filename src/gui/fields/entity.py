from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QSizePolicy, QWidget, QPushButton, QHBoxLayout

from gui.util import IconButton, LibraryDialog
from utils.helpers import set_module_type


@set_module_type('Fields')
class EntityField(QWidget):
    """
    A field widget that lets users pick an entity from a LibraryDialog.

    Parameters
    ----------
    parent : QWidget
        The parent widget.
    entity_table : str, optional
        Limit to a specific entity table ('blocks', 'entities', 'tools').
        If None, show all tabs.
    """

    option_schema = [
        {
            'text': 'Entity table',
            'key': 'f_entity_table',
            'type': str,
            'default': '',
            'tooltip': 'Limit to a specific entity table '
                       '(blocks, entities, tools)',
        },
    ]

    def __init__(self, parent, **kwargs):
        super().__init__(parent)
        self.parent = parent
        self.entity_table = kwargs.get('entity_table', None)
        self._value = ''

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(4)

        self.label = QPushButton('Select entity...', self)
        self.label.setFlat(True)
        self.label.setStyleSheet(
            'QPushButton { background: transparent; border: none;'
            ' text-align: left; padding: 0; }'
        )
        self.label.setCursor(Qt.PointingHandCursor)
        self.label.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Preferred,
        )
        self.label.clicked.connect(self.browse_entity)

        self.browse_button = IconButton(
            self,
            icon_path=':/resources/icon-blocks.png',
        )
        self.browse_button.setMaximumWidth(60)
        self.browse_button.clicked.connect(self.browse_entity)

        self.layout.addWidget(self.browse_button)
        self.layout.addWidget(self.label)

        width = kwargs.get('width', None)
        if width:
            self.setFixedWidth(width)

    def get_value(self):
        """Return the stored value as ``name:table:uuid``."""
        return self._value

    def set_value(self, value):
        """Set the value and update the display label."""
        self._value = str(value) if value else ''
        name = self._value.rsplit(':', 2)[0] if self._value else ''
        self.label.setText(name if name else 'Select entity...')

    def browse_entity(self):
        """Open the LibraryDialog and let the user pick an entity."""
        kind_map = {
            'entities': 'conversation',
            'blocks': 'blocks',
            'tools': 'tool',
        }
        kind = kind_map.get(self.entity_table, None)

        dlg = LibraryDialog(
            parent=self,
            callback=self._on_entity_selected,
            kind=kind,
        )
        dlg.open()

    def _on_entity_selected(self, item, link=False):
        """Handle entity selection from the library dialog."""
        name = item.text(0)
        table = item.text(3)
        uuid = item.text(1)
        self.set_value(f'{name}:{table}:{uuid}')
        self.parent.update_config()