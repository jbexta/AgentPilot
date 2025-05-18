import json
from abc import abstractmethod

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import *
from PySide6.QtGui import QCursor

from src.gui.util import save_table_config
from src.utils.helpers import convert_to_safe_case

from src.utils import sql

class ConfigWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.config = {}
        self.schema = []
        self.default_schema = []  # todo clean
        self.conf_namespace = None
        self.edit_bar = None
        self.user_editable = getattr(parent, 'user_editable', True)

        self.edit_bar_timer = QTimer(self)
        self.edit_bar_timer.setSingleShot(True)
        self.edit_bar_timer.timeout.connect(self.edit_bar_delayed_show)

    @abstractmethod
    def build_schema(self):
        schema = getattr(self, 'schema', None)
        tree = getattr(self, 'tree', None)
        if schema and tree:
            tree.build_columns_from_schema(schema)

        config_widget = getattr(self, 'config_widget', None)
        if config_widget:
            config_widget.build_schema()

    @abstractmethod
    def load(self):
        pass

    def load_config(self, json_config=None):
        """Loads the config dict from the root config widget"""
        from src.gui.widgets.config_db_tree import ConfigDBTree
        from src.gui.widgets.config_pages import ConfigPages
        from src.gui.widgets.config_tabs import ConfigTabs
        from src.gui.widgets.config_joined import ConfigJoined

        if hasattr(self, 'data_source'):
            # Load from data source
            table_name = self.data_source['table_name']
            item_id = self.data_source.get('item_id', None)
            if item_id is None:
                data_column = self.data_source.get('data_column', 'config')
                lookup_column = self.data_source.get('lookup_column', 'name')
                lookup_value = self.data_source.get('lookup_value', None)
                if not lookup_value:
                    raise ValueError("Either item_id or lookup_value is required for data_source")

                item_config = json.loads(sql.get_scalar(f"SELECT `{data_column}` FROM `{table_name}` WHERE `{lookup_column}` = ? LIMIT 1",
                                         (lookup_value,)))
                if item_config is None:
                    raise ValueError(f"Config not found for ConfigWidget")

                self.config = item_config

        elif json_config is not None:
            if json_config == '':
                json_config = {}
            if isinstance(json_config, str):
                json_config = json.loads(json_config)
            self.config = json_config if json_config else {}

        elif getattr(self, 'load_from_parent', True):
            parent_config = getattr(self.parent, 'config', {})

            if self.conf_namespace is None and not isinstance(self, ConfigDBTree):
                self.config = parent_config
            else:
                self.config = {k: v for k, v in parent_config.items() if k.startswith(f'{self.conf_namespace}.')}

        if hasattr(self, 'member_config_widget'):
            self.member_config_widget.load(temp_only_config=True)
        if getattr(self, 'config_widget', None):
            self.config_widget.load_config()
        if isinstance(self, ConfigJoined):
            widgets = getattr(self, 'widgets', [])
            for widget in widgets:
                if hasattr(widget, 'load_config'):
                    widget.load_config()
        elif isinstance(self, ConfigTabs) or isinstance(self, ConfigPages):
            pages = getattr(self, 'pages', {})
            for pn, page in pages.items():
                if not getattr(page, 'propagate', True) or not hasattr(page, 'load_config'):
                    continue

                page.load_config()

    def get_config(self):
        from src.gui.widgets.config_pages import ConfigPages
        from src.gui.widgets.config_tabs import ConfigTabs
        from src.gui.widgets.config_joined import ConfigJoined
        config = {}

        if self.__class__.__name__ == 'Page_System_Settings':
            pass
        if hasattr(self, 'member_type'):
            config['_TYPE'] = self.member_type

        if isinstance(self, ConfigTabs) or isinstance(self, ConfigPages):
            pages = getattr(self, 'pages', {})
            for page_name, page in pages.items():
                if hasattr(self.content, 'tabBar'):
                    is_vis = self.content.tabBar().isTabVisible(self.content.indexOf(page))
                else:
                    page_button = self.settings_sidebar.page_buttons.get(page_name, None)
                    is_vis = page_button.isVisible() if page_button else False

                if (not getattr(page, 'propagate', True) or
                    not hasattr(page, 'get_config') or
                    # not getattr(page, 'conf_namespace', None) or
                    not is_vis
                ):
                    continue

                page_config = page.get_config()
                config.update(page_config)

        elif isinstance(self, ConfigJoined):
            widgets = getattr(self, 'widgets', [])
            for widget in widgets:
                if not getattr(widget, 'propagate', True) or not hasattr(widget, 'get_config'):
                    continue
                cc = widget.get_config()
                config.update(cc)
                pass

        else:
            config.update(self.config)

        if getattr(self, 'config_widget', None):
            config.update(self.config_widget.get_config())
            pass

        if hasattr(self, 'tree'):
            for item in self.schema:
                is_config_field = item.get('is_config_field', False)
                if not is_config_field:
                    continue

                key = convert_to_safe_case(item.get('key', item['text']))
                indx = self.schema.index(item)
                val = self.tree.get_column_value(indx)
                if item['type'] == bool:
                    val = bool(val)
                config[key] = val

        return config

    def update_config(self):
        """Bubble update config dict to the root config widget"""
        if hasattr(self, 'save_config'):
            self.save_config()
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

    def save_config(self):
        """Saves the config to database when modified"""
        data_source = getattr(self, 'data_source', None)
        if not data_source:
            return

        table_name = data_source['table_name']
        data_column = data_source.get('data_column', 'config')
        item_id = data_source.get('item_id', None)
        config = self.get_config()
        json_config = json.dumps(config)

        if item_id is None:
            lookup_column = data_source.get('lookup_column', 'name')
            lookup_value = data_source['lookup_value']
            item_id = sql.get_scalar(f"SELECT id FROM `{table_name}` WHERE `{lookup_column}` = ? LIMIT 1", (lookup_value,))
            if not item_id:
                raise ValueError(f"Either item_id or lookup_value is required for data_source")

        # todo - support kinds
        save_table_config(
            ref_widget=self,
            table_name=table_name,
            item_id=item_id,
            key_field=data_column,
            value=json_config
        )
        # sql.execute(f"UPDATE `{table_name}` SET `{data_column}` = ? WHERE id = ?", (json_config, item_id))
        # if hasattr(self, 'on_edited'):
        #     self.on_edited()
        # # self.main.system.config.load()
        # # system_config = self.main.system.config.dict
        self.load_config(config)  # system_config)

    def update_breadcrumbs(self, nodes=None):
        nodes = nodes or []

        if hasattr(self, 'get_breadcrumbs'):
            nodes.append(self.get_breadcrumbs())

        if hasattr(self, 'breadcrumb_text'):
            nodes.append(self.breadcrumb_text)

        if hasattr(self, 'breadcrumb_widget'):
            self.breadcrumb_widget.set_nodes(nodes)

        if hasattr(self.parent, 'update_breadcrumbs'):
            self.parent.update_breadcrumbs(nodes)

    def try_add_breadcrumb_widget(self, root_title=None):
        """Adds a breadcrumb widget to the top of the layout"""
        from src.gui.util import find_breadcrumb_widget, BreadcrumbWidget
        breadcrumb_widget = find_breadcrumb_widget(self)
        # if not has attr (not method) layout
        layout = getattr(self, 'layout', None)
        if not layout or callable(layout):  # no layout is set
            from src.gui.util import CVBoxLayout
            self.layout = CVBoxLayout(self)

        if not breadcrumb_widget:  #  and hasattr(self, 'layout'):
            self.breadcrumb_widget = BreadcrumbWidget(parent=self, root_title=root_title)
            self.layout.insertWidget(0, self.breadcrumb_widget)

    def maybe_rebuild_schema(self, schema_overrides, item_id):  # todo rethink
        if item_id is None:
            return
        if not schema_overrides:
            return

        item_schema = schema_overrides.get(item_id, self.default_schema)
        if item_schema != self.schema:
            self.set_schema(item_schema, set_default=False)

    def set_schema(self, schema, set_default=True):
        self.schema = schema
        if set_default:
            self.default_schema = schema
        self.build_schema()

    def enterEvent(self, event):
        from src.gui.util import find_attribute
        if find_attribute(self, 'user_editing', False):
            self.toggle_edit_bar(True)

    def leaveEvent(self, event):
        widget_under_mouse = QApplication.widgetAt(QCursor.pos())
        if self.edit_bar and (widget_under_mouse is self.edit_bar or
                              self.isAncestorOf(widget_under_mouse)):
            return

        self.toggle_edit_bar(False)

    def toggle_widget_edit(self, state):
        if getattr(self, 'user_editable', False) or getattr(self, 'module_id', None):
            setattr(self, 'user_editing', state)
            self.set_edit_widget_visibility_recursive(state)

    def set_edit_widget_visibility_recursive(self, state):
        if hasattr(self, 'set_widget_edit_mode'):
            self.set_widget_edit_mode(state)

        if hasattr(self, 'widgets'):
            for widget in self.widgets:
                if hasattr(widget, 'set_widget_edit_mode'):
                    widget.set_widget_edit_mode(state)
        elif hasattr(self, 'pages'):
            for pn, page in self.pages.items():
                if hasattr(page, 'set_widget_edit_mode'):
                    page.set_widget_edit_mode(state)
        elif getattr(self, 'config_widget', None):
            self.config_widget.set_widget_edit_mode(state)

    def set_widget_edit_mode(self, state):
        if hasattr(self, 'settings_sidebar'):
            if getattr(self.settings_sidebar, 'new_page_btn', None):
                self.settings_sidebar.new_page_btn.setVisible(state)
        if getattr(self, 'new_page_btn', None):
            self.new_page_btn.setVisible(state)
        if getattr(self, 'adding_field', None):
            self.adding_field.setVisible(state)
        from src.gui.temp import OptionsButton
        for btn in self.findChildren(OptionsButton):
            btn.setVisible(state)

    def toggle_edit_bar(self, state):
        self.edit_bar_timer.stop()
        if state:
            from src.gui.util import find_attribute
            user_editing = find_attribute(self, 'user_editing', False)
            user_editable = find_attribute(self, 'user_editable', False)
            if not user_editing or not user_editable:
                return
            if not self.edit_bar:
                from src.gui.util import EditBar
                self.edit_bar = EditBar(self)
            self.edit_bar_timer.start(500)
        else:
            if self.edit_bar:
                self.edit_bar.hide()

    def edit_bar_delayed_show(self):
        if self.edit_bar:
            self.edit_bar.show()
        self.hide_parent_edit_bars()

    def hide_parent_edit_bars(self):
        parent = self.parent
        while parent:
            edit_bar = getattr(parent, 'edit_bar', None)
            if edit_bar:
                edit_bar.hide()
            parent = getattr(parent, 'parent', None)

    def show_first_parent_edit_bar(self):
        from src.gui.util import find_attribute
        if not find_attribute(self, 'user_editing', False):
            return
        parent = self.parent
        while parent:
            edit_bar = getattr(parent, 'edit_bar', None)
            if edit_bar:
                edit_bar.show()
                break
            parent = getattr(parent, 'parent', None)