from PySide6.QtWidgets import QVBoxLayout, QPushButton, QHBoxLayout

from src.gui.config import ConfigTabs, ConfigFields, ConfigJsonTree, ConfigJoined, ConfigWidget
from src.system.environments import Environment, EnvironmentSettings
from src.utils.helpers import convert_model_json_to_obj
import docker

CLIENT = docker.from_env()

imgs = CLIENT.images.list()
pass
# class Docker

class DockerEnvironment(Environment):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.image_name = 'ubuntu'

    # region Filesystem
    def start(self):
        try:
            self.container = CLIENT.containers.run(self.image_name, detach=True)
            print(f"Container {self.container.name} started")
        except Exception as e:
            print(f"Error starting container: {e}")


class DockerSettings(EnvironmentSettings):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = {'Docker': self.DockerPage(parent=self), **self.pages}

    class DockerPage(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.widgets = [
                self.DockerControls(parent=self),
                self.DockerFields(parent=self),
            ]

        class DockerControls(ConfigWidget):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.btn_start = QPushButton('Start')
                self.btn_stop = QPushButton('Stop')
                self.btn_restart = QPushButton('Restart')
                self.btn_build = QPushButton('Build')
                self.layout = QHBoxLayout(self)
                self.layout.addWidget(self.btn_start)
                self.layout.addWidget(self.btn_stop)
                self.layout.addWidget(self.btn_restart)
                self.layout.addWidget(self.btn_build)
                # self.setFixedHeight(30)

            # def after_init(self):
            #     self.btn_start.clicked.connect(self.parent.parent.start)
            #     self.btn_stop.clicked.connect(self.parent.parent.stop)
            #     self.btn_restart.clicked.connect(self.parent.parent.restart)
            #     self.btn_build.clicked.connect(self.parent.parent.build)

        class DockerFields(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.parent = parent
                self.conf_namespace = 'docker'
                self.schema = [
                    {
                        'text': 'Dockerfile',
                        'type': str,
                        'default': '',
                        'num_lines': 2,
                        'stretch_x': True,
                        'stretch_y': True,
                        'highlighter': 'DockerfileHighlighter',
                        'fold_mode': None,
                        'label_position': None,
                    },
                ]

# class DockerSettings(ConfigTabs):
#     def __init__(self, *args, **kwargs):
#         super().__init__(*args, **kwargs)
#         self.pages = {
#             # 'Messages': self.Page_Chat_Messages(parent=self),
#             'Image': self.Page_Env_Vars(parent=self),
#         }
#
#     class Page_Env_Vars(ConfigJsonTree):
#         def __init__(self, parent):
#             super().__init__(parent=parent,
#                              add_item_options={'title': 'NA', 'prompt': 'NA'},
#                              del_item_options={'title': 'NA', 'prompt': 'NA'})
#             self.parent = parent
#             self.conf_namespace = 'env_vars'
#             self.schema = [
#                 {
#                     'text': 'Variable',
#                     'type': str,
#                     'width': 120,
#                     'default': 'Variable name',
#                 },
#                 {
#                     'text': 'Value',
#                     'type': str,
#                     'stretch': True,
#                     'default': '',
#                 },
#             ]
