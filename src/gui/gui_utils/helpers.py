import json
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QPainter, QPixmap, Qt
from PySide6.QtWidgets import (
    QAbstractButton, QLabel, QMessageBox, QTabWidget, QTreeWidget, QWidget,
)

from gui import system
from utils import sql
from utils.helpers import (
    TRANSLATIONS, convert_to_safe_case, display_message, get_metadata,
    load_language, tr,
)


_main_window = None


def find_main():
    from PySide6.QtWidgets import QApplication

    global _main_window
    if _main_window is not None:
        return _main_window

    app = QApplication.instance()
    if app:
        for widget in app.topLevelWidgets():
            if widget.__class__.__name__ == 'Main':
                _main_window = widget
                return widget
    return None


def record_page_load_error(module_name):
    """Store the current exception's traceback so the test runner can
    report why a page failed to construct."""
    import traceback
    main = find_main()
    if main is None:
        return
    if getattr(main, '_page_load_errors', None) is None:
        main._page_load_errors = {}
    main._page_load_errors[module_name] = traceback.format_exc()


def find_chat_widget(widget):
    from plugins.workflows.widgets.chat_widget import ChattableWorkflowWidget
    # is instance ChattableWorkflowWidget
    if isinstance(widget, ChattableWorkflowWidget):
        return widget
    if not hasattr(widget, 'parent'):
        return None
    return find_chat_widget(widget.parent)


def find_workflow_widget(widget):
    from plugins.workflows.widgets.workflow_settings import WorkflowSettings
    if isinstance(widget, WorkflowSettings):
        return widget
    if hasattr(widget, 'workflow_settings'):
        return widget.workflow_settings
    if not hasattr(widget, 'parent'):
        return None
    return find_workflow_widget(widget.parent)


def find_attribute(widget, attribute, default=None):
    if hasattr(widget, attribute):
        return getattr(widget, attribute)
    if not hasattr(widget, 'parent'):
        return default
    return find_attribute(widget.parent, attribute)


def find_ancestor_tree_widget(widget):
    from gui.widgets.config_db_tree import ConfigDBTree
    if isinstance(widget, ConfigDBTree):
        return widget
    if not hasattr(widget, 'parent'):
        return None
    return find_ancestor_tree_widget(widget.parent)


def find_ancestor_tree_item_id(widget):
    from gui.widgets.config_db_tree import ConfigDBTree
    if isinstance(widget, ConfigDBTree):
        return widget.get_selected_item_id()
    # A host with no tree (e.g. the PageEditor popup) pins the item id here
    item_id = getattr(widget, 'tree_item_id', None)
    if item_id is not None:
        return item_id
    if not hasattr(widget, 'parent'):
        return None
    return find_ancestor_tree_item_id(widget.parent)


def get_member_settings_class(member_type):
    member_class = system.manager.modules.get_module_class('Members', module_name=member_type)

    if not member_class:
        display_message(
            message=f"Member module '{member_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return None

    member_settings_module = getattr(member_class, '_ap_settings_module', None)
    if not member_settings_module:
        return None

    member_settings_class = system.manager.modules.get_module_class('Widgets', module_name=member_settings_module)
    if not member_settings_class:
        display_message(
            message=f"Member settings module '{member_settings_module}' not found.",
            icon=QMessageBox.Warning,
        )
        return None

    return member_settings_class


def get_project_type_class(project_type):
    project_type_class = system.manager.modules.get_module_class('Project_types', module_name=project_type)
    if not project_type_class:
        display_message(
            message=f"Project type module '{project_type}' not found.",
            icon=QMessageBox.Warning,
        )
        return None

    return project_type_class


def colorize_pixmap(pixmap, opacity=1.0, color=None):
    if pixmap.isNull():
        return pixmap

    colored_pixmap = QPixmap(pixmap.size())
    colored_pixmap.fill(Qt.transparent)

    painter = QPainter()
    if not painter.begin(colored_pixmap):
        return pixmap  # Return original pixmap if painting fails
    painter.setCompositionMode(QPainter.CompositionMode_Source)
    painter.drawPixmap(0, 0, pixmap)
    painter.setOpacity(opacity)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)

    from gui.style import TEXT_COLOR as current_text_color
    painter.fillRect(colored_pixmap.rect(), current_text_color if not color else color)
    painter.end()

    return colored_pixmap


def clear_layout(layout, skip_count=0):
    """Clear all layouts and widgets from the given layout"""
    from gui.gui_utils.breadcrumb_widget import BreadcrumbWidget
    while layout.count() > skip_count:
        item = layout.itemAt(skip_count)
        widget = item.widget()
        if isinstance(widget, BreadcrumbWidget):
            skip_count += 1
            continue
        item = layout.takeAt(skip_count)
        if widget is not None:
            widget.deleteLater()
        else:
            child_layout = item.layout()
            if child_layout is not None:
                clear_layout(child_layout)


def str_presenter(dumper, data):
    """YAML representer that uses literal block style for multiline strings."""
    if isinstance(data, str) and '\n' in data:
        data = '\n'.join([line.rstrip() for line in data.split('\n')])
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


def bake_table_item(table_name, item_id):
    """Bake a table row to disk and set ``baked = 1``.

    ``modules`` rows are written as ``.py`` via the matching type
    controller; every other table is written as YAML to
    ``src/utils/baked/<table_name>/``. No dialogs or confirmations:
    callers that need user interaction should layer those on top.

    Returns the written path, or ``None`` if the row could not be
    baked (frozen binary, missing item, missing uuid column, etc.).
    """
    if getattr(sys, 'frozen', False):
        return None
    if not item_id:
        return None
    if table_name == 'modules':
        return _bake_module_row(item_id)
    return _bake_yaml_row(table_name, item_id)


def _bake_module_row(item_id):
    row = sql.get_results(
        "SELECT name, folder_id FROM modules WHERE id = ?",
        (item_id,), return_type='tuple',
    )
    if not row:
        return None
    name, folder_id = row
    folder_name = sql.get_scalar(
        "SELECT name FROM folders WHERE id = ?", (folder_id,)
    ) if folder_id else None
    if not folder_name:
        return None
    controller = system.manager.modules.type_controllers.get(
        folder_name.lower().replace(' ', '_')
    )
    if controller is None:
        return None
    return controller.bake_module(name)


def _bake_yaml_row(table_name, item_id):
    import yaml
    from utils.filesystem import get_application_path, get_all_baked_items

    bake_columns = ['uuid', 'name', 'config', 'kind', 'parent_id']
    if table_name == 'folders':
        bake_columns += ['type']

    existing_cols = [
        col for col in bake_columns
        if sql.get_scalar(
            f"SELECT COUNT(*) FROM pragma_table_info('{table_name}') WHERE name = ?",
            (col,)
        ) > 0
    ]
    if 'uuid' not in existing_cols:
        return None

    row = sql.get_results(
        f"SELECT {', '.join(existing_cols)} FROM `{table_name}` WHERE id = ?",
        (item_id,), return_type='tuple',
    )
    if not row:
        return None
    item_tuple = row
    uuid, name, config = item_tuple[:3]

    existing_baked = get_all_baked_items(table_name)
    existing_path = next(
        (p for p, baked_json in existing_baked.items()
         if baked_json.get('uuid') == uuid),
        None,
    )
    if existing_path:
        baked_dir_path = str(existing_path.parent)
    else:
        app_path = get_application_path()
        baked_dir_path = os.path.join(app_path, 'src', 'utils', 'baked', table_name)
        os.makedirs(baked_dir_path, exist_ok=True)

    short_uuid = f'_{uuid[:4]}'
    safe_filename = f"{convert_to_safe_case(name) + short_uuid}.yaml"
    safe_filepath = os.path.join(baked_dir_path, safe_filename)

    # If a previously-baked file exists for this uuid under a different
    # name, rename it rather than leaving an orphan.
    if existing_path and str(existing_path) != safe_filepath:
        os.rename(existing_path, safe_filepath)

    wrapped_config = {
        col_name: item_tuple[i] for i, col_name in enumerate(existing_cols)
    }
    wrapped_config['config'] = json.loads(config)

    parent_id = wrapped_config.pop('parent_id', None)
    if parent_id:
        parent_uuid = sql.get_scalar(
            f"SELECT uuid FROM `{table_name}` WHERE id = ?", (parent_id,)
        )
        if parent_uuid:
            wrapped_config['parent_uuid'] = parent_uuid

    folder_id = sql.get_scalar(
        f"SELECT folder_id FROM `{table_name}` WHERE id = ?", (item_id,)
    )
    if folder_id:
        wrapped_config['folder_path'] = _folder_path_from_id(folder_id)

    class CustomDumper(yaml.SafeDumper):
        pass
    CustomDumper.add_representer(str, str_presenter)

    with open(safe_filepath, 'w', encoding='utf-8') as f:
        yaml.dump(
            wrapped_config, f,
            Dumper=CustomDumper,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=1000,
            line_break='\n',
        )

    sql.execute(
        f"UPDATE `{table_name}` SET baked = 1 WHERE id = ?", (item_id,)
    )
    return safe_filepath


def _folder_path_from_id(folder_id):
    """Resolve a folder id to a slash-joined folder path."""
    parts = []
    current = folder_id
    while current:
        row = sql.get_results(
            "SELECT name, parent_id FROM folders WHERE id = ?",
            (current,), return_type='tuple',
        )
        if not row:
            break
        name, parent_id = row
        parts.append(name)
        current = parent_id
    return '/'.join(reversed(parts))


def auto_bake_table_item(table_name, item_id):
    if not system.manager.config.get('system.auto_bake', False):
        return
    baked_in_table = sql.get_scalar(f"SELECT COUNT(*) FROM pragma_table_info('{table_name}') WHERE `name` = 'baked'") > 0
    if not baked_in_table:
        return
    if sql.get_scalar(f"SELECT baked FROM {table_name} WHERE id = ?", (item_id,)) != 1:
        return

    old_name = sql.get_scalar(f"SELECT name FROM {table_name} WHERE id = ?", (item_id,))
    bake_table_item(table_name, item_id)
    config = sql.get_scalar(f"SELECT config FROM {table_name} WHERE id = ?", (item_id,), load_json=True)
    name = config.get('name', None)
    if not name:
        name = sql.get_scalar(f"SELECT name FROM {table_name} WHERE id = ?", (item_id,))
    if old_name != name:  # todo dedupe
        from gui.pages.modules import get_module_abs_path
        old_file_path = get_module_abs_path(item_id, module_name=old_name)
        if old_file_path and os.path.exists(old_file_path):
            os.remove(old_file_path)


def save_table_config(table_name, item_id, value, ref_widget=None, key_field='config'):
    # before_value = sql.get_scalar(f"SELECT `{key_field}` FROM `{table_name}` WHERE id = ?", (item_id,))
    sql.execute(f"""UPDATE `{table_name}`
                    SET `{key_field}` = ?
                    WHERE id = ?
                """, (value, item_id,))
    # if before_value != value:
    #     import time
    #     from core.actions import base as undo_history
    #     from core.actions.config_save import ConfigSaveAction
    #     undo_history.record(ConfigSaveAction(
    #         table=table_name, item_id=item_id, key_field=key_field,
    #         before=before_value, after=value, ts=time.time(),
    #     ))
    if table_name == 'modules':
        metadata = get_metadata(json.loads(value))
        sql.execute(f"""UPDATE `{table_name}`
                        SET metadata = ?
                        WHERE id = ?
                    """, (json.dumps(metadata), item_id,))

    auto_bake_table_item(table_name, item_id)

    if ref_widget:
        if hasattr(ref_widget, 'on_edited'):
            ref_widget.on_edited()


def get_field_widget(col_schema, parent=None):
    column_type = col_schema.get('type', 'text')
    column_key = col_schema.get('key', col_schema.get('name', 'unknown'))
    type_map = {  # todo temp map
        str: 'text',
        int: 'integer',
        float: 'float',
        bool: 'boolean',
    }
    if isinstance(column_type, (tuple, list)):
        col_schema['items'] = tuple(column_type)
        if column_type and not isinstance(column_type[0], str):
            col_schema.setdefault('value_type', type(column_type[0]))
        column_type = 'combo'
    elif column_type in type_map:
        column_type = type_map[column_type]

    if column_type == 'member_type_menu':
        pass
    widget_class = system.manager.modules.get_module_class(
        module_type='Fields',
        module_name=column_type,
    )
    widget = widget_class(parent=parent, **col_schema) if widget_class else None
    if not widget:
        print(
            f'Widget type {column_type} not found in modules. Skipping field: {column_key}')
        return None
    return widget


def set_widget_value(widget, value):
    try:
        if hasattr(widget, 'set_value'):
            widget.set_value(value)
    except Exception as e:
        import traceback
        traceback.print_exc()
        display_message(
            f'Error setting value for field {str(widget)}: {type(e).__name__}: {e}',
            icon=QMessageBox.Warning,
        )


def get_selected_pages(widget, incl_objects=False, stop_at_tree=False):  # todo temp stop
    """
    Recursively get all selected pages within the given widget.

    :param widget: The root widget to start the search from.
    :return: A dictionary with class name paths as keys and selected page names as values.
    """
    from gui.widgets.config_db_tree import ConfigDBTree
    from gui.widgets.config_joined import ConfigJoined
    from gui.widgets.config_pages import ConfigPages
    from gui.widgets.config_table import ConfigTable
    from gui.widgets.config_tabs import ConfigTabs

    result = {}

    def process_widget(w, path):
        if hasattr(w, 'get_page_state'):
            if stop_at_tree:
                return
            state = w.get_page_state()
            if state:
                result[path] = state if not incl_objects else (state, w)
            return

        if hasattr(w, 'pages'):
            if isinstance(w, ConfigTabs) or isinstance(w, ConfigPages):
                selected_index = w.content.currentIndex()
                if len(w.pages) - 1 < selected_index or (selected_index == -1 and len(w.pages) == 0):
                    return
                selected_page_name = list(w.pages.keys())[selected_index]
                selected_page = list(w.pages.values())[selected_index]
            else:
                return

            selected_page = w.pages[selected_page_name]
            result[path] = selected_page_name if not incl_objects else (selected_page_name, selected_page)

            process_widget(selected_page, f"{path}.{selected_page_name}")

        elif hasattr(w, 'widgets'):
            for i, child_widget in enumerate(w.widgets):
                process_widget(child_widget, f"{path}.widget_{i}")

        elif hasattr(w, 'config_widget'):
            if stop_at_tree:
                return
            if isinstance(w, (ConfigDBTree, ConfigTable)):
                item_id = w.get_selected_item_id()
                if item_id is not None:
                    result[path] = item_id if not incl_objects else (item_id, w)
            if w.config_widget:
                process_widget(w.config_widget, f"{path}.config_widget")

    process_widget(widget, widget.__class__.__name__)
    return result


def set_selected_pages(widget, selected_pages):
    """
    Set the selected pages within the given widget based on the provided dictionary.

    :param widget: The root widget to start setting pages from.
    :param selected_pages: A dictionary with class name paths as keys and selected page names as values.
    """
    from gui.widgets.config_db_tree import ConfigDBTree
    from gui.widgets.config_joined import ConfigJoined
    from gui.widgets.config_pages import ConfigPages
    from gui.widgets.config_table import ConfigTable
    from gui.widgets.config_tabs import ConfigTabs

    def process_widget(w, path):
        if hasattr(w, 'set_page_state'):
            if path in selected_pages:
                w.set_page_state(selected_pages[path])
            return

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
                        if w.bottom_to_top:
                            index = len(w.pages) - 1 - index
                        w.settings_sidebar.button_group.button(index).setChecked(True)
                    # elif isinstance(w, FileTree):
                    #     w.navigate_to(Path(selected_pages[path]), update_page_path=False)

        if hasattr(w, 'pages'):
            for page_name, page_widget in w.pages.items():
                process_widget(page_widget, f"{path}.{page_name}")

        elif hasattr(w, 'widgets'):
            for i, child_widget in enumerate(w.widgets):
                process_widget(child_widget, f"{path}.widget_{i}")

        elif hasattr(w, 'config_widget'):
            if path in selected_pages:
                if isinstance(w, ConfigDBTree):
                    w.load(select_id=selected_pages[path])
                elif isinstance(w, ConfigTable):
                    w.load()
                    w.select_item_by_id(selected_pages[path])
            if w.config_widget:
                process_widget(w.config_widget, f"{path}.config_widget")

    process_widget(widget, widget.__class__.__name__)


def retranslate(widget, language):
    """Switch the text of `widget` and its children to `language`"""
    english = {v: k for k, v in TRANSLATIONS.items()}
    load_language(language)

    def translate(text):
        return tr(english.get(text, text))

    for w in widget.findChildren(QWidget):
        if w.toolTip():
            w.setToolTip(translate(w.toolTip()))
        if isinstance(w, (QLabel, QAbstractButton)) and w.text():
            w.setText(translate(w.text()))
        elif isinstance(w, QTabWidget):
            for i in range(w.count()):
                w.setTabText(i, translate(w.tabText(i)))
        elif isinstance(w, QTreeWidget):
            header = w.headerItem()
            for i in range(header.columnCount()):
                header.setText(i, translate(header.text(i)))


def safe_single_shot(msec, callback):
    """Wrapper around QTimer.singleShot that catches exceptions"""
    def safe_callback():
        try:
            callback()
        except Exception as e:
            if 'already deleted' in str(e):
                return
            print(f"Timer callback error: {e}")

    QTimer.singleShot(msec, safe_callback)


def set_style_property(widget, name, value):
    """Set a dynamic property used by a style.py selector and re-apply
    the stylesheet to the widget and its children."""
    widget.setProperty(name, value)
    for w in (widget, *widget.findChildren(QWidget)):
        w.style().unpolish(w)
        w.style().polish(w)
