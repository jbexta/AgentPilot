import ast
import inspect
import json
import os
import uuid
from abc import abstractmethod
from functools import partial
from sqlite3 import IntegrityError
from textwrap import dedent
from typing import Dict, Any

from PySide6.QtCore import Signal, QFileInfo, Slot, QRunnable, QSize, QPoint, QTimer
from PySide6.QtWidgets import *
from PySide6.QtGui import QFont, Qt, QIcon, QPixmap, QCursor, QStandardItem, QStandardItemModel, QColor, QFontDatabase

from src.utils.helpers import block_signals, block_pin_mode, display_message_box, \
    merge_config_into_workflow_config, convert_to_safe_case, convert_model_json_to_obj, convert_json_to_obj, \
    try_parse_json, display_message, get_metadata
from src.gui.widgets import BaseComboBox, CircularImageLabel, \
    ColorPickerWidget, FontComboBox, BaseTreeWidget, IconButton, colorize_pixmap, LanguageComboBox, RoleComboBox, \
    clear_layout, TreeDialog, ToggleIconButton, HelpIcon, PluginComboBox, EnvironmentComboBox, find_main_widget, \
    CTextEdit, PythonHighlighter, APIComboBox, VenvComboBox, ModuleComboBox, XMLHighlighter, \
    InputSourceComboBox, InputTargetComboBox, find_attribute, \
    find_page_editor_widget  # XML used dynamically

from src.utils import sql
from src.utils.sql import define_table

import astor

class_param_schemas = {
    'ConfigTabs': [],
    'ConfigPages': [
        {
            'text': 'Right to Left',
            'key': 'w_right_to_left',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Bottom to Top',
            'key': 'w_bottom_to_top',
            'type': bool,
            'default': False,
        }
    ],
    'ConfigDBTree': [
        {
            'text': 'Table name',
            'key': 'w_table_name',
            'type': str,
            'stretch_x': True,
            'default': '',
        },
        {
            'text': 'Query',
            'key': 'w_query',
            'type': str,
            'label_position': 'top',
            'stretch_x': True,
            'num_lines': 3,
            'default': '',
        },
        {
            'text': 'Folder key',
            'key': 'w_folder_key',
            'type': str,
            'default': '',
        },
        {
            'text': 'Layout type',
            'key': 'w_layout_type',
            'type': ('vertical', 'horizontal',),
            'default': 'vertical',
        },
        {
            'text': 'Readonly',
            'key': 'w_readonly',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Searchable',
            'key': 'w_searchable',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Versionable',
            'key': 'w_versionable',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Default item icon',
            'key': 'w_default_item_icon',
            'type': str,
            'default': '',
        },
        {
            'text': 'Items pinnable',
            'key': 'w_items_pinnable',
            'type': bool,
            'default': True,
        },
        {
            'text': 'Tree header hidden',
            'key': 'w_tree_header_hidden',
            'type': bool,
            'default': False,
        },
        {
            'text': 'Tree header resizable',
            'key': 'w_tree_header_resizable',
            'type': bool,
            'default': True,
        },
        {
            'text': 'Show tree buttons',
            'key': 'w_show_tree_buttons',
            'type': bool,
            'default': True,
        },
        # {
        #     'text': 'Add item options',
        #     'type': list,
        #     'default': [],
        # },
        # {
        #     'text': 'Delete item options',
        #     'type': list,
        #     'default': [],
        # },
    ],
    'ConfigFields': [
        {
            'text': 'Field alignment',
            'key': 'w_field_alignment',
            'type': ('left', 'center', 'right',),
            'default': 'left',
        },
        {
            'text': 'Label width',
            'key': 'w_label_width',
            'type': int,
            'has_toggle': True,
            'default': 150,
        },
        {
            'text': 'Margin left',
            'key': 'w_margin_left',
            'type': int,
            'default': 0,
        },
        {
            'text': 'Add stretch to end',
            'key': 'w_add_stretch_to_end',
            'type': bool,
            'default': True,
        },
    ]
}

def get_class_path(module, class_name):
    if not module:
        return None

    def find_class_name_recursive(obj, path):
        """Recursively find the class name and return the path to it."""
        if not inspect.isclass(obj):
            return None

        current_path = path + [obj.__name__]

        if obj.__name__ == class_name:
            obj_superclass = obj.__bases__[0] if obj.__bases__ else None
            return current_path, obj_superclass

        # Check for nested classes
        for name, member in inspect.getmembers(obj):
            if inspect.isclass(member) and member.__module__ == obj.__module__:
                result = find_class_name_recursive(member, current_path)
                if result:
                    return result
        return None

    # Search for the class in the loaded module
    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and obj.__module__ == module.__name__ and obj.__name__.lower().startswith('page_'):
            return find_class_name_recursive(obj, [])

    return None


def modify_class_base(module_id, class_path, new_superclass):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, new_superclass):
            self.target_path = target_path
            self.current_path = []
            self.new_superclass = new_superclass

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                new_bases = [ast.Name(id=self.new_superclass, ctx=ast.Load())]
                node.bases = new_bases

                if self.new_superclass == 'ConfigPages' or self.new_superclass == 'ConfigTabs':
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            ensure_attribute(item, 'pages', {})
                            # comment_attributes(item, ['schema'])
                            break
                elif self.new_superclass == 'ConfigDBTree' or self.new_superclass == 'ConfigFields':
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                            ensure_attribute(item, 'schema', [])  # , reset_value=True)
                            # comment_attributes(item, ['pages'])
                            break

            self.generic_visit(node)
            self.current_path.pop()
            return node

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, new_superclass)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)  # astor.to_source(modified_tree)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


def ensure_attribute(node, attr_name, attr_value, reset_value=False):
    rem_node = None
    for item in node.body:
        if isinstance(item, ast.Assign) and isinstance(item.targets[0], ast.Attribute) and item.targets[0].attr == attr_name:
            if not reset_value:
                return
            # node.body.remove(item)
            rem_node = item

    if rem_node:
        node.body.remove(rem_node)

    if isinstance(attr_value, dict):
        new_attr = ast.Assign(
            targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=attr_name, ctx=ast.Store())],
            value=ast.Dict(keys=[ast.Str(s=k) for k in attr_value.keys()],
                           values=[ast.Str(s=str(v)) for v in attr_value.values()])
        )
    else:
        new_attr = ast.Assign(
            targets=[ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=attr_name, ctx=ast.Store())],
            value=ast.Str(s=attr_value)
        )

    node.body.append(new_attr)


# def comment_attributes(node, attributes):
#     # import astor
#     new_body = []
#     for stmt in node.body:
#         if (isinstance(stmt, ast.Assign) and
#             isinstance(stmt.targets[0], ast.Attribute) and
#             stmt.targets[0].attr in attributes):
#             # Convert the assignment node back to source code.
#             # This may span multiple lines if the assignment is complex.
#             try:
#                 original_code = astor.to_source(stmt)
#             except Exception:
#                 original_code = ""  # Fallback in case conversion fails.
#             # Prepend each line with a comment symbol.
#             commented_lines = []
#             for line in original_code.splitlines():
#                 commented_lines.append("# " + line)
#             commented_code = "\n".join(commented_lines)
#             # Replace the assignment with an expression node containing a string literal.
#             # The CustomSourceGenerator can then handle outputting this literal as a comment.
#             comment_node = ast.Expr(value=ast.Str(s=commented_code))
#             new_body.append(comment_node)
#         else:
#             new_body.append(stmt)
#     node.body = new_body


def modify_class_add_page(module_id, class_path, new_page_name):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, new_page_name):
            self.target_path = target_path
            self.current_path = []
            self.new_page_name = new_page_name
            self.safe_page_name = convert_to_safe_case(new_page_name)

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                new_page = ast.parse(dedent(f"""
                    class Page_{self.safe_page_name}(ConfigWidget):
                        def __init__(self, parent):
                            super().__init__(parent)
                """))
                node.body.append(new_page.body[0])

                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        self.modify_init(item)
                        break

            self.generic_visit(node)
            self.current_path.pop()
            return node

        def modify_init(self, init_node):
            for stmt in init_node.body:
                if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'pages'):
                    continue
                if not isinstance(stmt.value, ast.Dict):
                    continue

                # Add new page to existing dictionary  # args is  `parent=self`
                new_key = ast.Str(s=self.new_page_name)
                new_value = ast.Call(
                    func=ast.Attribute(value=ast.Name(id='self', ctx=ast.Load()), attr=f'Page_{self.safe_page_name}',
                                       ctx=ast.Load()),
                    args=[ast.Name(id='self', ctx=ast.Load())],
                    keywords=[]
                )
                stmt.value.keys.append(new_key)
                stmt.value.values.append(new_value)
                return

            # If we didn't find and modify an existing self.pages, create a new one
            new_pages = ast.parse(f"self.pages = {{{self.new_page_name!r}: self.{self.safe_page_name}(self)}}").body[0]

            init_node.body.append(new_pages)

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, new_page_name)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


def modify_class_delete_page(module_id, class_path, page_name):
    class ClassModifier(ast.NodeTransformer):
        def __init__(self, target_path, page_name):
            self.target_path = target_path
            self.current_path = []
            self.page_name = page_name

        def visit_ClassDef(self, node):
            self.current_path.append(node.name)
            if self.current_path == self.target_path:
                class_name = None
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == '__init__':
                        class_name = self.modify_init(item)
                        break
                if class_name:
                    for item in node.body:
                        if isinstance(item, ast.ClassDef) and item.name == class_name:
                            node.body.remove(item)
                            break

            self.generic_visit(node)
            self.current_path.pop()
            return node

        def modify_init(self, init_node):
            for stmt in init_node.body:
                if not (isinstance(stmt, ast.Assign) and isinstance(stmt.targets[0], ast.Attribute) and stmt.targets[0].attr == 'pages'):
                    continue
                if not isinstance(stmt.value, ast.Dict):
                    continue

                class_name = None
                for i, key in enumerate(stmt.value.keys):
                    if key.s == self.page_name:
                        class_name = stmt.value.values[i].func.attr
                        del stmt.value.keys[i]
                        del stmt.value.values[i]
                        # break
                        return class_name
                # if class_name:
                #     parent_class_node =
            return None

    from src.system.base import manager
    module_config = manager.get_manager('modules').modules.get(module_id, {})
    source = module_config.get('data', None)
    if not source:
        return None

    tree = ast.parse(source)
    modifier = ClassModifier(class_path, page_name)
    modified_tree = modifier.visit(tree)
    modified_source = astor.to_source(modified_tree, source_generator_class=CustomSourceGenerator)

    # Update the module data with the modified source
    module_config['data'] = modified_source
    manager.get_manager('modules').modules[module_id] = module_config

    return modified_source


class CustomSourceGenerator(astor.code_gen.SourceGenerator):
    def visit_Dict(self, node):
        if not node.keys:
            self.write('{}')
            return

        self.write('{')
        self.indentation += 1
        for key, value in zip(node.keys, node.values):
            self.fill()
            self.visit(key)
            self.write(': ')
            self.visit(value)
            self.write(',')
        self.indentation -= 1
        self.fill()
        self.write('}')

    def fill(self, text=""):
        self.write('\n' + self.indent_with * self.indentation + text)


class EditBar(QWidget):
    def __init__(self, editing_widget):
        super().__init__(parent=None)
        from src.system.base import manager
        self.editing_widget = editing_widget
        self.editing_module_id = find_attribute(editing_widget, 'module_id')
        self.class_name = editing_widget.__class__.__name__
        self.loaded_module = manager.get_manager('modules').loaded_modules.get(self.editing_module_id)
        class_tup = get_class_path(self.loaded_module, self.class_name)
        self.class_map = None
        self.current_superclass = None
        if class_tup:
            self.class_map, self.current_superclass = class_tup
            print(self.current_superclass)

        self.page_editor = find_page_editor_widget(editing_widget)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setProperty('class', 'edit-bar')

        self.layout = QHBoxLayout(self)

        self.type_combo = BaseComboBox()
        self.type_combo.addItems(['ConfigWidget', 'ConfigTabs', 'ConfigPages', 'ConfigJoined', 'ConfigDBTree', 'ConfigFields'])
        self.type_combo.setFixedWidth(150)
        # set current superclass
        if self.current_superclass:
            self.type_combo.setCurrentText(self.current_superclass.__name__)
        self.type_combo.currentIndexChanged.connect(self.on_type_combo_changed)

        # self.btn_add_widget_left = IconButton(
        #     parent=self,
        #     icon_path=':/resources/icon-new.png',
        #     tooltip='Add Widget Left',
        #     size=20,
        # )

        self.layout.addWidget(self.type_combo)

        self.options_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-settings-solid.png',
            tooltip='Options',
            size=20,
        )
        self.options_btn.setProperty('class', 'send')
        self.options_btn.clicked.connect(self.show_options)
        self.layout.addWidget(self.options_btn)
        self.config_widget = PopupPageParams(self)
        self.rebuild_config_widget()

    def show_options(self):
        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()

    def rebuild_config_widget(self):
        new_superclass = self.type_combo.currentText()
        self.config_widget.schema = class_param_schemas.get(new_superclass, [])
        self.config_widget.build_schema()

    def on_type_combo_changed(self, index):
        if not self.page_editor:
            return
        if self.editing_module_id != self.page_editor.config_widget.item_id:
            return
        new_superclass = self.type_combo.currentText()
        new_class = modify_class_base(self.editing_module_id, self.class_map, new_superclass)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, self.editing_module_id))

            from src.system.base import manager
            manager.load_manager('modules')
            self.page_editor.load()
            self.page_editor.config_widget.config_widget.widgets[0].reimport()
            self.rebuild_config_widget()

    def leaveEvent(self, event):
        type_combo_is_expanded = self.type_combo.view().isVisible()
        config_widget_shown = self.config_widget.isVisible()
        if not (type_combo_is_expanded or config_widget_shown):
            self.hide()

    def sizeHint(self):
        # size of contents
        width = self.layout.sizeHint().width()
        return QSize(width, 25)

    def showEvent(self, event):
        # move to top left of editing widget
        try:  # !! #
            if self.editing_widget and not self.editing_widget.isVisible():
                return
            self.move(self.editing_widget.mapToGlobal(QPoint(0, -45)))
        except RuntimeError:
            pass


class ConfigWidget(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.config: Dict[str, Any] = {}
        self.schema = []
        self.default_schema = []  # todo clean
        self.conf_namespace = None
        self.edit_bar = None
        self.user_editable = True

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
        if json_config is not None:
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

        if isinstance(self, ConfigDBItem):
            pass
        return config

    def update_config(self):
        """Bubble update config dict to the root config widget"""
        if hasattr(self, 'save_config'):
            self.save_config()
        elif hasattr(self.parent, 'update_config'):
            self.parent.update_config()

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
        from src.gui.widgets import find_breadcrumb_widget, BreadcrumbWidget
        breadcrumb_widget = find_breadcrumb_widget(self)
        # if not has attr (not method) layout
        layout = getattr(self, 'layout', None)
        if not layout or callable(layout):  # no layout is set
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
        if find_attribute(self, 'user_editing', False):
            self.toggle_edit_bar(True)

    def leaveEvent(self, event):
        widget_under_mouse = QApplication.widgetAt(QCursor.pos())
        if self.edit_bar and (widget_under_mouse is self.edit_bar or
                              self.edit_bar.isAncestorOf(widget_under_mouse)):
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

    def toggle_edit_bar(self, state):
        self.edit_bar_timer.stop()
        if state:
            if not find_attribute(self, 'user_editing', False):
                return
            if not self.edit_bar:
                self.edit_bar = EditBar(self)
            self.edit_bar_timer.start(500)
        else:
            if self.edit_bar:
                self.edit_bar.hide()
            self.show_first_parent_edit_bar()

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
        if not find_attribute(self, 'user_editing', False):
            return
        parent = self.parent
        while parent:
            edit_bar = getattr(parent, 'edit_bar', None)
            if edit_bar:
                edit_bar.show()  # !! #
                break
            parent = getattr(parent, 'parent', None)

class ConfigJoined(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        layout_type = kwargs.get('layout_type', 'vertical')
        self.propagate = kwargs.get('propagate', True)
        self.layout = CVBoxLayout(self) if layout_type == 'vertical' else CHBoxLayout(self)
        self.widgets = kwargs.get('widgets', [])
        self.add_stretch_to_end = kwargs.get('add_stretch_to_end', False)
        # self.user_editable = True

    def build_schema(self):
        for widget in self.widgets:
            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            self.layout.addWidget(widget)

        if self.add_stretch_to_end:
            self.layout.addStretch(1)
        if hasattr(self, 'after_init'):
            self.after_init()

    def load(self):
        for widget in self.widgets:
            if hasattr(widget, 'load'):
                widget.load()


class ConfigFields(ConfigWidget):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent=parent)

        self.conf_namespace = kwargs.get('conf_namespace', None)
        self.field_alignment = kwargs.get('field_alignment', Qt.AlignLeft)
        self.layout = CVBoxLayout(self)
        self.label_width = kwargs.get('label_width', None)
        self.label_text_alignment = kwargs.get('label_text_alignment', Qt.AlignLeft)
        self.margin_left = kwargs.get('margin_left', 0)
        self.add_stretch_to_end = kwargs.get('add_stretch_to_end', True)
        self.schema = kwargs.get('schema', [])
        # self.user_editable = True
        self.adding_field = None

    def build_schema(self):
        """Build the widgets from the schema list"""
        clear_layout(self.layout)
        schema = self.schema
        if not schema:
            self.adding_field = self.AddingField(self)
            if not find_attribute(self, 'user_editing'):
                self.adding_field.hide()
            self.layout.addWidget(self.adding_field)
            self.layout.addStretch(1)

            if hasattr(self, 'after_init'):  # todo clean
                self.after_init()
            return

        self.layout.setContentsMargins(self.margin_left, 0, 0, 5)
        row_layout = None
        last_row_key = None
        has_stretch_y = False

        for param_dict in schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            row_key = param_dict.get('row_key', None)
            label_position = param_dict.get('label_position', 'left')
            label_width = param_dict.get('label_width', None) or self.label_width
            has_toggle = param_dict.get('has_toggle', False)
            tooltip = param_dict.get('tooltip', None)
            visible = param_dict.get('visible', True)
            stretch_y = param_dict.get('stretch_y', False)

            if row_key is not None and row_layout is None:
                row_layout = CHBoxLayout()
            elif row_key is not None and row_layout is not None and row_key != last_row_key:
                self.layout.addLayout(row_layout)
                row_layout = CHBoxLayout()
            elif row_key is None and row_layout is not None:
                self.layout.addLayout(row_layout)
                row_layout = None

            last_row_key = row_key

            current_value = self.config.get(f'{key}', None)
            if current_value is not None:
                param_dict['default'] = current_value

            widget = self.create_widget(**param_dict)
            setattr(self, key, widget)
            self.connect_signal(widget)

            if hasattr(widget, 'build_schema'):
                widget.build_schema()

            param_layout = CHBoxLayout() if label_position == 'left' else CVBoxLayout()
            param_layout.setContentsMargins(2, 8, 2, 0)
            param_layout.setAlignment(self.field_alignment)
            if label_position is not None:
                label_layout = CHBoxLayout()
                label_layout.setAlignment(self.label_text_alignment)
                param_label = QLabel(param_dict['text'])
                param_label.setAlignment(self.label_text_alignment)
                if not visible:
                    param_label.setVisible(False)
                if label_width:
                    param_label.setFixedWidth(label_width)

                label_layout.addWidget(param_label)

                label_minus_width = 0
                if tooltip:
                    info_label = HelpIcon(parent=self, tooltip=tooltip)
                    info_label.setAlignment(self.label_text_alignment)
                    label_minus_width += 22
                    label_layout.addWidget(info_label)

                if has_toggle:
                    toggle = QCheckBox()
                    toggle.setFixedWidth(20)
                    setattr(self, f'{key}_tgl', toggle)
                    self.connect_signal(toggle)
                    toggle.stateChanged.connect(partial(self.toggle_widget, toggle, key))
                    self.toggle_widget(toggle, key, None)
                    label_minus_width += 20
                    label_layout.addWidget(toggle)

                if has_toggle or tooltip:
                    label_layout.addStretch(1)

                if label_width:
                    param_label.setFixedWidth(label_width - label_minus_width)

                param_layout.addLayout(label_layout)

            param_layout.addWidget(widget)
            if isinstance(param_layout, CHBoxLayout):
                param_layout.addStretch(1)

            if stretch_y:
                has_stretch_y = True

            if row_layout:
                row_layout.addLayout(param_layout)
            else:
                self.layout.addLayout(param_layout)

            if not visible:
                widget.setVisible(False)

        if row_layout:
            self.layout.addLayout(row_layout)

        self.adding_field = self.AddingField(self)
        if not find_attribute(self, 'user_editing'):
            self.adding_field.hide()
        self.layout.addWidget(self.adding_field)

        if self.add_stretch_to_end and not has_stretch_y:
            self.layout.addStretch(1)

        if hasattr(self, 'after_init'):
            # if self.__class__.__name__ == 'Page_Display_Themes':
            #     print('after_init')
            self.after_init()

    class AddingField(QWidget):
        def __init__(self, parent):
            super().__init__(parent)
            self.layout = CHBoxLayout(self)
            self.tb_name = QLineEdit()
            self.tb_name.setPlaceholderText('Name')
            self.cb_type = BaseComboBox()
            self.cb_type.addItems([
                'Text',
                'Integer',
                'Float',
                'Boolean',
                'ComboBox',
                'ModelComboBox',
                'EnvironmentComboBox',
                'RoleComboBox',
                'ModuleComboBox',
                'LanguageComboBox',
                'ColorPickerWidget',
            ])
            self.btn_add = QPushButton('Add')
            self.layout.addWidget(self.tb_name)
            self.layout.addWidget(self.cb_type)
            self.layout.addWidget(self.btn_add)

    def load(self):
        """Loads the widget values from the config dict"""
        with block_signals(self):
            for param_dict in self.schema:
                # if self.__class__.__name__ == 'Module_Config_Fields':  # and key == 'load_on_startup':
                #     print('load prompt_model: ', config_value)
                key = convert_to_safe_case(param_dict.get('key', param_dict['text']))

                widget = getattr(self, key)
                config_key = f"{self.conf_namespace}.{key}" if self.conf_namespace else key

                config_value = self.config.get(config_key, None)
                has_config_value = config_value is not None


                toggle = getattr(self, f'{key}_tgl', None)
                if toggle:
                    toggle.setChecked(has_config_value)
                    widget.setVisible(has_config_value)

                if has_config_value:
                    is_encrypted = param_dict.get('encrypt', False)
                    if is_encrypted:
                        # todo decrypt
                        pass
                    self.set_widget_value(widget, config_value)
                else:
                    self.set_widget_value(widget, param_dict.get('default', ''))

    def update_config(self):
        config = {}
        for param_dict in self.schema:
            param_key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            config_key = f"{self.conf_namespace}.{param_key}" if self.conf_namespace else param_key

            widget_toggle = getattr(self, f'{param_key}_tgl', None)
            if widget_toggle:
                if not widget_toggle.isChecked():
                    config.pop(config_key, None)
                    continue

            widget = getattr(self, param_key)
            widget_value = get_widget_value(widget)
            if getattr(widget, 'use_namespace', None):
                config.update(widget_value)
            else:
                config[config_key] = widget_value

            if self.__class__.__name__ == 'BlockMemberSettings' and param_key == 'prompt_model':
                print('update prompt_model: ', json.dumps(config))

        self.config = config
        super().update_config()

    def create_widget(self, **kwargs):
        param_type = kwargs['type']
        default_value = kwargs.get('default', '')
        param_width = kwargs.get('width', None)
        num_lines = kwargs.get('num_lines', 1)
        text_size = kwargs.get('text_size', None)
        text_align = kwargs.get('text_alignment', Qt.AlignLeft)  # only works for single line
        highlighter = kwargs.get('highlighter', None)
        highlighter_field = kwargs.get('highlighter_field', None)
        monospaced = kwargs.get('monospaced', False)
        # expandable = kwargs.get('expandable', False)
        transparent = kwargs.get('transparent', False)
        minimum = kwargs.get('minimum', 0)
        maximum = kwargs.get('maximum', 1)
        step = kwargs.get('step', 1)
        stretch_x = kwargs.get('stretch_x', False)
        stretch_y = kwargs.get('stretch_y', False)
        placeholder_text = kwargs.get('placeholder_text', None)
        # wrap_text = kwargs.get('wrap_text', False)

        set_width = param_width or 50
        if param_type == bool:
            widget = QCheckBox()
        elif param_type == int:
            widget = QSpinBox()
            widget.setMinimum(minimum)
            widget.setMaximum(maximum)
            widget.setSingleStep(step)
        elif param_type == float:
            widget = QDoubleSpinBox()
            widget.setMinimum(minimum)
            widget.setMaximum(maximum)
            widget.setSingleStep(step)
        elif param_type == str:
            gen_block_folder_name = kwargs.get('gen_block_folder_name', None)
            placeholder = kwargs.get('placeholder', None)
            fold_mode = kwargs.get('fold_mode', 'xml')
            widget = QLineEdit() if num_lines == 1 else CTextEdit(gen_block_folder_name=gen_block_folder_name, fold_mode=fold_mode)

            transparency = 'background-color: transparent;' if transparent else ''
            widget.setStyleSheet(f"border-radius: 6px;" + transparency)

            if isinstance(widget, CTextEdit):
                widget.setTabStopDistance(widget.fontMetrics().horizontalAdvance(' ') * 4)
            elif isinstance(widget, QLineEdit):
                widget.setAlignment(text_align)

            if placeholder:
                widget.setPlaceholderText(placeholder)

            font = widget.font()
            if monospaced:
                font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
            if text_size:
                font.setPointSize(text_size)
            widget.setFont(font)

            if highlighter:
                try:
                    # highlighter is a string name of the highlighter class, imported in this file
                    # reassign highlighter to the highlighter class
                    highlighter = globals()[highlighter]
                    widget.highlighter = highlighter(widget.document(), self.parent)
                    if isinstance(highlighter, PythonHighlighter):
                        widget.setLineWrapMode(QPlainTextEdit.NoWrap)
                except Exception as e:
                    pass
            elif highlighter_field:
                widget.highlighter_field = highlighter_field

            if placeholder_text:
                widget.setPlaceholderText(placeholder_text)

            if not stretch_y:
                font_metrics = widget.fontMetrics()
                height = (font_metrics.lineSpacing() + 2) * num_lines + widget.contentsMargins().top() + widget.contentsMargins().bottom()
                widget.setFixedHeight(height)

            set_width = param_width or 150
        elif isinstance(param_type, tuple):
            widget = BaseComboBox()
            widget.addItems(param_type)
            set_width = param_width or 150
        elif param_type == 'CircularImageLabel':
            diameter = kwargs.get('diameter', 50)
            widget = CircularImageLabel(diameter=diameter)
            set_width = widget.width()
        elif param_type == 'PluginComboBox':
            plugin_type = kwargs.get('plugin_type', 'Agent')
            centered = kwargs.get('centered', False)
            allow_none = kwargs.get('allow_none', True)
            none_text = None if not allow_none else kwargs.get('none_text', 'Choose Plugin')
            widget = PluginComboBox(plugin_type=plugin_type, centered=centered, none_text=none_text)
            set_width = param_width or 150
        elif param_type == 'ModelComboBox':
            widget = ModelComboBox(parent=self)
            set_width = param_width or 150
        elif param_type == 'MemberPopupButton':
            use_namespace = kwargs.get('use_namespace', None)
            member_type = kwargs.get('member_type', 'agent')
            widget = MemberPopupButton(parent=self, use_namespace=use_namespace, member_type=member_type)
            set_width = param_width or 24
        elif param_type == 'EnvironmentComboBox':
            widget = EnvironmentComboBox()
            set_width = param_width or 150
        elif param_type == 'VenvComboBox':
            widget = VenvComboBox(parent=self)
            set_width = param_width or 150
        elif param_type == 'FontComboBox':
            widget = FontComboBox()
            set_width = param_width or 150
        elif param_type == 'RoleComboBox':
            widget = RoleComboBox()
            set_width = param_width or 150
        elif param_type == 'ModuleComboBox':
            widget = ModuleComboBox()
            set_width = param_width or 150
        elif param_type == 'LanguageComboBox':
            widget = LanguageComboBox()
            set_width = param_width or 150
        elif param_type == 'ColorPickerWidget':
            widget = ColorPickerWidget()
            set_width = param_width or 25
        else:
            raise ValueError(f'Unknown param type: {param_type}')

        self.set_widget_value(widget, default_value)

        if stretch_x or stretch_y:
            x_pol = QSizePolicy.Expanding if stretch_x else QSizePolicy.Fixed
            y_pol = QSizePolicy.Expanding if stretch_y else QSizePolicy.Fixed
            widget.setSizePolicy(x_pol, y_pol)

        elif set_width:
            widget.setFixedWidth(set_width)

        return widget

    def connect_signal(self, widget):
        if isinstance(widget, CircularImageLabel):
            widget.avatarChanged.connect(self.update_config)
        elif isinstance(widget, ColorPickerWidget):
            widget.colorChanged.connect(self.update_config)
        elif isinstance(widget, ModelComboBox):
            widget.currentIndexChanged.connect(self.update_config)
        elif isinstance(widget, MemberPopupButton):
            pass  # do nothing
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(self.update_config)
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(self.update_config)
        elif isinstance(widget, QComboBox):
            widget.currentIndexChanged.connect(self.update_config)
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(self.update_config)
        elif isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(self.update_config)
        elif isinstance(widget, CTextEdit):
            widget.textChanged.connect(self.update_config)
        else:
            raise Exception(f'Widget not implemented: {type(widget)}')

    def set_widget_value(self, widget, value):
        try:
            if isinstance(widget, CircularImageLabel):
                widget.setImagePath(value)
            elif isinstance(widget, ColorPickerWidget):
                widget.setColor(value)
            elif isinstance(widget, PluginComboBox):
                widget.set_key(value)
            elif isinstance(widget, ModelComboBox):
                from src.system.base import manager
                if value == '':
                    value = manager.config.dict.get('system.default_chat_model', 'mistral/mistral-large-latest')
                value = convert_model_json_to_obj(value)

                value_copy = value.copy()
                model_params = value_copy.pop('model_params', {})

                widget.config_widget.load_config(model_params)
                widget.config_widget.load()

                value_copy = json.dumps(value_copy)
                widget.set_key(value_copy)
                widget.refresh_options_button_visibility()
            elif isinstance(widget, MemberPopupButton):
                value = convert_json_to_obj(value)
                use_namespace = getattr(widget, 'use_namespace', None)
                if use_namespace:
                    use_config = {k: v for k, v in self.config.items() if k.startswith(f'{widget.use_namespace}.')}
                    widget.config_widget.load_config(use_config)
                else:
                    widget.config_widget.load_config(value)
                widget.config_widget.load()
            elif isinstance(widget, EnvironmentComboBox):
                widget.set_key(value)
            elif isinstance(widget, VenvComboBox):
                widget.set_key(value)
            elif isinstance(widget, RoleComboBox):
                widget.set_key(value)
            elif isinstance(widget, ModuleComboBox):
                widget.set_key(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QComboBox):
                widget.setCurrentText(str(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, CTextEdit):
                widget.setPlainText(value)
            else:
                raise Exception(f'Widget not implemented: {type(widget)}')
        except Exception as e:
            print('Error setting widget value: ', e)

    def toggle_widget(self, toggle, key, _):
        widget = getattr(self, key)
        widget.setVisible(toggle.isChecked())

    def clear_fields(self):
        for param_dict in self.schema:
            key = convert_to_safe_case(param_dict.get('key', param_dict['text']))
            widget = getattr(self, key)
            if isinstance(widget, QLineEdit):
                widget.clear()
            elif isinstance(widget, QCheckBox):
                widget.setChecked(False)
            elif isinstance(widget, QSpinBox):
                widget.setValue(0)
            elif isinstance(widget, QDoubleSpinBox):
                widget.setValue(0.0)
            elif isinstance(widget, QComboBox):
                widget.setCurrentIndex(0)
            elif isinstance(widget, CTextEdit):
                widget.clear()


class IconButtonCollection(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent
        self.layout = CHBoxLayout(self)
        self.layout.setContentsMargins(0, 2, 0, 2)
        self.icon_size = 19
        self.setFixedHeight(self.icon_size + 6)


class TreeButtons(IconButtonCollection):
    def __init__(self, parent):
        super().__init__(parent=parent)

        self.btn_add = IconButton(
            parent=self,
            icon_path=':/resources/icon-new.png',
            tooltip='Add',
            size=self.icon_size,
        )
        self.btn_del = IconButton(
            parent=self,
            icon_path=':/resources/icon-minus.png',
            tooltip='Delete',
            size=self.icon_size,
        )
        self.layout.addWidget(self.btn_add)
        self.layout.addWidget(self.btn_del)

        if getattr(parent, 'folder_key', False):
            self.btn_new_folder = IconButton(
                parent=self,
                icon_path=':/resources/icon-new-folder.png',
                tooltip='New Folder',
                size=self.icon_size,
            )
            self.layout.addWidget(self.btn_new_folder)
            runnables = ['blocks', 'agents', 'tools']
            if parent.folder_key in runnables:
                self.btn_run = IconButton(
                    parent=self,
                    icon_path=':/resources/icon-run.png',
                    tooltip='Run',
                    size=self.icon_size,
                )
                self.layout.addWidget(self.btn_run)

        if getattr(parent, 'folders_groupable', False):
            self.btn_group_folders = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-group.png',
                icon_path_checked=':/resources/icon-group-solid.png',
                tooltip='Group Folders',
                icon_size_percent=0.6,
                size=self.icon_size,
            )
            self.layout.addWidget(self.btn_group_folders)
            self.btn_group_folders.clicked.connect(self.parent.load)
            self.btn_group_folders.setChecked(True)

        if getattr(parent, 'versionable', False):
            self.btn_versions = IconButton(
                parent=self,
                icon_path=':/resources/icon-history.png',
                tooltip='Versions',
                size=self.icon_size,
            )
            self.btn_versions.clicked.connect(self.parent.show_history_context_menu)
            self.layout.addWidget(self.btn_versions)

        if getattr(parent, 'filterable', False):
            self.btn_filter = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-filter.png',
                icon_path_checked=':/resources/icon-filter-filled.png',
                tooltip='Filter',
                size=self.icon_size,
            )
            self.btn_filter.toggled.connect(self.toggle_filter)
            self.layout.addWidget(self.btn_filter)

        if getattr(parent, 'searchable', False):
            self.btn_search = ToggleIconButton(
                parent=self,
                icon_path=':/resources/icon-search.png',
                icon_path_checked=':/resources/icon-search-filled.png',
                tooltip='Search',
                size=self.icon_size,
            )
            self.layout.addWidget(self.btn_search)

            self.search_box = QLineEdit()
            self.search_box.setContentsMargins(1, 0, 1, 0)
            self.search_box.setPlaceholderText('Search...')

            self.search_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.btn_search.toggled.connect(self.toggle_search)

            if hasattr(parent, 'filter_rows'):
                self.search_box.textChanged.connect(parent.filter_rows)

            self.layout.addWidget(self.search_box)
            self.search_box.hide()

        self.layout.addStretch(1)

    def add_button(self, icon_button, icon_att_name):
        setattr(self, icon_att_name, icon_button)
        self.layout.takeAt(self.layout.count() - 1)  # remove last stretch
        self.layout.addWidget(getattr(self, icon_att_name))
        self.layout.addStretch(1)

    def toggle_search(self):
        is_checked = self.btn_search.isChecked()
        self.search_box.setVisible(is_checked)
        self.parent.filter_rows()
        if is_checked:
            self.search_box.setFocus()

    def toggle_filter(self):
        is_checked = self.btn_filter.isChecked()
        if hasattr(self.parent, 'filter_widget'):
            self.parent.filter_widget.setVisible(is_checked)
        self.parent.updateGeometry()


class FilterWidget(QWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.parent = parent
        self.layout = CHBoxLayout(self)

        self.button_group = QButtonGroup(self)
        self.button_group.buttonClicked.connect(self.on_button_clicked)

        self.kind_buttons = {kind: self.FilterButton(text=kind)
                             for kind in kwargs.get('kind_list', [])}

        for i, (key, btn) in enumerate(self.kind_buttons.items()):
            self.button_group.addButton(btn, i)
            self.layout.addWidget(btn)

        default_kind = kwargs.get('kind', None)
        if default_kind:
            default_btn = self.kind_buttons.get(default_kind)
            if default_btn:
                default_btn.setChecked(True)

        self.layout.addStretch(1)

    def on_button_clicked(self, button):
        self.parent.load()

    def get_kind(self):
        for kind, btn in self.kind_buttons.items():
            if btn.isChecked():
                return kind
        return self.parent.kind

    class FilterButton(QPushButton):
        def __init__(self, text):
            super().__init__()
            self.setCheckable(True)
            self.setText(text.title())
            # set padding
            self.setStyleSheet('padding: 5px;')


class ConfigDBItem(ConfigWidget):
    """
    A wrapper widget for displaying a single item config from the db.
    Must contain a config widget that is the ConfigWidget representing the item.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.table_name = kwargs.get('table_name')
        self.item_id = kwargs.get('item_id', None)
        self.item_name = kwargs.get('item_name', None)
        self.key_field = kwargs.get('key_field', 'name')
        self.value_field = kwargs.get('value_field', 'config')
        self.config_widget = kwargs.get('config_widget')
        self.propagate = False
        self.load_from_parent = False

        self.layout = CVBoxLayout(self)

        self.config_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.config_widget)

    def get_item_id(self, temp_recurse_stop=False):
        if self.item_id:
            return self.item_id
        if not self.item_name:
            raise Exception("Item name is missing")

        item_id = sql.get_scalar(f"""
            SELECT id
            FROM `{self.table_name}`
            WHERE `{self.key_field}` = ?
        """, (self.item_name,))
        if not item_id:
            if temp_recurse_stop:  # todo
                raise Exception("Item not found and unable to add it")

            sql.execute(f"""
                INSERT INTO `{self.table_name}` (`{self.key_field}`) VALUES (?)
            """, (self.item_name,))
            item_id = self.get_item_id(temp_recurse_stop=True)
            if not item_id:
                raise ValueError('Unable to get item id for ConfigDBItem')

        return int(item_id)

    def load(self):
        item_id = self.get_item_id()
        json_config = json.loads(sql.get_scalar(f"""
            SELECT
                `{self.value_field}`
            FROM `{self.table_name}`
            WHERE id = ?
        """, (item_id,)))
        if ((self.table_name == 'entities' or self.table_name == 'blocks' or self.table_name == 'tools')
                and json_config.get('_TYPE', 'agent') != 'workflow'):
            json_config = merge_config_into_workflow_config(json_config)
        self.config_widget.load_config(json_config)
        self.config_widget.load()

    def save_config(self):
        """
        Saves the config to the database using the item ID.
        """
        item_id = self.get_item_id()
        config = self.get_config()

        save_table_config(
            ref_widget=self,
            table_name=self.table_name,
            item_id=item_id,
            value=config,
        )
        self.config_widget.load_config(config)


class ConfigTree(ConfigWidget):
    """Base class for a tree widget"""
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.conf_namespace = kwargs.get('conf_namespace', None)
        self.schema = kwargs.get('schema', [])
        layout_type = kwargs.get('layout_type', 'vertical')
        tree_height = kwargs.get('tree_height', None)
        self.readonly = kwargs.get('readonly', False)
        self.filterable = kwargs.get('filterable', False)
        self.searchable = kwargs.get('searchable', False)
        self.versionable = kwargs.get('versionable', False)
        self.dynamic_load = kwargs.get('dynamic_load', False)
        self.folders_groupable = kwargs.get('folders_groupable', False)
        # self.async_load = kwargs.get('async_load', False)
        self.default_item_icon = kwargs.get('default_item_icon', None)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        tree_header_resizable = kwargs.get('tree_header_resizable', True)
        self.config_widget = kwargs.get('config_widget', None)
        self.folder_key = kwargs.get('folder_key', None)

        self.show_tree_buttons = kwargs.get('show_tree_buttons', True)

        self.add_item_options = kwargs.get('add_item_options', None)
        self.del_item_options = kwargs.get('del_item_options', None)

        self.layout = CVBoxLayout(self)

        splitter_orientation = Qt.Horizontal if layout_type == 'horizontal' else Qt.Vertical
        self.splitter = QSplitter(splitter_orientation)
        self.splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.setChildrenCollapsible(False)

        self.tree_container = QWidget()
        self.tree_layout = CVBoxLayout(self.tree_container)
        if self.filterable:
            self.filter_widget = FilterWidget(parent=self, **kwargs)
            self.filter_widget.hide()
            self.tree_layout.addWidget(self.filter_widget)

        if self.show_tree_buttons:
            self.tree_buttons = TreeButtons(parent=self)
            # self.tree_buttons.btn_add.clicked.connect(self.add_item)
            # self.tree_buttons.btn_del.clicked.connect(self.delete_item)
            self.tree_layout.addWidget(self.tree_buttons)

        self.tree = BaseTreeWidget(parent=self)
        self.tree.setHeaderHidden(tree_header_hidden)
        self.tree.setSortingEnabled(False)
        self.tree.itemChanged.connect(self.on_cell_edited)
        self.tree.itemSelectionChanged.connect(self.on_item_selected)
        self.tree.itemExpanded.connect(self.on_folder_toggled)
        self.tree.itemCollapsed.connect(self.on_folder_toggled)

        if not tree_header_resizable:
            self.tree.header().setSectionResizeMode(QHeaderView.Fixed)
        # self.tree.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        if tree_height:
            self.tree.setFixedHeight(tree_height)
        self.tree.move(-15, 0)

        # self.fetched_rows_signal.connect(self.load_rows, Qt.QueuedConnection)

        if self.dynamic_load:
            self.tree.verticalScrollBar().valueChanged.connect(self.check_infinite_load)
            self.load_count = 0

        self.tree_layout.addWidget(self.tree)
        self.splitter.addWidget(self.tree_container)

        if self.config_widget:
            # self.config_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.splitter.addWidget(self.config_widget)

        self.layout.addWidget(self.splitter)
        # self.layout.addStretch(1)

    @abstractmethod
    def load(self):
        # if self.async_load:
        #     rows = self.config.get(f'{self.conf_namespace}.data', [])
        #     self.insert_rows(rows)
        #     main = find_main_widget(self)
        #     load_runnable = self.LoadRunnable(self)
        #     main.threadpool.start(load_runnable)
        # else:
        pass

    # @Slot(list)
    # def load_rows(self, rows):
    #     # self.config[f'{self.conf_namespace}.data'] = rows
    #     self.insert_rows(rows)
    #     # single shot
    #     QTimer.singleShot(10, self.update_config)

    # def insert_rows(self, rows):
    #     with block_signals(self.tree):
    #         self.tree.clear()
    #         for row_fields in rows:
    #             item = QTreeWidgetItem(self.tree, row_fields)

    @abstractmethod
    def check_infinite_load(self, item):
        pass

    @abstractmethod
    def on_cell_edited(self, item):
        pass

    @abstractmethod
    def on_item_selected(self):
        pass

    @abstractmethod
    def on_folder_toggled(self, item):
        pass

    @abstractmethod
    def add_item(self, row_dict=None, icon=None):
        pass

    @abstractmethod
    def delete_item(self):
        pass

    @abstractmethod
    def rename_item(self):
        pass


class ConfigDBTree(ConfigTree):
    """
    A widget that displays a tree of items from the db, with buttons to add and delete items.
    Can contain a config widget shown either to the right of the tree or below it,
    representing the config for each item in the tree.
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)
        self.default_schema = self.schema.copy()
        self.kind = kwargs.get('kind', None)
        self.query = kwargs.get('query', None)
        self.query_params = kwargs.get('query_params', ())
        self.table_name = kwargs.get('table_name', None)
        self.propagate = False
        # self.db_config_field = kwargs.get('db_config_field', 'config')
        # self.config_buttons = kwargs.get('config_buttons', None)
        # self.user_editable = True

        self.init_select = kwargs.get('init_select', True)
        self.items_pinnable = kwargs.get('items_pinnable', True)

        self.schema_overrides = {}
        # define_table(self.table_name)
        self.current_version = None  # todo, should be here?

        if self.show_tree_buttons:
            # self.tree_buttons = TreeButtons(parent=self)
            self.tree_buttons.btn_add.clicked.connect(self.add_item)
            self.tree_buttons.btn_del.clicked.connect(self.delete_item)
            if hasattr(self.tree_buttons, 'btn_new_folder'):
                self.tree_buttons.btn_new_folder.clicked.connect(self.add_folder_btn_clicked)
            if hasattr(self.tree_buttons, 'btn_run'):
                self.tree_buttons.btn_run.clicked.connect(self.run_btn_clicked)
            if not self.add_item_options:
                self.tree_buttons.btn_add.hide()
            if not self.del_item_options:
                self.tree_buttons.btn_del.hide()

        if hasattr(self, 'after_init'):
            self.after_init()

    def load(self, select_id=None, silent_select_id=None, append=False):
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        if not self.query:
            return

        if hasattr(self, 'load_count'):
            if not append:
                self.load_count = 0
            limit = 100
            offset = self.load_count * limit
            self.query_params = (limit, offset,)

        group_folders = False
        if self.show_tree_buttons:
            if hasattr(self.tree_buttons, 'btn_group_folders'):
                group_folders = self.tree_buttons.btn_group_folders.isChecked()

        query = self.query if not self.filterable else self.query.replace('{{kind}}', self.filter_widget.get_kind())
        data = sql.get_results(query=query, params=self.query_params)
        self.tree.load(
            data=data,
            append=append,
            select_id=select_id,
            silent_select_id=silent_select_id,
            folder_key=self.folder_key,
            init_select=self.init_select,
            readonly=self.readonly,
            schema=self.schema,
            group_folders=group_folders,
            default_item_icon=self.default_item_icon,
        )
        if len(data) == 0:
            return

        if hasattr(self, 'load_count'):
            self.load_count += 1

    def reload_current_row(self):
        data = sql.get_results(query=self.query, params=self.query_params)
        self.tree.reload_selected_item(data=data, schema=self.schema)

    def update_config(self):
        """Overrides to stop propagation to the parent."""
        self.save_config()

    def save_config(self):
        """
        Saves the config to the database using the tree selected ID.
        """
        item_id = self.get_selected_item_id()
        config = self.get_config()

        save_table_config(
            ref_widget=self,
            table_name=self.table_name,
            item_id=item_id,
            value=config,
        )
        self.config_widget.load_config(config)

    def on_item_selected(self):
        self.current_version = None

        item_id = self.get_selected_item_id()
        if hasattr(self.tree_buttons, 'btn_run'):
            self.tree_buttons.btn_run.setVisible(item_id is not None)
        if hasattr(self.tree_buttons, 'btn_versions'):
            self.tree_buttons.btn_versions.setVisible(item_id is not None)

        if isinstance(item_id, str):
            item_id = None  # todo clean
        if not item_id:
            self.toggle_config_widget(False)
            return

        self.toggle_config_widget(True)

        if self.config_widget:
            self.config_widget.maybe_rebuild_schema(self.schema_overrides, item_id)

            json_config = json.loads(sql.get_scalar(f"""
                SELECT
                    `config`
                FROM `{self.table_name}`
                WHERE id = ?
            """, (item_id,)))

            try:
                json_metadata = json.loads(sql.get_scalar(f"""
                    SELECT
                        `metadata`
                    FROM `{self.table_name}`
                    WHERE id = ?
                """, (item_id,)))
                self.current_version = json_metadata.get('current_version', None)
            except Exception as e:
                pass

            if ((self.table_name == 'entities' or self.table_name == 'blocks' or self.table_name == 'tools')
                    and json_config.get('_TYPE', 'agent') != 'workflow'):
                json_config = merge_config_into_workflow_config(json_config)
            self.config_widget.load_config(json_config)
            self.config_widget.load()

    def on_folder_toggled(self, item):
        folder_id = int(item.text(1))  # self.get_selected_folder_id()
        if not folder_id:
            return

        expanded = 1 if item.isExpanded() else 0
        sql.execute("""
            UPDATE folders
            SET expanded = ?
            WHERE id = ?
        """, (expanded, folder_id,))

    def toggle_config_widget(self, enabled):
        widget = self.config_widget
        if widget:
            widget.setEnabled(enabled)
            widget.setVisible(enabled)

    def filter_rows(self):
        if not self.show_tree_buttons:
            return

        search_query = self.tree_buttons.search_box.text().lower()
        if not self.tree_buttons.search_box.isVisible():
            search_query = ''

        def filter_item(item, search_query):
            # Initially set the item as not matched
            matched = False
            # Check if the item's text matches the query
            for c in range(item.columnCount()):
                item_col_text = item.text(c).lower()
                if search_query in item_col_text:
                    matched = True
                    break

            # Recursively check children of the item
            child_count = item.childCount()
            for i in range(child_count):
                child_item = item.child(i)
                if filter_item(child_item, search_query):
                    matched = True

            # Hide or show item based on match
            item.setHidden(not matched)

            return matched

        # Ensure the search query is correctly applied
        if search_query == '':
            # show all items
            for i in range(self.tree.topLevelItemCount()):
                item = self.tree.topLevelItem(i)
                item.setHidden(False)

                # Show all nested items
                def show_all_children(item):
                    for i in range(item.childCount()):
                        child = item.child(i)
                        child.setHidden(False)
                        show_all_children(child)

                show_all_children(item)
            return

        # Start filtering from the top level items
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            filter_item(item, search_query)

    def get_selected_item_id(self):
        return self.tree.get_selected_item_id()

    def get_selected_folder_id(self):
        return self.tree.get_selected_folder_id()

    def on_cell_edited(self, item):
        item_id = int(item.text(1))
        col_indx = self.tree.currentColumn()
        field_schema = self.schema[col_indx]
        is_config_field = field_schema.get('is_config_field', False)

        if is_config_field:
            self.update_config()
            change_callback = field_schema.get('change_callback', None)
            if change_callback:
                change_callback()
            # reload_on_change = field_schema.get('reload_on_change', False)
        else:
            col_key = convert_to_safe_case(field_schema.get('key', field_schema['text']))
            new_value = item.text(col_indx)
            if not col_key:
                return

            try:
                sql.execute(f"""
                    UPDATE `{self.table_name}`
                    SET `{col_key}` = ?
                    WHERE id = ?
                """, (new_value, item_id,))
            except Exception as e:
                display_message(self,
                    message=f"Error updating item:\n{str(e)}",
                    icon=QMessageBox.Warning,
                )
                self.load()
                return

        if hasattr(self, 'on_edited'):
            self.on_edited()
        self.tree.update_tooltips()

    def add_item(self):
        add_opts = self.add_item_options
        if not add_opts:
            return

        dlg_title = add_opts['title']
        dlg_prompt = add_opts['prompt']

        with block_pin_mode():
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)

            if not ok:
                return False

        try:
            if self.table_name == 'entities':
                # kind = self.'AGENT'  # self.get_kind() if hasattr(self, 'get_kind') else ''
                agent_config = json.dumps({'info.name': text})
                sql.execute(f"INSERT INTO `entities` (`name`, `kind`, `config`) VALUES (?, ?, ?)",
                            (text, self.kind, agent_config))

            elif self.table_name == 'models':
                # kind = self.get_kind() if hasattr(self, 'get_kind') else ''
                api_id = self.parent.parent.parent.get_selected_item_id()
                sql.execute(f"INSERT INTO `models` (`api_id`, `kind`, `name`) VALUES (?, ?, ?)",
                            (api_id, self.kind, text,))

            elif self.table_name == 'tools':
                empty_config = json.dumps(merge_config_into_workflow_config({'_TYPE': 'block', 'block_type': 'Code'}))
                sql.execute(f"INSERT INTO `tools` (`name`, `config`) VALUES (?, ?)", (text, empty_config,))

            elif self.table_name == 'blocks':
                empty_config = json.dumps({'_TYPE': 'block'})
                sql.execute(f"INSERT INTO `blocks` (`name`, `config`) VALUES (?, ?)", (text, empty_config,))

            elif self.table_name == 'tasks':
                empty_config = json.dumps({'_TYPE': 'block', 'block_type': 'Code'})
                sql.execute(f"INSERT INTO `tasks` (`name`, `config`) VALUES (?, ?)", (text, empty_config,))

            else:
                if self.kind:
                    sql.execute(f"INSERT INTO `{self.table_name}` (`name`, `kind`) VALUES (?, ?)", (text, self.kind,))
                else:
                    sql.execute(f"INSERT INTO `{self.table_name}` (`name`) VALUES (?)", (text,))

            last_insert_id = sql.get_scalar("SELECT seq FROM sqlite_sequence WHERE name=?", (self.table_name,))
            self.load(select_id=last_insert_id)

            if hasattr(self, 'on_edited'):
                self.on_edited()
                if self.table_name == 'modules':
                    main = find_main_widget(self)
                    main.main_menu.build_custom_pages()
                    main.page_settings.build_schema()  # !! #
                    main.main_menu.settings_sidebar.toggle_page_pin(text, True)
            return True

        except IntegrityError:
            display_message(self,
                message='Item already exists',
                icon=QMessageBox.Warning,
            )
            return False

    def delete_item(self):
        main = find_main_widget(self)
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(self,
                    message='Folder is locked',
                    icon=QMessageBox.Information,
                )
                return False

            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Delete folder",
                text="Are you sure you want to delete this folder? It's contents will be extracted.",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

            folder_parent = item.parent() if item else None
            folder_parent_id = folder_parent.text(1) if folder_parent else None

            # Unpack all items from folder to parent folder (or root)
            sql.execute(f"""
                UPDATE `{self.table_name}`
                SET folder_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE folder_id = ?
            """, (folder_id,))
            # Unpack all folders from folder to parent folder (or root)
            sql.execute(f"""
                UPDATE `folders`
                SET parent_id = {'NULL' if not folder_parent_id else folder_parent_id}
                WHERE parent_id = ?
            """, (folder_id,))

            sql.execute(f"""
                DELETE FROM folders
                WHERE id = ?
            """, (folder_id,))

            if hasattr(self, 'on_edited'):
                self.on_edited()
            self.load()
            return True
        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return False

            del_opts = self.del_item_options
            if not del_opts:
                return

            dlg_title = del_opts['title']
            dlg_prompt = del_opts['prompt']

            retval = display_message_box(
                icon=QMessageBox.Warning,
                title=dlg_title,
                text=dlg_prompt,
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

            try:
                if self.table_name == 'contexts':
                    context_id = item_id
                    all_context_ids = sql.get_results("""
                        WITH RECURSIVE context_tree AS (
                            SELECT id FROM contexts WHERE id = ?
                            UNION ALL
                            SELECT c.id
                            FROM contexts c
                            JOIN context_tree ct ON c.parent_id = ct.id
                        )
                        SELECT id FROM context_tree;""", (context_id,), return_type='list')
                    if all_context_ids:
                        all_context_ids = tuple(all_context_ids)
                        sql.execute(f"DELETE FROM contexts_messages WHERE context_id IN ({','.join('?' * len(all_context_ids))});", all_context_ids)
                        sql.execute(f"DELETE FROM contexts WHERE id IN ({','.join('?' * len(all_context_ids))});", all_context_ids)

                elif self.table_name == 'apis':
                    api_id = item_id
                    sql.execute("DELETE FROM models WHERE api_id = ?;", (api_id,))
                elif self.table_name == 'modules':
                    from src.system.base import manager
                    manager.modules.unload_module(item_id)
                    pages_module_folder_id = sql.get_scalar("""
                        SELECT id
                        FROM folders
                        WHERE name = 'Pages'
                            AND type = 'modules'
                    """)  # todo de-deupe
                    page_name = sql.get_scalar("SELECT name FROM modules WHERE id = ? and folder_id = ?",
                                               (item_id, pages_module_folder_id))
                    if page_name:
                        main.main_menu.settings_sidebar.toggle_page_pin(page_name, False)

                sql.execute(f"DELETE FROM `{self.table_name}` WHERE `id` = ?", (item_id,))

                if hasattr(self, 'on_edited'):
                    self.on_edited()
                    if self.table_name == 'modules':
                        main.main_menu.build_custom_pages()
                        main.page_settings.build_schema()  # !! #
                self.load()
                return True

            except Exception as e:
                display_message(self,
                    message=f'Item could not be deleted:\n' + str(e),
                    icon=QMessageBox.Warning,
                )
                return False

    def rename_item(self):
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_locked = sql.get_scalar(f"""SELECT locked FROM folders WHERE id = ?""", (folder_id,)) or False
            if is_locked == 1:
                display_message(self,
                    message='Folder is locked',
                    icon=QMessageBox.Information,
                )
                return False

            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename folder', 'Enter a new name for the folder')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            sql.execute(f"UPDATE `folders` SET `name` = ? WHERE id = ?", (text, folder_id))
            self.reload_current_row()

        else:
            current_name = item.text(0)
            dlg_title, dlg_prompt = ('Rename item', 'Enter a new name for the item')
            text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt, text=current_name)
            if not ok:
                return

            item_id = self.get_selected_item_id()
            if not item_id:
                return False

            sql.execute(f"UPDATE `{self.table_name}` SET `name` = ? WHERE id = ?", (text, item_id,))
            self.reload_current_row()

        if hasattr(self, 'on_edited'):
            self.on_edited()

    def pin_item(self):
        is_pinned = self.is_tree_item_pinned()
        item = self.tree.currentItem()
        if not item:
            return
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            sql.execute(f"UPDATE folders SET pinned = ? WHERE id = ?", (not is_pinned, int(item.text(1))))
        else:
            sql.execute(f"UPDATE `{self.table_name}` SET pinned = ? WHERE id = ?", (not is_pinned, self.get_selected_item_id()))

        self.load()
        # item_id = int(item.text(1))
        # if item_id in self.pinned_items:
        #     self.pinned_items.remove(item_id)
        # else:
        #     self.pinned_items.add(item_id)
        #
        # self.update_config()

    def run_btn_clicked(self):
        main = find_main_widget(self)
        if main.page_chat.workflow.responding:
            return
        item_id = self.get_selected_item_id()
        if not item_id:
            return
        main.page_chat.new_context(entity_id=item_id, entity_table=self.table_name)
        main.page_chat.ensure_visible()

    def add_folder_btn_clicked(self):
        self.add_folder()
        self.load()

    def add_folder(self, name=None, parent_folder=None):
        if self.folder_key is None:
            raise ValueError('Folder key not set')

        if parent_folder is None:
            item = self.tree.currentItem()
            parent_item = item.parent() if item else None
            parent_id = int(parent_item.text(1)) if parent_item else None
        else:
            parent_id = parent_folder

        if name is None:
            dlg_title, dlg_prompt = ('New folder', 'Enter the name of the new folder')
            name, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
            if not ok:
                return

        kind = self.filter_widget.get_kind() if hasattr(self, 'filter_widget') else self.kind
        folder_key = self.folder_key.get(kind) if isinstance(self.folder_key, dict) else self.folder_key
        # check if name already exists
        ex_ids = sql.get_results(f"""
            SELECT id
            FROM folders 
            WHERE name = ? 
                AND parent_id {'is' if not parent_id else '='} ?
                AND type = ?""",
            (name, parent_id, folder_key),
            return_type='list'
        )
        if len(ex_ids) > 0:
            return ex_ids[0]

        sql.execute(f"INSERT INTO `folders` (`name`, `parent_id`, `type`) VALUES (?, ?, ?)",
                    (name, parent_id, folder_key))
        ins_id = sql.get_scalar("SELECT MAX(id) FROM folders")

        if hasattr(self, 'on_edited'):
            self.on_edited()

        return ins_id

    def duplicate_item(self):
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            display_message(self,
                message='Folders cannot be duplicated yet',
                icon=QMessageBox.Information,
            )
            return

        else:
            id = self.get_selected_item_id()
            if not id:
                return False

            config = sql.get_scalar(f"""
                SELECT
                    `config`
                FROM `{self.table_name}`
                WHERE id = ?
            """, (id,))
            if not config:
                return False

            add_opts = self.add_item_options
            if not add_opts:
                return
            dlg_title = add_opts['title']
            dlg_prompt = add_opts['prompt']

            with block_pin_mode():
                text, ok = QInputDialog.getText(self, dlg_title, dlg_prompt)
                if not ok:
                    return False

            if self.table_name == 'entities':
                sql.execute(f"""
                    INSERT INTO `entities` (`name`, `kind`, `config`)
                    VALUES (?, ?, ?)
                """, (text, self.kind, config))
            else:
                sql.execute(f"""
                    INSERT INTO `{self.table_name}` (`name`, `config`)
                    VALUES (?, ?)
                """, (text, config,))
            if hasattr(self, 'on_edited'):
                self.on_edited()
            self.load()

    def show_context_menu(self):
        menu = QMenu(self)

        btn_rename = menu.addAction('Rename')
        btn_duplicate = menu.addAction('Duplicate')
        btn_delete = menu.addAction('Delete')
        # add separator
        if self.items_pinnable:
            menu.addSeparator()
            is_pinned = self.is_tree_item_pinned()
            btn_pin = menu.addAction('Pin' if not is_pinned else 'Unpin')
            btn_pin.triggered.connect(self.pin_item)

        btn_rename.triggered.connect(self.rename_item)
        btn_duplicate.triggered.connect(self.duplicate_item)
        btn_delete.triggered.connect(self.delete_item)

        menu.exec_(QCursor.pos())

    def show_history_context_menu(self):
        if not self.versionable:
            return

        id = self.get_selected_item_id()
        if not id:
            return

        metadata = sql.get_scalar(f"""
            SELECT metadata
            FROM `{self.table_name}`
            WHERE id = ?
        """, (id,))
        if not metadata:
            return

        metadata = json.loads(metadata)
        current_version = metadata.get('current_version', None)
        versions = metadata.get('versions', {})

        menu = QMenu(self)
        for key, value in versions.items():
            action = menu.addAction(key)
            action.setCheckable(True)
            action.setChecked(key == current_version)
            action.triggered.connect(lambda: self.load_version(key))
        # show_history = menu.addAction('Last week')
        # show_history = menu.addAction('Yesterday 17:42')
        sep = menu.addSeparator()
        # show_history = menu.addAction('Newwww')
        # sep = menu.addSeparator()
        # show_history = menu.addAction('Delete version')
        show_history = menu.addAction('Save as new version')
        # show_history.triggered.connect(self.show_history)
        menu.exec_(QCursor.pos())

    def load_version(self, version_config):
        pass

    def is_tree_item_pinned(self):
        # todo temp
        item = self.tree.currentItem()
        if not item:
            return None
        tag = item.data(0, Qt.UserRole)
        if tag == 'folder':
            folder_id = int(item.text(1))
            is_pinned = sql.get_scalar(f"""
                SELECT pinned
                FROM folders
                WHERE id = ?
                """, (folder_id,)) == 1
            return is_pinned

        else:
            item_id = self.get_selected_item_id()
            if not item_id:
                return False
            is_pinned = sql.get_scalar(f"""
                SELECT pinned
                FROM `{self.table_name}`
                WHERE id = ?
                """, (item_id,)) == 1
            return is_pinned

    def check_infinite_load(self):
        if self.tree.verticalScrollBar().value() == self.tree.verticalScrollBar().maximum():
            self.load(append=True)


class ConfigJsonTree(ConfigTree):
    """
    A tree widget that is loaded from and saved to a config
    """
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)

        self.tree_buttons.btn_add.clicked.connect(self.add_item)
        self.tree_buttons.btn_del.clicked.connect(self.delete_item)

    def load(self):
        with block_signals(self):
            self.tree.clear()

            ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
            row_data_json = self.config.get(f'{ns}data', None)
            if row_data_json is None:
                return

            if isinstance(row_data_json, str):
                parsed, row_data_json = try_parse_json(row_data_json)
                if not parsed: return  # todo show error message
            data = row_data_json
            for row_dict in data:
                self.add_new_entry(row_dict)
            self.set_height()

    def update_config(self):
        schema = self.schema
        config = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            item_config = {}
            for j in range(len(schema)):
                key = convert_to_safe_case(schema[j].get('key', schema[j]['text']))
                col_type = schema[j].get('type', str)
                cell_widget = self.tree.itemWidget(row_item, j)

                combos = ['RoleComboBox', 'InputSourceComboBox', 'InputTargetComboBox']
                if col_type in combos:
                    # current_index = cell_widget.currentIndex()
                    item_data = cell_widget.currentData()
                    item_config[key] = item_data
                    if col_type == 'InputSourceComboBox':
                        item_config['source_options'] = cell_widget.current_options()
                    elif col_type == 'InputTargetComboBox':
                        item_config['target_options'] = cell_widget.current_options()
                    continue  # todo because of the issue below
                    # item_config[key] = get_widget_value(cell_widget)  # cell_widget.currentText()
                elif isinstance(col_type, str):
                    if isinstance(cell_widget, QCheckBox):
                        col_type = bool

                if col_type == bool:
                    item_config[key] = True if cell_widget.checkState() == Qt.Checked else False
                elif isinstance(col_type, tuple):
                    item_config[key] = cell_widget.currentText()
                else:
                    item_config[key] = row_item.text(j)

            tag = row_item.data(0, Qt.UserRole)
            if tag == 'folder':
                item_config['_TYPE'] = 'folder'
            config.append(item_config)

        ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
        self.config = {f'{ns}data': config}
        super().update_config()

    def add_new_entry(self, row_dict, parent_item=None, icon=None):
        with block_signals(self.tree):
            col_values = [row_dict.get(convert_to_safe_case(col_schema.get('key', col_schema['text'])), None)
                          for col_schema in self.schema]

            parent_item = parent_item or self.tree
            item = QTreeWidgetItem(parent_item, [str(v) for v in col_values])

            if self.readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)

            combos = ['RoleComboBox', 'InputSourceComboBox', 'InputTargetComboBox']
            for i, col_schema in enumerate(self.schema):
                ftype = col_schema.get('type', None)
                default = col_schema.get('default', '')
                key = convert_to_safe_case(col_schema.get('key', col_schema['text']))
                val = row_dict.get(key, default)
                if ftype in combos:
                    if ftype == 'RoleComboBox':
                        widget = RoleComboBox()
                    elif ftype == 'InputSourceComboBox':
                        widget = InputSourceComboBox(self)
                    elif ftype == 'InputTargetComboBox':
                        widget = InputTargetComboBox(self)

                    # elif val:
                    #     widget.setCurrentText(val)
                    #     widget.customCurrentIndexChanged.connect(self.cell_edited)
                    self.tree.setItemWidget(item, i, widget)

                    # index = widget.findData(val)
                    # widget.setCurrentIndex(index)
                    # set the tree item combo widget instead
                    widget = self.tree.itemWidget(item, i)
                    index = widget.findData(val)
                    widget.setCurrentIndex(index)

                    if ftype == 'InputSourceComboBox':
                        widget.set_options(val, row_dict.get('source_options', None))

                    # if ftype == 'RoleComboBox':
                    widget.currentIndexChanged.connect(self.on_cell_edited)
                    # else:
                    #     widget.main_combo.currentIndexChanged.connect(self.cell_edited)

                elif ftype == QPushButton:
                    btn_func = col_schema.get('func', None)
                    btn_partial = partial(btn_func, row_dict)
                    btn_icon_path = col_schema.get('icon', '')
                    pixmap = colorize_pixmap(QPixmap(btn_icon_path))
                    self.tree.setItemIconButtonColumn(item, i, pixmap, btn_partial)
                elif ftype == bool:
                    widget = QCheckBox()
                    self.tree.setItemWidget(item, i, widget)
                    widget.setChecked(val)
                    widget.stateChanged.connect(self.on_cell_edited)
                elif isinstance(ftype, tuple):
                    widget = BaseComboBox()
                    widget.addItems(ftype)
                    widget.setCurrentText(str(val))

                    widget.currentIndexChanged.connect(self.on_cell_edited)
                    self.tree.setItemWidget(item, i, widget)

            if icon:
                item.setIcon(0, QIcon(icon))

            is_folder = row_dict.get('_TYPE', None) == 'folder'
            if is_folder:
                item.setData(0, Qt.UserRole, 'folder')
                item.setIcon(1, QIcon(colorize_pixmap(QPixmap(':/resources/icon-folder.png'))))

                folder_data = row_dict.get('_data', [])
                for row_data in folder_data:
                    self.add_new_entry(row_data, parent_item=item)
                # item.setIcon(0, QIcon(':/icons/folder.png'))
            # return item

    def set_height(self):
        # tree height including column header and row height * number of rows
        header_height = self.tree.header().height()
        row_height = self.tree.sizeHintForRow(0)
        row_count = self.tree.topLevelItemCount()
        self.setFixedHeight(header_height + (row_height * row_count) + 40)

    def on_cell_edited(self, item):
        self.update_config()
        col_indx = self.tree.currentColumn()
        field_schema = self.schema[col_indx]

        on_edit_reload = field_schema.get('on_edit_reload', False)
        if on_edit_reload:
            self.load()

    def add_item(self, row_dict=None, icon=None):
        if row_dict is None:
            row_dict = {convert_to_safe_case(col.get('key', col['text'])): col.get('default', '')
                        for col in self.schema}
        self.add_new_entry(row_dict, icon)
        self.update_config()
        self.set_height()

    def delete_item(self):
        item = self.tree.currentItem()
        if item is None:
            return

        get_columns = ['content', 'description']
        col_indexs = [i for i, col in enumerate(self.schema)
                         if convert_to_safe_case(col.get('key', col['text'])) in get_columns]
        show_warning = False
        for i in col_indexs:
            col_val = item.text(i)
            if col_val:
                show_warning = True

        if show_warning:
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Delete item",
                text="Are you sure you want to delete this item?",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return False

        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        self.update_config()
        self.set_height()


class ConfigJsonFileTree(ConfigTree):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent, **kwargs)

    def load(self):
        with block_signals(self):
            self.tree.clear()

            ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
            row_data_json = self.config.get(f'{ns}data', None)
            if row_data_json is None:
                return

            if isinstance(row_data_json, str):
                parsed, row_data_json = try_parse_json(row_data_json)
                if not parsed: return  # todo show error message
            data = row_data_json
            for row_dict in data:
                self.add_new_entry(row_dict)
            # self.set_height()

    # def get_item_config_recursive(self, row_item):
    #     item_config = {}
    #     for j in range(len(self.schema)):
    #         key = convert_to_safe_case(self.schema[j].get('key', self.schema[j]['text']))
    #         col_type = self.schema[j].get('type', str)
    #         cell_widget = self.tree.itemWidget(row_item, j)
    #
    #         combos = ['RoleComboBox', 'InputSourceComboBox', 'InputTargetComboBox']
    #         if col_type in combos:
    #             # current_index = cell_widget.currentIndex()
    #             item_data = cell_widget.currentData()
    #             item_config[key] = item_data
    #             if col_type == 'InputSourceComboBox':
    #                 item_config['source_options'] = cell_widget.current_options()
    #             elif col_type == 'InputTargetComboBox':
    #                 item_config['target_options'] = cell_widget.current_options()
    #             continue  # todo because of the issue below
    #             # item_config[key] = get_widget_value(cell_widget)  # cell_widget.currentText()
    #         elif isinstance(col_type, str):
    #             if isinstance(cell_widget, QCheckBox):
    #                 col_type = bool
    #
    #         if col_type == bool:
    #             item_config[key] = True if cell_widget.checkState() == Qt.Checked else False
    #         elif isinstance(col_type, tuple):
    #             item_config[key] = cell_widget.currentText()
    #         else:
    #             item_config[key] = row_item.text(j)
    #
    #     tag = row_item.data(0, Qt.UserRole)
    #     if tag == 'folder':
    #         item_config['_TYPE'] = 'folder'
    #         item_config['_data'] = []
    #         for i in range(row_item.childCount()):
    #             child_item = row_item.child(i)
    #             item_config['_data'].append(self.get_item_config_recursive(child_item))

    def get_item_config_recursive(self, row_item):
        """
        Get the config (as a dictionary) for the QTreeWidgetItem 'row_item'.
        If the item is a folder (tag 'folder'), then recursively get and
        include its children in the _data list.
        """
        item_config = {}
        # Loop over each column in this row (assuming self.schema is a list
        # that defines the columns)
        for col_index in range(len(self.schema)):
            col_config = self.schema[col_index]
            # Use the safe key (either 'key' in the schema or the 'text')
            key = convert_to_safe_case(col_config.get('key', col_config.get('text')))
            col_type = col_config.get('type', str)
            cell_widget = self.tree.itemWidget(row_item, col_index)

            # Handle specific combo box types that store data differently.
            if col_type in ['RoleComboBox', 'InputSourceComboBox', 'InputTargetComboBox']:
                item_data = cell_widget.currentData()
                item_config[key] = item_data
                if col_type == 'InputSourceComboBox':
                    item_config['source_options'] = cell_widget.current_options()
                elif col_type == 'InputTargetComboBox':
                    item_config['target_options'] = cell_widget.current_options()
            # If col_type is specified as a string and the cell widget is a QCheckBox,
            # then treat it as a boolean.
            elif isinstance(col_type, str) and isinstance(cell_widget, QCheckBox):
                item_config[key] = (cell_widget.checkState() == Qt.Checked)
            # For all others, simply use the text() as stored in the QTreeWidgetItem.
            else:
                item_config[key] = row_item.text(col_index)

        # Check if the item is a folder. It’s identified by tag stored in Qt.UserRole.
        tag = row_item.data(0, Qt.UserRole)
        if tag == 'folder':
            item_config['_TYPE'] = 'folder'
            item_config['_data'] = []
            # Loop over children and recursively add their config dicts.
            for child_index in range(row_item.childCount()):
                child_item = row_item.child(child_index)
                child_config = self.get_item_config_recursive(child_item)
                item_config['_data'].append(child_config)

        return item_config

    def update_config(self):  # todo dedupe and merge with ConfigJsonTree
        config = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            item_config = self.get_item_config_recursive(row_item)
            config.append(item_config)

        ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
        self.config = {f'{ns}data': config}
        super().update_config()

    def add_new_entry(self, row_dict, parent_item=None, icon=None):
        with block_signals(self.tree):
            col_values = [row_dict.get(convert_to_safe_case(col_schema.get('key', col_schema['text'])), None)
                          for col_schema in self.schema]

            parent_item = parent_item or self.tree
            item = QTreeWidgetItem(parent_item, [str(v) for v in col_values])

            if self.readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)

            is_folder = row_dict.get('_TYPE', None) == 'folder'
            if is_folder:
                item.setData(0, Qt.UserRole, 'folder')
                item.setIcon(1, QIcon(colorize_pixmap(QPixmap(':/resources/icon-folder.png'))))

        folder_data = row_dict.get('_data', [])
        for row_data in folder_data:
            self.add_new_entry(row_data, parent_item=item)


class ConfigVoiceTree(ConfigDBTree):
    """At the top left is an api provider combobox, below that is the tree of voices, and to the right is the config widget."""
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
            ],
            tree_header_hidden=True,
            readonly=True,
        )

    def after_init(self):
        # take the tree from the layout
        # tree_layout = self.tree_layout
        self.tree_layout.setSpacing(5)
        tree = self.tree_layout.itemAt(0).widget()

        # add the api provider combobox
        self.api_provider = APIComboBox(with_model_kinds=('VOICE',))
        self.api_provider.currentIndexChanged.connect(self.load)

        # add spacing
        self.tree_layout.insertWidget(0, self.api_provider)

        # add the tree back to the layout
        self.tree_layout.addWidget(tree)

    def load(self, select_id=None, append=False):
        """
        Loads the QTreeWidget with folders and agents from the database.
        """
        api_voices = sql.get_results(query="""
            SELECT
                name,
                id
            FROM models
            WHERE api_id = ?
                AND kind = 'VOICE'
            ORDER BY name
        """, params=(1,))

        self.tree.load(
            data=api_voices,
            append=append,
            folder_key=None,
            # folder_key=self.folder_key,
            init_select=False,
            readonly=False,
            schema=self.schema,
        )

    def on_cell_edited(self, item):
        pass

    def add_item(self):
        pass

    def delete_item(self):
        pass

    def rename_item(self):
        pass

    def show_context_menu(self):
        pass


class ConfigAsyncWidget(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.main = find_main_widget(self)

    def load(self):
        load_runnable = self.LoadRunnable(self)
        self.main.threadpool.start(load_runnable)

    class LoadRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()

        def run(self):
            pass

class ConfigExtTree(ConfigJsonTree):
    fetched_rows_signal = Signal(list)

    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            conf_namespace=kwargs.get('conf_namespace', None),
            # propagate=False,
            schema=kwargs.get('schema', []),
            layout_type=kwargs.get('layout_type', 'vertical'),
            config_widget=kwargs.get('config_widget', None),
            # add_item_options=kwargs.get('add_item_options', None),
            # del_item_options=kwargs.get('del_item_options', None),
            tree_width=kwargs.get('tree_width', 400)
        )
        self.fetched_rows_signal.connect(self.load_rows, Qt.QueuedConnection)

        # self.main = find_main_widget(self)
        # if not self.main:
        #     # raise ValueError('Main widget not found')
        #     pass
        #     find_main_widget(self)

    def load(self, rows=None):
        rows = self.config.get(f'{self.conf_namespace}.data', [])
        self.insert_rows(rows)
        main = find_main_widget(self)
        load_runnable = self.LoadRunnable(self)
        main.threadpool.start(load_runnable)

    @Slot(list)
    def load_rows(self, rows):
        # self.config[f'{self.conf_namespace}.data'] = rows
        self.insert_rows(rows)
        # single shot
        QTimer.singleShot(10, self.update_config)

    def insert_rows(self, rows):
        with block_signals(self.tree):
            self.tree.clear()
            for row_fields in rows:
                item = QTreeWidgetItem(self.tree, row_fields)

    def get_config(self):
        config = {}
        data = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            row_data = [row_item.text(j) for j in range(row_item.columnCount())]
            data.append(row_data)
        config[f'{self.conf_namespace}.data'] = data
        return config

    def update_config(self):
        """Bubble update config dict to the root config widget"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    # def save_config(self):
    #     """Remove the super method to prevent saving the config"""
    #     pass

    class LoadRunnable(QRunnable):
        def __init__(self, parent):
            super().__init__()
            main = find_main_widget(parent)
            self.page_chat = main.page_chat

        def run(self):
            pass

    def on_item_selected(self):
        pass


class ConfigJsonDBTree(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)  # , **kwargs)
        self.table_name = kwargs.get('table_name', None)
        self.item_icon_path = kwargs.get('item_icon_path', None)
        self.key_field = kwargs.get('key_field', 'id')
        self.show_fields = kwargs.get('show_fields', None)
        self.item_icon = colorize_pixmap(QPixmap(self.item_icon_path))

        self.schema = kwargs.get('schema', [])
        tree_height = kwargs.get('tree_height', None)

        self.readonly = kwargs.get('readonly', False)
        tree_width = kwargs.get('tree_width', 200)
        tree_header_hidden = kwargs.get('tree_header_hidden', False)
        layout_type = kwargs.get('layout_type', 'vertical')

        self.layout = QVBoxLayout(self) if layout_type == 'vertical' else QHBoxLayout(self)
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)

        tree_layout = QVBoxLayout()
        self.tree_buttons = TreeButtons(parent=self)
        self.tree_buttons.btn_add.clicked.connect(self.add_item)
        self.tree_buttons.btn_del.clicked.connect(self.delete_item)

        self.tree = BaseTreeWidget(parent=self)
        if tree_height:
            self.tree.setFixedHeight(tree_height)
        # self.tree.itemDoubleClicked.connect(self.goto_link)
        self.tree.setHeaderHidden(tree_header_hidden)
        self.tree.setSortingEnabled(False)

        tree_layout.addWidget(self.tree_buttons)
        tree_layout.addWidget(self.tree)
        self.layout.addLayout(tree_layout)

        self.tree.move(-15, 0)

    def load(self):
        with block_signals(self.tree):
            self.tree.clear()

            id_list = next(iter(self.config.values()), None)  # !! #
            if id_list is None:
                return
            # id_list = json.loads(row_data_json_str)

            if len(id_list) == 0:
                return
            if not self.show_fields:
                return

            if self.key_field == 'id':
                id_list = [int(i) for i in id_list]
            results = sql.get_results(f"""
                SELECT
                    {','.join(self.show_fields)}
                FROM {self.table_name}
                WHERE {self.key_field} IN ({','.join(['?' for i in id_list])})
            """, id_list)
            for row_tuple in results:
                self.add_new_entry(row_tuple, self.item_icon)

    def add_new_entry(self, row_tuple, icon=None):
        with block_signals(self.tree):
            item = QTreeWidgetItem(self.tree, [str(v) for v in row_tuple])

            if self.readonly:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            else:
                item.setFlags(item.flags() | Qt.ItemIsEditable)

            for i, col_schema in enumerate(self.schema):
                ftype = col_schema.get('type', None)
                # default = col_schema.get('default', '')

                val = row_tuple[i]
                if ftype == 'RoleComboBox':
                    widget = RoleComboBox()
                    widget.setFixedWidth(100)
                    index = widget.findData(val)
                    widget.setCurrentIndex(index)
                    widget.currentIndexChanged.connect(self.on_cell_edited)
                    self.tree.setItemWidget(item, i, widget)
                elif ftype == bool:
                    widget = QCheckBox()
                    self.tree.setItemWidget(item, i, widget)
                    widget.setChecked(val)
                    widget.stateChanged.connect(self.on_cell_edited)
                elif isinstance(ftype, tuple):
                    widget = BaseComboBox()
                    widget.addItems(ftype)
                    widget.setCurrentText(str(val))

                    widget.currentIndexChanged.connect(self.on_cell_edited)
                    self.tree.setItemWidget(item, i, widget)

            if icon:
                item.setIcon(0, QIcon(icon))

    def add_item(self, column_vals=None, icon=None):
        if self.table_name == 'tools':
            list_type = 'TOOL'
        elif self.table_name == 'blocks':
            list_type = 'BLOCK'
        elif self.table_name == 'entities':
            list_type = 'AGENT'
        elif self.table_name == 'modules':
            list_type = 'MODULE'
        else:
            raise NotImplementedError(f'DB table not supported: {self.table_name}')

        list_dialog = TreeDialog(
            parent=self,
            title=f'Choose {list_type.capitalize()}',
            list_type=list_type,
            callback=self.add_item_callback,
            # multi_select=True,
        )
        list_dialog.open()

    def add_item_callback(self, item):
        item = item.data(0, Qt.UserRole)
        item_id = item['id']  # is always last column
        item_exists = any([item_id == self.tree.topLevelItem(i).text(len(self.schema) - 1)
                           for i in range(self.tree.topLevelItemCount())])
        if item_exists:
            return

        row_tuple = (item['name'], item['id'])
        self.add_new_entry(row_tuple, self.item_icon)
        self.update_config()

    def delete_item(self):
        item = self.tree.currentItem()
        if item is None:
            return

        self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(item))
        self.update_config()

    def update_config(self):
        schema = self.schema
        config = []
        for i in range(self.tree.topLevelItemCount()):
            row_item = self.tree.topLevelItem(i)
            id_index = len(schema) - 1  # always last column
            row_id = row_item.text(id_index)
            config.append(row_id)

        ns = f'{self.conf_namespace}.' if self.conf_namespace else ''
        self.config = {f'{ns}data': config}  # !! # todo this is instead of calling load_config()
        super().update_config()

    # def goto_link(self, item):  # todo dupe code
    #     from src.gui.widgets import find_main_widget
    #     tool_id = item.text(1)
    #     tool_name = item.text(0)
    #     main = find_main_widget(self)
    #     table_name_map = {
    #         'tools': 'Tools',
    #         'blocks': 'Blocks',
    #         'entities': 'Agents',
    #         'modules': 'Modules',
    #     }
    #     page_name = table_name_map[self.table_name]
    #     main.main_menu.settings_sidebar.page_buttons[page_name].click()
    #     # main.main_menu.settings_sidebar.page_buttons['Settings'].click()
    #     # main.page_settings.settings_sidebar.page_buttons['Tools'].click()
    #     tools_tree = main.main_menu.pages[page_name].tree
    #
    #     # for i in range(tools_tree.topLevelItemCount()):
    #     #     row_name = tools_tree.topLevelItem(i).text(0)
    #     #     if row_name == tool_name:
    #     #         tools_tree.setCurrentItem(tools_tree.topLevelItem(i))
    #
    #     # # RECURSIVELY ITERATE ITEMS AND CHILDREN
    #     # def find_item(tree, name):
    #     #     for i in range(tree.topLevelItemCount()):
    #     #         row_name = tree.topLevelItem(i).text(0)
    #     #         if row_name == name:
    #     #             tree.setCurrentItem(tree.topLevelItem(i))
    #     #             return
    #     #         find_item(tree.topLevelItem(i), name)
    #     #
    #     # find_item(tools_tree, tool_name)
    #     # AttributeError: 'PySide6.QtWidgets.QTreeWidgetItem' object has no attribute 'topLevelItemCount'
    #
    #     #fixed here:
    #     for i in range(tools_tree.topLevelItemCount()):
    #         row_name = tools_tree.topLevelItem(i).text(0)
    #         if row_name == tool_name:
    #             tools_tree.setCurrentItem(tools_tree.topLevelItem(i))
    #             break

# class ConfigJsonFileTree(ConfigJsonTree):
#     def __init__(self, parent, **kwargs):
#         super().__init__(parent=parent, **kwargs)
#         self.setAcceptDrops(True)
#
#         # remove last stretch
#         self.tree_buttons.layout.takeAt(self.tree_buttons.layout.count() - 1)
#
#         self.btn_add_folder = IconButton(
#             parent=self,
#             icon_path=':/resources/icon-new-folder.png',
#             tooltip='Add Folder',
#             size=18,
#         )
#         self.btn_add_folder.clicked.connect(self.add_folder)
#         self.tree_buttons.layout.addWidget(self.btn_add_folder)
#         self.tree_buttons.layout.addStretch(1)
#
#     def load(self):
#         with block_signals(self.tree):
#             self.tree.clear()
#
#             data = next(iter(self.config.values()), None)  # !! #
#             if data is None:
#                 return
#
#             # col_names = [col['text'] for col in self.schema]
#             for row_dict in data:
#                 path = row_dict['location']
#                 icon_provider = QFileIconProvider()
#                 icon = icon_provider.icon(QFileInfo(path))
#                 if icon is None or isinstance(icon, QIcon) is False:
#                     icon = QIcon()
#
#                 self.add_new_entry(row_dict, icon=icon)
#
#     def add_item(self, column_vals=None, icon=None):
#         with block_pin_mode():
#             file_dialog = QFileDialog()
#             # file_dialog.setProperty('class', 'uniqueFileDialog')
#             file_dialog.setFileMode(QFileDialog.ExistingFile)
#             file_dialog.setOption(QFileDialog.ShowDirsOnly, False)
#             file_dialog.setFileMode(QFileDialog.Directory)
#             # file_dialog.setStyleSheet("QFileDialog { color: black; }")
#             path, _ = file_dialog.getOpenFileName(None, "Choose Files", "", options=file_dialog.Options())
#
#         if path:
#             self.add_path(path)
#
#     def add_folder(self):
#         with block_pin_mode():
#             file_dialog = QFileDialog()
#             file_dialog.setFileMode(QFileDialog.Directory)
#             file_dialog.setOption(QFileDialog.ShowDirsOnly, True)
#             path = file_dialog.getExistingDirectory(self, "Choose Directory", "")
#             if path:
#                 self.add_path(path)
#
#     def add_path(self, path):
#         filename = os.path.basename(path)
#         is_dir = os.path.isdir(path)
#         row_dict = {'filename': filename, 'location': path, 'is_dir': is_dir}
#
#         icon_provider = QFileIconProvider()
#         icon = icon_provider.icon(QFileInfo(path))
#         if icon is None or isinstance(icon, QIcon) is False:
#             icon = QIcon()
#
#         super().add_item(row_dict, icon)
#
#     def dragEnterEvent(self, event):
#         # Check if the event contains file paths to accept it
#         if event.mimeData().hasUrls():
#             event.acceptProposedAction()
#
#     def dragMoveEvent(self, event):
#         # Check if the event contains file paths to accept it
#         if event.mimeData().hasUrls():
#             event.acceptProposedAction()
#
#     def dropEvent(self, event):
#         # Get the list of URLs from the event
#         urls = event.mimeData().urls()
#
#         # Extract local paths from the URLs
#         paths = [url.toLocalFile() for url in urls]
#
#         for path in paths:
#             self.add_path(path)
#
#         event.acceptProposedAction()


class ConfigPlugin(ConfigWidget):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)

        self.layout = CVBoxLayout(self)
        self.layout.setContentsMargins(0, 5, 0, 0)

        self.plugin_type = kwargs.get('plugin_type', 'Agent')
        self.plugin_json_key = kwargs.get('plugin_json_key', 'use_plugin')
        none_text = kwargs.get('none_text', None)
        plugin_label_text = kwargs.get('plugin_label_text', None)
        plugin_label_width = kwargs.get('plugin_label_width', None)

        h_layout = CHBoxLayout()
        self.plugin_combo = PluginComboBox(plugin_type=self.plugin_type, none_text=none_text)
        self.plugin_combo.setFixedWidth(90)
        self.plugin_combo.currentIndexChanged.connect(self.plugin_changed)
        self.default_class = kwargs.get('default_class', None)
        self.config_widget = None

        if plugin_label_text:
            label = QLabel(plugin_label_text)
            if plugin_label_width is not None:
                label.setFixedWidth(plugin_label_width)
            h_layout.addWidget(label)
        h_layout.addWidget(self.plugin_combo)
        h_layout.addStretch(1)
        self.layout.addLayout(h_layout)
        self.layout.addStretch(1)

    def get_config(self):
        config = {}  # self.config  #
        config[self.plugin_json_key] = self.plugin_combo.currentData()
        c_w_conf = self.config_widget.get_config()
        config.update(self.config_widget.get_config())
        return config

    def plugin_changed(self):
        self.build_plugin_config()
        self.update_config()

    def build_plugin_config(self):
        from src.system.plugins import get_plugin_class
        plugin = self.plugin_combo.currentData()
        plugin_class = get_plugin_class(self.plugin_type, plugin, default_class=self.default_class)
        pass

        self.layout.takeAt(self.layout.count() - 1)  # remove last stretch
        if self.config_widget is not None:
            self.layout.takeAt(self.layout.count() - 1)  # remove config widget
            self.config_widget.deleteLater()

        self.config_widget = plugin_class(parent=self)
        self.layout.addWidget(self.config_widget)
        self.layout.addStretch(1)

        self.config_widget.build_schema()
        self.config_widget.load_config()

    def load(self):
        plugin_value = self.config.get(self.plugin_json_key, '')
        index = self.plugin_combo.findData(plugin_value)
        if index == -1:
            index = 0

        self.plugin_combo.setCurrentIndex(index)  # p

        self.build_plugin_config()
        self.config_widget.load()


class ConfigCollection(ConfigWidget):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.content = None
        self.pages = {}
        # self.hidden_pages = []  # !! #
        self.include_in_breadcrumbs = False

    def load(self):
        current_page = self.content.currentWidget()
        if current_page and hasattr(current_page, 'load'):
            current_page.load()

        self.update_breadcrumbs()

    def get_breadcrumbs(self):
        if not getattr(self, 'include_in_breadcrumbs', True):
            return None
        # return current page name
        current_page = self.content.currentWidget()
        # get self.pages key where value is current_page
        if current_page:
            try:
                page_index = list(self.pages.values()).index(current_page)
                return list(self.pages.keys())[page_index]
            except Exception:
                return None

    def add_page(self):
        edit_bar = getattr(self, 'edit_bar', None)
        if not edit_bar:
            return
        page_editor = edit_bar.page_editor
        if not page_editor:
            return
        if edit_bar.editing_module_id != page_editor.config_widget.item_id:
            return

        new_page_name, ok = QInputDialog.getText(self, "Enter name", "Enter a name for the new page:")
        if not ok:
            return False

        # safe_name = convert_to_safe_case(new_page_name)
        if new_page_name in self.pages:
            display_message(
                self,
                f"A page named '{new_page_name}' already exists.",
                title="Page Exists",
                icon=QMessageBox.Warning,
            )
            return False

        new_class = modify_class_add_page(edit_bar.editing_module_id, edit_bar.class_map, new_page_name)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, edit_bar.editing_module_id))

            from src.system.base import manager
            manager.load_manager('modules')
            page_editor.load()
            page_editor.config_widget.config_widget.widgets[0].reimport()


class ConfigPages(ConfigCollection):
    def __init__(
            self,
            parent,
            align_left=False,
            right_to_left=False,
            bottom_to_top=False,
            button_kwargs=None,
            default_page=None,
            is_pin_transmitter=False,
    ):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QStackedWidget(self)
        # self.user_editable = True
        self.settings_sidebar = None
        self.default_page = default_page
        self.align_left = align_left
        self.right_to_left = right_to_left
        self.bottom_to_top = bottom_to_top
        self.button_kwargs = button_kwargs
        self.is_pin_transmitter = is_pin_transmitter
        self.content.currentChanged.connect(self.on_current_changed)

    def build_schema(self):
        """Build the widgets of all pages from `self.pages`"""
        # self.blockSignals(True)
        # remove all widgets from the content stack
        for i in reversed(range(self.content.count())):
            remove_widget = self.content.widget(i)
            self.content.removeWidget(remove_widget)
            remove_widget.deleteLater()

        # remove settings sidebar
        if getattr(self, 'settings_sidebar', None):
            self.layout.removeWidget(self.settings_sidebar)
            self.settings_sidebar.deleteLater()

        # hidden_pages = getattr(self, 'hidden_pages', [])  # !! #
        with block_signals(self.content, recurse_children=False):
            for page_name, page in self.pages.items():
                # if page_name in hidden_pages:  # !! #
                #     continue

                if hasattr(page, 'build_schema'):
                    page.build_schema()
                self.content.addWidget(page)

            if self.default_page:
                default_page = self.pages.get(self.default_page)
                page_index = self.content.indexOf(default_page)
                self.content.setCurrentIndex(page_index)

        self.settings_sidebar = self.ConfigSidebarWidget(parent=self)

        layout = CHBoxLayout()
        if not self.right_to_left:
            layout.addWidget(self.settings_sidebar)
            layout.addWidget(self.content)
        else:
            layout.addWidget(self.content)
            layout.addWidget(self.settings_sidebar)

        self.layout.addLayout(layout)

        if hasattr(self, 'after_init'):
            self.after_init()
        # self.blockSignals(False)

    def on_current_changed(self, _):
        self.load()
        self.update_breadcrumbs()

    class ConfigSidebarWidget(QWidget):
        def __init__(self, parent):  # , width=None):
            super().__init__(parent=parent)

            self.parent = parent
            self.main = find_main_widget(self)
            self.setAttribute(Qt.WA_StyledBackground, True)
            self.setProperty("class", "sidebar")

            self.button_kwargs = parent.button_kwargs or {}
            self.button_type = self.button_kwargs.get('button_type', 'text')

            self.layout = CVBoxLayout(self)
            self.layout.setContentsMargins(10, 0, 10, 0)
            self.button_group = None
            self.new_page_btn = None

            self.load()

        def load(self):
            class_name = self.parent.__class__.__name__
            skip_count = 3 if class_name == 'MainPages' else 0
            clear_layout(self.layout, skip_count=skip_count)  # for title button bar todo dirty
            self.new_page_btn = None

            pinnable_pages = []  # todo
            pinned_pages = []
            # visible_pages = self.parent.pages

            if self.parent.is_pin_transmitter:
                main = find_main_widget(self)
                pinnable_pages = main.pinnable_pages()  # getattr(self.parent, 'pinnable_pages', [])
                pinned_pages = main.pinned_pages()
                # visible_pages = {key: page for key, page in self.parent.pages.items()}
                #                  # if key not in self.parent.hidden_pages}  # !! #

            if self.button_type == 'icon':
                self.page_buttons = {
                    key: IconButton(
                        parent=self,
                        icon_path=getattr(page, 'icon_path', ':/resources/icon-pages-large.png'),
                        size=self.button_kwargs.get('icon_size', QSize(16, 16)),
                        tooltip=key.title(),
                        checkable=True,
                    ) for key, page in self.parent.pages.items()
                }
                self.page_buttons['Chat'].setObjectName("homebutton")

                for btn in self.page_buttons.values():
                    btn.setCheckable(True)
                visible_pages = {key: page for key, page in self.parent.pages.items()
                                 if key in pinned_pages}

            elif self.button_type == 'text':
                self.page_buttons = {
                    key: self.Settings_SideBar_Button(
                        parent=self,
                        text=key,
                        **self.button_kwargs,
                    ) for key in self.parent.pages.keys()
                }
                visible_pages = {key: page for key, page in self.parent.pages.items()
                                 if key not in pinned_pages}

            self.button_group = QButtonGroup(self)

            if len(self.page_buttons) > 0:
                for page_key, page_btn in self.page_buttons.items():
                    visible = page_key in visible_pages
                    if not visible:
                        page_btn.setVisible(False)

                for page_key, page_btn in self.page_buttons.items():
                    page_btn.setContextMenuPolicy(Qt.CustomContextMenu)
                    page_btn.customContextMenuRequested.connect(lambda pos, btn=page_btn: self.show_context_menu(pos, btn, pinnable_pages))

            for i, (key, btn) in enumerate(self.page_buttons.items()):
                self.button_group.addButton(btn, i)
                self.layout.addWidget(btn)

            if self.parent.__class__.__name__ != 'MainPages':
                self.new_page_btn = IconButton(
                    parent=self,
                    icon_path=':/resources/icon-new-large.png',
                    size=25,
                )
                if not find_attribute(self.parent, 'user_editing'):
                    self.new_page_btn.hide()
                self.new_page_btn.setMinimumWidth(25)
                self.new_page_btn.clicked.connect(self.parent.add_page)
                self.layout.addWidget(self.new_page_btn)

            if not self.parent.bottom_to_top:
                self.layout.addStretch(1)
            self.button_group.buttonClicked.connect(self.on_button_clicked)

        def show_context_menu(self, pos, button, pinnable_pages):
            menu = QMenu(self)

            from src.system.base import manager
            custom_pages = manager.modules.get_page_modules()
            page_key = next(key for key, value in self.page_buttons.items() if value == button)
            is_custom_page = page_key in custom_pages
            if page_key in pinnable_pages:
                if isinstance(button, IconButton):
                    btn_unpin = menu.addAction('Unpin')
                    btn_unpin.triggered.connect(lambda: self.unpin_page(page_key))
                elif isinstance(button, self.Settings_SideBar_Button):
                    btn_pin = menu.addAction('Pin')
                    btn_pin.triggered.connect(lambda: self.pin_page(page_key))

            if is_custom_page:
                btn_edit = menu.addAction('Edit')
                btn_edit.triggered.connect(lambda: self.edit_page(page_key))

            user_editing = find_attribute(self.parent, 'user_editing', False)
            if user_editing:
                btn_edit = menu.addAction('Delete')
                btn_edit.triggered.connect(lambda: self.delete_page(page_key))

            menu.exec_(QCursor.pos())

        def edit_page(self, page_name):
            from src.gui.pages.modules import PageEditor
            from src.system.base import manager
            page_modules = manager.modules.get_page_modules(with_ids=True)

            # get the id KEY where the name VALUE is page_name
            module_id = next((_id for _id, name in page_modules if name == page_name), None)
            if not module_id:
                return

            page_widget = self.parent.pages[page_name]
            # setattr(page_widget, 'user_editing', True)
            if hasattr(page_widget, 'toggle_widget_edit'):
                page_widget.toggle_widget_edit(True)
                # page_widget.build_schema()  # !! #

            main = find_main_widget(self)
            if getattr(main, 'module_popup', None):
                main.module_popup.close()
                main.module_popup = None
            main.module_popup = PageEditor(main, module_id)
            main.module_popup.load()
            main.module_popup.show()  # todo dedupe
        #
        # def rename_page(self, page_name):
        #     pass
        #
        def delete_page(self, page_name):  # todo dedupe
            retval = display_message_box(
                icon=QMessageBox.Warning,
                title="Delete page",
                text=f"Are you sure you want to permenantly delete the page '{page_name}'?",
                buttons=QMessageBox.Yes | QMessageBox.No,
            )
            if retval != QMessageBox.Yes:
                return

            edit_bar = getattr(self.parent, 'edit_bar', None)
            if not edit_bar:
                return
            page_editor = edit_bar.page_editor
            if not page_editor:
                return
            if edit_bar.editing_module_id != page_editor.config_widget.item_id:
                return

            safe_name = convert_to_safe_case(page_name)
            new_class = modify_class_delete_page(edit_bar.editing_module_id, edit_bar.class_map, safe_name)
            if new_class:
                # `config` is a table json column (a dict)
                # the code needs to go in the 'data' key
                sql.execute("""
                    UPDATE modules
                    SET config = json_set(config, '$.data', ?)
                    WHERE id = ?
                """, (new_class, edit_bar.editing_module_id))

                from src.system.base import manager
                manager.load_manager('modules')
                page_editor.load()
                page_editor.config_widget.config_widget.widgets[0].reimport()

        def toggle_page_pin(self, page_name, pinned):
            from src.system.base import manager
            pinned_pages = sql.get_scalar("SELECT `value` FROM settings WHERE `field` = 'pinned_pages';")
            pinned_pages = set(json.loads(pinned_pages) if pinned_pages else [])

            if pinned:
                pinned_pages.add(page_name)
            elif page_name in pinned_pages:
                pinned_pages.remove(page_name)
            sql.execute("""UPDATE settings SET value = json(?) WHERE `field` = 'pinned_pages';""",
                        (json.dumps(list(pinned_pages)),))
            # sql.execute("""UPDATE settings SET value = json_set(value, '$."display.pinned_pages"', json(?)) WHERE `field` = 'app_config'""",
            #             (json.dumps(list(pinned_pages)),))
            manager.config.load()
            app_config = manager.config.dict
            self.main.page_settings.load_config(app_config)
            self.load()  # load this sidebar

        def pin_page(self, page_name):
            """Always called from page_settings.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=True)
            target_widget = self.main.main_menu
            target_widget.settings_sidebar.load()

            # if current page is the one being pinned, switch the page_settings sidebar to the system page, then switch to the pinned page
            self.click_menu_button(target_widget, page_name)
            # current_page = self.parent.content.currentWidget()
            # pinning_page = self.parent.pages[page_name]
            # if current_page == pinning_page:
            #     system_button = next(iter(self.page_buttons.values()), None)
            #     system_button.click()
            #
            #     click_button = self.main.main_menu.settings_sidebar.page_buttons.get(page_name)
            #     if click_button:
            #         self.main.main_menu.settings_sidebar.on_button_clicked(click_button)

        def unpin_page(self, page_name):
            """Always called from main_pages.sidebar_menu"""
            self.toggle_page_pin(page_name, pinned=False)
            target_widget = self.main.page_settings
            target_widget.settings_sidebar.load()

            # if current page is the one being unpinned, switch to the system page, then switch to the unpinned page
            self.click_menu_button(target_widget, page_name)
            # current_page = self.parent.content.currentWidget()
            # unpinning_page = self.parent.pages[page_name]
            # if current_page == unpinning_page:
            #     settings_button = next(iter(self.page_buttons.values()), None)
            #     settings_button.click()
            #
            #     click_button = self.main.page_settings.settings_sidebar.page_buttons.get(page_name)
            #     if click_button:
            #         self.main.page_settings.settings_sidebar.on_button_clicked(click_button)

        def click_menu_button(self, widget, page_name):
            current_page = self.parent.content.currentWidget()
            unpinning_page = self.parent.pages[page_name]
            if current_page == unpinning_page:
                settings_button = next(iter(self.page_buttons.values()), None)
                settings_button.click()

                click_button = widget.settings_sidebar.page_buttons.get(page_name)
                if click_button:
                    widget.settings_sidebar.on_button_clicked(click_button)


        def on_button_clicked(self, button):
            current_index = self.parent.content.currentIndex()
            clicked_index = self.button_group.id(button)
            if current_index == clicked_index:
                is_main = self.parent.__class__.__name__ == 'MainPages'
                if is_main and button == self.page_buttons.get('Chat'):
                    has_no_messages = len(self.parent.main.page_chat.workflow.message_history.messages) == 0
                    if has_no_messages:
                        return
                    main = find_main_widget(self)
                    copy_context_id = main.page_chat.workflow.context_id
                    main.page_chat.new_context(copy_context_id=copy_context_id)
                return
            self.parent.content.setCurrentIndex(clicked_index)
            button.setChecked(True)

        class Settings_SideBar_Button(QPushButton):
            def __init__(self, parent, text='', text_size=13, align_left=False):
                super().__init__()
                self.setText(self.tr(text))  # todo - translate
                self.setCheckable(True)
                self.font = QFont()
                self.font.setPointSize(text_size)
                self.setFont(self.font)
                if align_left:
                    self.setStyleSheet("QPushButton { text-align: left; }")

class ConfigTabs(ConfigCollection):
    def __init__(self, parent, **kwargs):
        super().__init__(parent=parent)
        self.layout = CVBoxLayout(self)
        self.content = QTabWidget(self)
        self.new_page_btn = None
        # self.user_editable = True
        self.content.currentChanged.connect(self.on_current_changed)
        hide_tab_bar = kwargs.get('hide_tab_bar', False)
        if hide_tab_bar:
            self.content.tabBar().hide()

    def build_schema(self):
        """Build the widgets of all tabs from `self.tabs`"""
        with block_signals(self):
            for tab_name, tab in self.pages.items():
                if hasattr(tab, 'build_schema'):
                    tab.build_schema()
                self.content.addTab(tab, tab_name)

        self.layout.addWidget(self.content)

        self.new_page_btn = IconButton(
            parent=self,
            icon_path=':/resources/icon-new-large.png',
            size=25,
        )
        if not find_attribute(self, 'user_editing'):
            self.new_page_btn.hide()
        self.new_page_btn.setMinimumWidth(25)
        self.new_page_btn.clicked.connect(self.add_page)

        self.recalculate_new_page_btn_position()

    def load(self):
        super().load()
        self.recalculate_new_page_btn_position()

    def on_current_changed(self, _):
        self.load()
        self.update_breadcrumbs()

    # def show_tab_context_menu(self, pos):
    #     tab_index = self.content.tabBar().tabAt(pos)
    #     if tab_index == -1:
    #         return
    #
    #     menu = QMenu(self.parent)
    #
    #     page_key = list(self.pages.keys())[tab_index]
    #     user_editing = find_attribute(self, 'user_editing', False)
    #     if user_editing:
    #         btn_delete = menu.addAction('Delete')
    #         btn_delete.triggered.connect(lambda: self.delete_page(page_key))
    #
    #         menu.exec_(QCursor.pos())  # todo not working why?
    #         # if action == btn_delete:
    #         #     self.delete_page(page_key)

    def recalculate_new_page_btn_position(self):
        if not self.new_page_btn:
            return
        tab_bar = self.content.tabBar()
        pos = tab_bar.mapTo(self, tab_bar.rect().topRight())
        self.new_page_btn.move(pos.x() + 1, pos.y())

    def delete_page(self, page_name):  # todo dedupe
        retval = display_message_box(
            icon=QMessageBox.Warning,
            title="Delete page",
            text=f"Are you sure you want to permenantly delete the page '{page_name}'?",
            buttons=QMessageBox.Yes | QMessageBox.No,
        )
        if retval != QMessageBox.Yes:
            return

        edit_bar = getattr(self, 'edit_bar', None)
        if not edit_bar:
            return
        page_editor = edit_bar.page_editor
        if not page_editor:
            return
        if edit_bar.editing_module_id != page_editor.config_widget.item_id:
            return

        safe_name = convert_to_safe_case(page_name)
        new_class = modify_class_delete_page(edit_bar.editing_module_id, edit_bar.class_map, safe_name)
        if new_class:
            # `config` is a table json column (a dict)
            # the code needs to go in the 'data' key
            sql.execute("""
                UPDATE modules
                SET config = json_set(config, '$.data', ?)
                WHERE id = ?
            """, (new_class, edit_bar.editing_module_id))

            from src.system.base import manager
            manager.load_manager('modules')
            page_editor.load()
            page_editor.config_widget.config_widget.widgets[0].reimport()

class MemberPopupButton(IconButton):
    def __init__(self, parent, use_namespace=None, member_type='agent', **kwargs):
        super().__init__(
            parent=parent,
            icon_path=':/resources/icon-agent-group.png',
            size=24,
        )
        self.use_namespace = use_namespace
        self.config_widget = PopupMember(self, use_namespace=use_namespace, member_type=member_type)
        self.clicked.connect(self.show_popup)

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    def show_popup(self):
        if self.config_widget.isVisible():
            self.config_widget.hide()
        else:
            self.config_widget.show()


class ModelComboBox(BaseComboBox):
    """
    BE CAREFUL SETTING BREAKPOINTS DUE TO PYSIDE COMBOBOX BUG
    Needs to be here atm to avoid circular references
    """
    def __init__(self, *args, **kwargs):
        self.parent = kwargs.pop('parent', None)
        self.first_item = kwargs.pop('first_item', None)
        super().__init__(*args, **kwargs)

        self.options_btn = self.OptionsButton(
            parent=self,
            icon_path=':/resources/icon-settings-solid.png',
            tooltip='Options',
            size=20,
        )
        self.config_widget = PopupModel(self)
        self.layout = CHBoxLayout(self)
        self.layout.addWidget(self.options_btn)
        self.options_btn.move(-20, 0)

        self.load()

    def load(self):
        from src.system.base import manager
        with block_signals(self):
            self.clear()

            model = QStandardItemModel()
            self.setModel(model)

            api_models = {}

            providers = manager.providers.to_dict()
            for provider_name, provider in providers.items():
                for (kind, model_name), api_id in provider.model_api_ids.items():
                    if not model_name:  # todo
                        continue
                    api_name = provider.api_ids[api_id]
                    model_config = provider.models.get((kind, model_name))
                    alias = provider.model_aliases.get((kind, model_name), model_name)
                    api_key = model_config.get('api_key', '')
                    if api_key == '':
                        continue
                    if api_name not in api_models:
                        api_models[api_name] = []
                    api_models[api_name].append((kind, model_name, provider_name, alias))

            for api_name, models in api_models.items():
                if api_name.lower() == 'openai':
                    pass
                header_item = QStandardItem(api_name)
                header_item.setData('header', Qt.UserRole)
                header_item.setEnabled(False)
                font = header_item.font()
                font.setBold(True)
                header_item.setFont(font)
                model.appendRow(header_item)

                for kind, model_name, provider_name, alias in models:
                    data = {
                        'kind': kind,
                        'model_name': model_name or '',  # todo
                        # 'model_params': model_config,  purposefully exclude params
                        'provider': provider_name,
                    }
                    item = QStandardItem(alias)
                    item.setData(json.dumps(data), Qt.UserRole)
                    model.appendRow(item)

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

        self.refresh_options_button_visibility()

    def refresh_options_button_visibility(self):
        self.options_btn.setVisible(len(self.config_widget.get_config()) > 0)

    def get_value(self):
        """
        DO NOT PUT A BREAKPOINT IN HERE BECAUSE IT WILL FREEZE YOUR PC (LINUX, PYCHARM & VSCODE) ISSUE WITH PYSIDE COMBOBOX
        """
        from src.utils.helpers import convert_model_json_to_obj
        model_key = self.currentData()
        model_obj = convert_model_json_to_obj(model_key)
        model_obj['model_params'] = self.config_widget.get_config()  #!88!#
        return model_obj

    def set_key(self, key):
        from src.utils.helpers import convert_model_json_to_obj
        model_obj = convert_model_json_to_obj(key)
        super().set_key(json.dumps(model_obj))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.options_btn.move(self.width() - 40, 0)

    # only show options button when the mouse is over the combobox
    def enterEvent(self, event):
        self.options_btn.show()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.refresh_options_button_visibility()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        self.options_btn.show()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if self.options_btn.geometry().contains(event.pos()):
            self.options_btn.show_options()
        else:
            super().mousePressEvent(event)

    def paintEvent(self, event):
        current_item = self.model().item(self.currentIndex())
        if current_item:
            # Check if the selected item's text color is red
            if current_item.foreground().color() == QColor('red'):
                # Set the text color to red when
                # painter = QPainter(self)
                option = QStyleOptionComboBox()
                self.initStyleOption(option)

                painter = QStylePainter(self)
                painter.setPen(QColor('red'))
                painter.drawComplexControl(QStyle.CC_ComboBox, option)

                # Get the text rectangle
                text_rect = self.style().subControlRect(QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxEditField)
                text_rect.adjust(2, 0, -2, 0)  # Adjust the rectangle to provide some padding

                # Draw the text with red color
                current_text = self.currentText()
                painter.drawText(text_rect, Qt.AlignLeft, current_text)
                return

        super().paintEvent(event)

    class OptionsButton(IconButton):
        def __init__(self, parent, *args, **kwargs):
            super().__init__(parent=parent, *args, **kwargs)
            self.clicked.connect(self.show_options)
            self.hide()
            # self.config_widget = CustomDropdown(self)

        def showEvent(self, event):
            super().showEvent(event)
            self.parent.options_btn.move(self.parent.width() - 40, 0)

        def show_options(self):
            if self.parent.config_widget.isVisible():
                self.parent.config_widget.hide()
            else:
                self.parent.config_widget.show()


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
            type_default_roles = {
                'agent': 'assistant',
                'user': 'user',
                'block': 'block',
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
                            'placeholder': 'Class name',
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
        def __init__(self, parent=None):
            super().__init__(parent)
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
            from src.utils.helpers import convert_model_json_to_obj
            from src.system.base import manager

            combo = self.parent.parent
            model_key = combo.currentData()
            model_obj = convert_model_json_to_obj(model_key)

            default = manager.providers.get_model_parameters(model_obj, incl_api_data=False)
            self.load_config(default)

            combo.currentIndexChanged.emit(combo.currentIndex())
            self.load()


class PopupPageParams(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.label_width = 140
        self.schema = []

        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setFixedWidth(300)
        # self.build_schema()

    def showEvent(self, event):
        super().showEvent(event)
        parent = self.parent
        if parent:
            btm_right = parent.rect().bottomRight()
            btm_right_global = parent.mapToGlobal(btm_right)
            btm_right_global_minus_width = btm_right_global - QPoint(self.width(), 0)
            self.move(btm_right_global_minus_width)


def get_widget_value(widget):
    if isinstance(widget, CircularImageLabel):
        return widget.avatar_path
    elif isinstance(widget, ColorPickerWidget):
        return widget.get_color()
    elif isinstance(widget, ModelComboBox):
        d = widget.get_value()
        print('get_widget_value: ', str(d))
        return d
    elif isinstance(widget, MemberPopupButton):
        t = widget.config_widget.get_config()
        return t
    elif isinstance(widget, PluginComboBox):
        return widget.currentData()
    elif isinstance(widget, VenvComboBox):
        return widget.currentData()
    elif isinstance(widget, EnvironmentComboBox):
        return widget.currentData()
    elif isinstance(widget, RoleComboBox):
        return widget.currentData()
    elif isinstance(widget, ModuleComboBox):
        return widget.currentData()
    elif isinstance(widget, QCheckBox):
        return widget.isChecked()
    elif isinstance(widget, QLineEdit):
        return widget.text()
    elif isinstance(widget, QComboBox):
        return widget.currentText()
    elif isinstance(widget, QSpinBox):
        return widget.value()
    elif isinstance(widget, QDoubleSpinBox):
        return widget.value()
    elif isinstance(widget, CTextEdit):
        return widget.toPlainText()
    else:
        raise Exception(f'Widget not implemented: {type(widget)}')


class CVBoxLayout(QVBoxLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)


class CHBoxLayout(QHBoxLayout):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setSpacing(0)


def save_table_config(table_name, item_id, ref_widget, value, key_field='config'):
    value_json = json.dumps(value)

    sql.execute(f"""UPDATE `{table_name}` 
                    SET `{key_field}` = ?
                    WHERE id = ?
                """, (value_json, item_id,))
    if table_name == 'modules':
        metadata = get_metadata(value)
        sql.execute(f"""UPDATE `{table_name}`
                        SET metadata = ?
                        WHERE id = ?
                    """, (json.dumps(metadata), item_id,))

    if ref_widget:
        current_version = getattr(ref_widget, 'current_version', None)
        if current_version:
            # Update the versions dict where the key matches current_version
            sql.execute(f"""
                UPDATE `{table_name}` 
                SET metadata = json_set(
                    metadata,
                    '$.versions.{current_version}',
                    JSON(?)
                )
                WHERE id = ?
            """, (value_json, item_id,))
            # pass

    if hasattr(ref_widget, 'on_edited'):
        ref_widget.on_edited()


def get_selected_pages(widget: Any):
    """
    Recursively get all selected pages within the given widget.

    :param widget: The root widget to start the search from.
    :return: A dictionary with class name paths as keys and selected page names as values.
    """
    result = {}


    def process_widget(w, path):
        if hasattr(w, 'pages'):
            if isinstance(w, ConfigTabs) or isinstance(w, ConfigPages):
                selected_index = w.content.currentIndex()
                if len(w.pages) - 1 < selected_index or (selected_index == -1 and len(w.pages) == 0):
                    return
                selected_page = list(w.pages.keys())[selected_index]
            else:
                return

            result[path] = selected_page

            page_widget = w.pages[selected_page]
            process_widget(page_widget, f"{path}.{selected_page}")
            # for page_name, page_widget in w.pages.items():
            #     process_widget(page_widget, f"{path}.{page_name}")

        elif isinstance(w, ConfigJoined):
            for i, child_widget in enumerate(w.widgets):
                process_widget(child_widget, f"{path}.widget_{i}")

        elif isinstance(w, ConfigDBTree):
            if w.config_widget:
                process_widget(w.config_widget, f"{path}.config_widget")


    process_widget(widget, widget.__class__.__name__)
    return result


def set_selected_pages(widget: Any, selected_pages: Dict[str, str]):
    """
    Set the selected pages within the given widget based on the provided dictionary.

    :param widget: The root widget to start setting pages from.
    :param selected_pages: A dictionary with class name paths as keys and selected page names as values.
    """
    pass
    def process_widget(w, path):
        if path in selected_pages:
            if isinstance(w, (ConfigTabs, ConfigPages)):
                page_name = selected_pages[path]
                if page_name in w.pages:
                    if isinstance(w, ConfigTabs):
                        index = list(w.pages.keys()).index(page_name)
                        w.content.setCurrentIndex(index)
                    elif isinstance(w, ConfigPages):
                        index = list(w.pages.keys()).index(page_name)
                        w.content.setCurrentIndex(index)
                        # Update sidebar button
                        w.settings_sidebar.button_group.button(index).setChecked(True)

        if hasattr(w, 'pages'):
            for page_name, page_widget in w.pages.items():
                process_widget(page_widget, f"{path}.{page_name}")

        elif isinstance(w, ConfigJoined):
            for i, child_widget in enumerate(w.widgets):
                process_widget(child_widget, f"{path}.widget_{i}")

        elif isinstance(w, ConfigDBTree):
            if w.config_widget:
                process_widget(w.config_widget, f"{path}.config_widget")

    process_widget(widget, widget.__class__.__name__)

#
# def get_selected_pages(widget, class_name_path=[]):
#     result = {}
#
#     current_class_name = widget.__class__.__name__
#     current_path = class_name_path + [current_class_name]
#
#     if isinstance(widget, ConfigTabs):
#         tab_widget = widget.content
#         current_tab = tab_widget.currentWidget()
#         current_tab_name = tab_widget.tabText(tab_widget.currentIndex())
#
#     elif isinstance(widget, ConfigPages):
#         selected_page_name = widget.content.currentWidget().objectName()
#         result[".".join(current_path)] = {
#             "class_name_path": current_path,
#             "selected_page_name": selected_page_name
#         }
#
#         # Recursively process the currently selected page
#         selected_widget = widget.pages[selected_page_name]
#         result.update(get_selected_pages(selected_widget, current_path))
#
#     elif isinstance(widget, ConfigJoined):
#         for sub_widget in widget.widgets:
#             result.update(get_selected_pages(sub_widget, current_path))
#
#     elif isinstance(widget, ConfigDBTree):
#         if widget.config_widget:
#             result.update(get_selected_pages(widget.config_widget, current_path))
#
#     # elif isinstance(widget, (ConfigFields, ConfigDBSingle)):
#     #     # These widgets don't have nested pages, so we don't need to process them further
#     #     pass
#     #
#     # else:
#     #     # For any other type of widget, we'll try to process its children
#     #     for child in widget.children():
#     #         if isinstance(child, ConfigWidget):
#     #             result.update(get_selected_pages(child, current_path))
#
#     return result
# # def collect_selected_pages_recursive(widget):
# #     widget_selected_pages = {}  # {page_name_map (list of class names from root): page_widget}
# #     if isinstance(widget, ConfigTabs):
# #         tab_widget = widget.content
# #         current_tab = tab_widget.currentWidget()
# #         current_tab_name = tab_widget.tabText(tab_widget.currentIndex())
# #
# #     elif isinstance(widget, ConfigPages):
# #         pass
# #     elif isinstance(widget, ConfigJoined)
# #
# #     else:
# #         if hasattr(widget, 'widgets'):
# #             for w in widget.widgets:
# #                 collect_selected_pages_recursive(w)
