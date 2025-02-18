import json

# import interpreter
from PySide6.QtCore import QRunnable
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from src.plugins.openinterpreter.src import interpreter
from src.gui.config import ConfigJsonTree, ConfigDBTree, ConfigExtTree, ConfigJoined, ConfigFields, ConfigTabs
from src.gui.widgets import IconButton, find_main_widget
from src.utils import sql


OI_EXECUTOR = interpreter


class EnvironmentManager:
    def __init__(self, parent):
        self.environments = {}  # dict of id: (name, Environment)
        # self.environment_ids = {}  # dict of id: name

    def load(self):
        from src.system.plugins import get_plugin_class
        data = sql.get_results("""
            SELECT
                id,
                name,
                config
            FROM environments""")
        for env_id, name, config in data:
            config = json.loads(config)
            # if name not in self.environments:
            env_class = get_plugin_class('Environment', name, default_class=Environment)
            env_obj = env_class(config=config)
            self.environments[env_id] = (name, env_obj)
            # else:
            #     self.environments[env_id].update(config)

    def get_env_from_name(self, name):  # todo
        for env_id, (env_name, env_obj) in self.environments.items():
            if env_name == name:
                return env_id, env_obj
        return None


class Environment:
    def __init__(self, config):
        self.config = config
        # self.update(config)

    def run_code(self, lang, code, venv_path=None):
        OI_EXECUTOR.venv_path = venv_path
        oi_res = OI_EXECUTOR.computer.run(lang, code)
        output = next(r for r in oi_res if r['format'] == 'output').get('content', '')
        return output

    def update(self, config):
        self.config = config
        self.set_env_vars()

    def set_env_vars(self):
        pass
        # env_vars = self.config.get('env_vars.data', [])  # todo clean nested json
        # # env_vars = json.loads(env_vars)
        # for env_var in env_vars:
        #     ev_name, ev_value = env_var.get('variable', 'Variable name'), env_var.get('value', '')
        #     if ev_name == 'Variable name':
        #         continue
        #     os.environ[ev_name] = ev_value


class EnvironmentSettings(ConfigTabs):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pages = {
            'Venv': self.Page_Venv(parent=self),
            'Env vars': self.Page_Env_Vars(parent=self),
        }

    class Page_Venv(ConfigJoined):
        def __init__(self, parent):
            super().__init__(parent=parent, layout_type='vertical')
            self.widgets = [
                self.Page_Venv_Config(parent=self),
                self.Page_Packages(parent=self),
            ]

        class Page_Venv_Config(ConfigFields):
            def __init__(self, parent):
                super().__init__(parent=parent)
                self.schema = [
                    {
                        'text': 'Venv',
                        'type': 'VenvComboBox',
                        'width': 350,
                        'label_position': None,
                        'default': 'default',
                    },
                ]

            def update_config(self):
                super().update_config()
                self.reload_venv()

            def reload_venv(self):
                self.parent.widgets[1].load()

        class Page_Packages(ConfigJoined):
            def __init__(self, parent):
                super().__init__(parent=parent, layout_type='horizontal')
                self.widgets = [
                    self.Installed_Libraries(parent=self),
                    self.Pypi_Libraries(parent=self),
                ]
                # self.setFixedHeight(450)

            class Installed_Libraries(ConfigExtTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        conf_namespace='installed_packages',
                        schema=[
                            {
                                'text': 'Installed packages',
                                'key': 'name',
                                'type': str,
                                'width': 150,
                            },
                            {
                                'text': '',
                                'key': 'version',
                                'type': str,
                                'width': 25,
                            },
                        ],
                        add_item_options={'title': 'NA', 'prompt': 'NA'},
                        del_item_options={'title': 'Uninstall Package', 'prompt': 'Are you sure you want to uninstall this package?'},
                        # tree_height=450,
                    )

                class LoadRunnable(QRunnable):
                    def __init__(self, parent):
                        super().__init__()
                        self.parent = parent
                        main = find_main_widget(self)
                        self.page_chat = main.page_chat

                    def run(self):
                        import sys
                        from src.system.base import manager
                        try:
                            venv_name = self.parent.parent.config.get('venv', 'default')
                            if venv_name == 'default':
                                packages = sorted(set([module.split('.')[0] for module in sys.modules.keys()]))
                                rows = [[package, ''] for package in packages]
                            else:
                                packages = manager.venvs.venvs[venv_name].list_packages()
                                rows = packages

                            self.parent.fetched_rows_signal.emit(rows)
                        except Exception as e:
                            self.page_chat.main.error_occurred.emit(str(e))

                def add_item(self):
                    pypi_visible = self.parent.widgets[1].isVisible()
                    self.parent.widgets[1].setVisible(not pypi_visible)

            class Pypi_Libraries(ConfigDBTree):
                def __init__(self, parent):
                    super().__init__(
                        parent=parent,
                        table_name='pypi_packages',
                        query="""
                            SELECT
                                name,
                                folder_id
                            FROM pypi_packages
                            LIMIT 1000""",
                        schema=[
                            {
                                'text': 'Browse PyPI',
                                'key': 'name',
                                'type': str,
                                'width': 150,
                            },
                        ],
                        layout_type='horizontal',
                        folder_key='pypi_packages',
                        searchable=True,
                        items_pinnable=False,
                    )
                    self.btn_sync = IconButton(
                        parent=self.tree_buttons,
                        icon_path=':/resources/icon-refresh.png',
                        tooltip='Update package list',
                        size=18,
                    )
                    self.btn_sync.clicked.connect(self.sync_pypi_packages)
                    self.tree_buttons.add_button(self.btn_sync, 'btn_sync')
                    self.hide()

                def on_item_selected(self):
                    pass

                def filter_rows(self):
                    if not self.show_tree_buttons:
                        return

                    search_query = self.tree_buttons.search_box.text().lower()
                    if not self.tree_buttons.search_box.isVisible():
                        search_query = ''

                    if search_query == '':
                        self.query = """
                            SELECT
                                name,
                                folder_id
                            FROM pypi_packages
                            LIMIT 1000
                        """
                    else:
                        self.query = f"""
                            SELECT
                                name,
                                folder_id
                            FROM pypi_packages
                            WHERE name LIKE '%{search_query}%'
                            LIMIT 1000
                        """
                    self.load()

                def sync_pypi_packages(self):
                    import requests
                    import re

                    url = 'https://pypi.org/simple/'
                    response = requests.get(url, stream=True)

                    items = []
                    batch_size = 10000

                    pattern = re.compile(r'<a[^>]*>(.*?)</a>')
                    previous_overlap = ''
                    for chunk in response.iter_content(chunk_size=10240):
                        if chunk:
                            chunk_str = chunk.decode('utf-8')
                            chunk = previous_overlap + chunk_str
                            previous_overlap = chunk_str[-100:]

                            matches = pattern.findall(chunk)
                            for match in matches:
                                item_name = match.strip()
                                if item_name:
                                    items.append(item_name)

                        if len(items) >= batch_size:
                            # generate the query directly without using params
                            query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join(
                                [f"('{item}')" for item in items])
                            sql.execute(query)
                            items = []

                    # Insert any remaining items
                    if items:
                        query = 'INSERT OR IGNORE INTO pypi_packages (name) VALUES ' + ', '.join(
                            [f"('{item}')" for item in items])
                        sql.execute(query)

                    print('Scraping and storing items completed.')
                    self.load()

    class Page_Env_Vars(ConfigJsonTree):
            def __init__(self, parent):
                super().__init__(parent=parent,
                                 add_item_options={'title': 'NA', 'prompt': 'NA'},
                                 del_item_options={'title': 'NA', 'prompt': 'NA'})
                self.parent = parent
                # self.setFixedWidth(250)
                self.conf_namespace = 'env_vars'
                self.schema = [
                    {
                        'text': 'Env Var',
                        'type': str,
                        'width': 120,
                        'default': 'Variable name',
                    },
                    {
                        'text': 'Value',
                        'type': str,
                        'width': 120,
                        'stretch': True,
                        'default': '',
                    },
                ]
