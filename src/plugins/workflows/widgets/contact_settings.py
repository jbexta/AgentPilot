from PySide6.QtGui import Qt
from gui.widgets.config_fields import ConfigFields
from utils.helpers import set_module_type


@set_module_type(module_type='Widgets')
class ContactSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.parent = parent
        self.member_id = None
        self.field_alignment = Qt.AlignHCenter
        self.schema = [
            {
                'text': 'Type',
                'type': ('Individual', 'Company'),
                'default': 'Individual',
                'row_key': 1,
            },
            {
                'text': 'Company',
                'type': str,
                'width': 200,
                'default': '',
                'row_key': 1,
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