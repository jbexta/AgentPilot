from PySide6.QtCore import QPoint
from PySide6.QtGui import Qt
from PySide6.QtWidgets import QPushButton

from src.gui.widgets.config_fields import ConfigFields
from src.gui.widgets.config_joined import ConfigJoined
from src.gui.widgets.config_json_tree import ConfigJsonTree
from src.gui.widgets.config_tabs import ConfigTabs

from src.utils.helpers import convert_model_json_to_obj


class PopupMember(ConfigJoined):
    def __init__(self, parent, use_namespace=None, member_type='agent'):
        super().__init__(parent=parent, layout_type='vertical')
        self.use_namespace = use_namespace
        self.conf_namespace = use_namespace
        self.member_type = member_type
        self.widgets = [
            self.PopupMemberFields(parent=self),
        ]
        self.widgets[0].conf_namespace = use_namespace
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(350)
        self.build_schema()

    class PopupMemberFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.label_width = 175
            type_default_roles = {  #!memberdiff!#
                'agent': 'assistant',
                'user': 'user',
                'block': 'block',
                'voice': 'audio',
                'image': 'image',
            }
            self.schema = [
                {
                    'text': 'Output role',
                    'type': 'RoleComboBox',
                    'width': 90,
                    'tooltip': 'Set the primary output role for this member',
                    'default': type_default_roles[parent.member_type],
                },
                {
                    'text': 'Output placeholder',
                    'type': str,
                    'tooltip': 'A tag to use this member\'s output from other members system messages',
                    'default': '',
                    # 'row_key': 0,
                },
                {
                    'text': 'Hide bubbles',
                    'type': bool,
                    'tooltip': 'When checked, the responses from this member will not be shown in the chat',
                    'default': False,
                },
            ]

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent
        if parent:
            btm_right = parent.rect().bottomRight()
            btm_right_global = parent.mapToGlobal(btm_right)
            btm_right_global_minus_width = btm_right_global - QPoint(self.width(), 0)
            self.move(btm_right_global_minus_width)


class PopupModel(ConfigJoined):
    def __init__(self, parent):
        super().__init__(parent=parent, layout_type='vertical', add_stretch_to_end=True)
        self.widgets = [
            self.PopupModelFields(parent=self),
            self.PopupModelOutputTabs(parent=self),
        ]
        # self.user_editable = False
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(350)
        self.build_schema()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent
        if parent:
            btm_right = parent.rect().bottomRight()
            btm_right_global = parent.mapToGlobal(btm_right)
            btm_right_global_minus_width = btm_right_global - QPoint(self.width(), 0)
            self.move(btm_right_global_minus_width)

    # class PopupModelXML(ConfigJsonTree):
    #     def __init__(self, parent):
    #         super().__init__(parent=parent,
    #                          add_item_options={'title': 'NA', 'prompt': 'NA'},
    #                          del_item_options={'title': 'NA', 'prompt': 'NA'})
    #         self.conf_namespace = 'xml_roles'
    #         self.schema = [
    #             {
    #                 'text': 'XML Tag',
    #                 'type': str,
    #                 'stretch': True,
    #                 'default': '',
    #             },
    #             {
    #                 'text': 'Map to role',
    #                 'type': 'RoleComboBox',
    #                 'width': 120,
    #                 'default': 'default',
    #             },
    #         ]
    # #         self.PopupModelOutputTabs(parent=self),
    # #     ]

    class PopupModelOutputTabs(ConfigTabs):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.provider = None
            self.pages = {
                'Structure': self.PopupModelStructure(parent=self),
                'Role maps': self.PopupModelXML(parent=self),
                # 'Prompt': self.Tab_System_Prompt(parent=self),
            }

        class PopupModelStructure(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent, layout_type='vertical', add_stretch_to_end=True)
                self.conf_namespace = 'structure'
                self.widgets = [
                    self.PopupModelStructureFields(parent=self),
                    self.PopupModelStructureParams(parent=self),
                ]

            class PopupModelStructureFields(ConfigFields):
                def __init__(self, parent):
                    super().__init__(parent=parent)
                    self.conf_namespace = 'structure'
                    self.schema = [
                        {
                            'text': 'Class name',
                            'type': str,
                            'label_position': None,
                            'placeholder_text': 'Class name',
                            'default': '',
                        },
                        # {
                        #     'text': 'Data',
                        #     'type': str,
                        #     'default': '',
                        #     'num_lines': 2,
                        #     'stretch_x': True,
                        #     'stretch_y': True,
                        #     'highlighter': 'PythonHighlighter',
                        #     'placeholder': 'from pydantic import BaseModel\n\nclass ExampleStructure(BaseModel):\n    name: str\n    age: int\n    active: bool\n    email: Optional[str]',
                        #     'label_position': None,
                        # },
                    ]

            class PopupModelStructureParams(ConfigJsonTree):
                def __init__(self, parent):
                    super().__init__(parent=parent,
                                     add_item_options={'title': 'NA', 'prompt': 'NA'},
                                     del_item_options={'title': 'NA', 'prompt': 'NA'})
                    self.conf_namespace = 'structure'
                    self.schema = [
                        {
                            'text': 'Attribute',
                            'type': str,
                            'stretch': True,
                            'default': 'Attr name',
                        },
                        {
                            'text': 'Type',
                            'type': ('str', 'int', 'bool', 'float'),
                            'width': 120,
                            'default': 'str',
                        },
                        {
                            'text': 'Req',
                            'type': bool,
                            'width': 50,
                            'default': True,
                        },
                    ]

        class PopupModelXML(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_options={'title': 'NA', 'prompt': 'NA'},
                                 del_item_options={'title': 'NA', 'prompt': 'NA'})
                self.conf_namespace = 'xml_roles'
                self.schema = [
                    {
                        'text': 'XML Tag',
                        'type': str,
                        'stretch': True,
                        'default': 'Tag name',
                    },
                    {
                        'text': 'Map to role',
                        'type': 'RoleComboBox',
                        'width': 120,
                        'default': 'User',
                    },
                ]

            # def after_init(self):
            #     self.layout.addStretch(1)  # todo fix

    class PopupModelFields(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.parent = parent
            self.schema = [
                {
                    'text': 'Temperature',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 0.6,
                    'row_key': 'A',
                },
                {
                    'text': 'Presence penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'default': 0.0,
                    'row_key': 'A',
                },
                {
                    'text': 'Top P',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 0.0,
                    'maximum': 1.0,
                    'step': 0.05,
                    'default': 1.0,
                    'row_key': 'B',
                },
                {
                    'text': 'Frequency penalty',
                    'type': float,
                    'has_toggle': True,
                    'label_width': 140,
                    'minimum': -2.0,
                    'maximum': 2.0,
                    'step': 0.2,
                    'default': 0.0,
                    'row_key': 'B',
                },
                {
                    'text': 'Max tokens',
                    'type': int,
                    'has_toggle': True,
                    'label_width': 125,
                    'minimum': 1,
                    'maximum': 999999,
                    'step': 1,
                    'default': 100,
                },
            ]

        def after_init(self):
            self.btn_reset_to_default = QPushButton('Reset to defaults')
            self.btn_reset_to_default.clicked.connect(self.reset_to_default)
            self.layout.addWidget(self.btn_reset_to_default)

        def reset_to_default(self):
            # from src.utils.helpers import convert_model_json_to_obj
            from src.system import manager

            combo = self.parent.parent
            model_key = combo.currentData()
            model_obj = convert_model_json_to_obj(model_key)

            default = manager.providers.get_model_parameters(model_obj, incl_api_data=False)
            self.load_config(default)

            combo.currentIndexChanged.emit(combo.currentIndex())
            self.load()


class PopupPageParams(ConfigFields):
    def __init__(self, parent, schema=None):
        super().__init__(parent=parent)
        self.label_width = 140
        self.schema = schema or []

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(300)

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent
        if parent:
            btm_right = parent.rect().bottomRight()
            btm_right_global = parent.mapToGlobal(btm_right)
            btm_right_global_minus_width = btm_right_global - QPoint(self.width(), 0)
            self.move(btm_right_global_minus_width)