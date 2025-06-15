
from PySide6.QtGui import Qt
from src.gui.widgets.config_fields import ConfigFields
from src.utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ContactSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.member_id = None
        self.field_alignment = Qt.AlignHCenter
        self.schema = [
            {
                'text': 'Avatar',
                'key': 'avatar_path',
                'type': 'image',
                'label_position': None,
                'diameter': 30,
                'row_key': 0,
                'default': '',
            },
            {
                'text': 'Name',
                'type': str,
                'stretch_x': True,
                'text_size': 15,
                # 'text_alignment': Qt.AlignCenter,
                'label_position': None,
                'transparent': True,
                'row_key': 0,
                'default': 'Contact',
            },
            {
                'text': 'Phone number',
                'type': str,
                'default': '',
            },
            {
                'text': 'Email',
                'type': str,
                'width': 250,
                'default': '',
            },
        ]
