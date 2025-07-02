from typing_extensions import override

from gui.util import CHBoxLayout, clear_layout, IconButton
from gui.widgets.config_widget import ConfigWidget
from utils.helpers import convert_to_safe_case


# class IconButtonCollection(QWidget):
#     def __init__(self, parent):
#         super().__init__()
#         self.parent = parent
#         self.layout = CHBoxLayout(self)
#         self.layout.setContentsMargins(0, 2, 0, 2)
#         self.icon_size = 22
#         self.setFixedHeight(self.icon_size + 6)

class IconButtonCollection(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.schema = kwargs.get('schema', [])

        self.layout = CHBoxLayout(self)
        self.layout.setContentsMargins(0, 2, 0, 2)
        self.icon_size = 22
        self.setFixedHeight(self.icon_size + 6)

        # self.conf_namespace = kwargs.get('conf_namespace', None)
        # self.field_alignment = kwargs.get('field_alignment', Qt.AlignLeft)
        # self.layout = CVBoxLayout(self)
        # self.label_width = kwargs.get('label_width', None)
        # self.label_text_alignment = kwargs.get('label_text_alignment', Qt.AlignLeft)
        # self.margin_left = kwargs.get('margin_left', 0)
        self.right_to_left = kwargs.get('right_to_left', False)
        self.add_stretch_to_end = kwargs.get('add_stretch_to_end', True)
        # self.schema = kwargs.get('schema', [])
        # self.adding_field = None

    @override
    def build_schema(self):
        """Build the widgets from the schema list"""
        clear_layout(self.layout)
        schema = self.schema
        if not schema:
            # self.adding_field = self.AddingField(self)
            # if not find_attribute(self, 'user_editing'):
            #     self.adding_field.hide()
            # self.layout.addWidget(self.adding_field)
            # self.layout.addStretch(1)
            #
            # if hasattr(self, 'after_init'):  # todo clean
            #     self.after_init()
            return  # todo add adding_button

        if self.add_stretch_to_end and self.right_to_left:
            self.layout.addStretch(1)

        for param_dict in schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            tooltip = param_dict.get('tooltip', None)
            icon_path = param_dict.get('icon_path', None)
            target = param_dict.get('target', None)

            stretch = param_dict.get('stretch', False)
            if stretch:
                self.layout.addStretch(stretch if isinstance(stretch, int) else 1)
                continue

            button = IconButton(
                parent=self,
                icon_path=icon_path,
                tooltip=tooltip,
                text=param_dict.get('text', None),
                size=self.icon_size,
                target=target,
            )
            setattr(self, key, button)
            self.layout.addWidget(button)
            # self.connect_signal(widget)

            # if hasattr(button, 'build_schema'):
            #     button.build_schema()

        # if getattr(self, 'user_editable', True):
        #     self.layout.addSpacing(7)
        #     self.adding_field = self.AddingField(self)
        #     if not find_attribute(self, 'user_editing'):
        #         self.adding_field.hide()
        #     self.layout.addWidget(self.adding_field)

        if self.add_stretch_to_end and not self.right_to_left:
            self.layout.addStretch(1)

        if hasattr(self, 'after_init'):
            self.after_init()
