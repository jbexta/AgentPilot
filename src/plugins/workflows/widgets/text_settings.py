from gui.widgets.config_fields import ConfigFields


class TextSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Data',
                'type': str,
                'default': '',
                'num_lines': 2,
                'stretch_x': True,
                'stretch_y': True,
                'wrap_text': True,
                'highlighter': 'xml',
                'fold_mode': 'xml',
                'format_blocks': True,
                'label_position': None,
            },
        ]