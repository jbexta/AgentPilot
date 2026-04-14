from gui.widgets.config_fields import ConfigFields


class PromptSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Model',
                'key': 'prompt_model',
                'type': 'model',
                'popup_params': True,
                'model_kind': 'CHAT',
                'label_position': None,
                'default': 'default',
            },
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
                'label_position': None,
            },
        ]