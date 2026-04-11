"""
Member type menu field widget for member type selection.

This module provides a MemberTypeMenu field widget that extends IconButton to create
a button that opens a dropdown menu for member type selection. It provides a simple
interface for selecting different member types through a contextual menu.
"""

import json
from functools import partial
from PySide6.QtWidgets import QMenu
from PySide6.QtGui import QAction, QFont
from PySide6.QtCore import Qt

from gui import system
from gui.util import IconButton
from plugins.workflows.widgets.workflow_settings import WorkflowSettings


class MemberTypeMenu(IconButton):  # todo dedupe
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent=parent,
            icon_path=':/resources/icon-refresh.png',
            size=24,
        )
        self.is_member_header = getattr(parent, 'is_member_header', True)
        self.current_value = None
        
        self.menu = QMenu(self)
        
        self.clicked.connect(self.show_menu)

    def select_item(self, value):
        """Handle menu item selection"""
        self.current_value = value
        self.update_config()

    def get_value(self):
        """Get the currently selected value"""
        return self.current_value

    def set_value(self, value):
        self.current_value = value

    def set_member_type(self, value):
        current_name = self.parent.config.get('name', 'Agent')
        get_default = lambda v: getattr(system.manager.modules.get_module_class('Members', v), 'default_name', v.replace('_', ' ').title())
        new_name = get_default(value) if get_default(self.current_value) == current_name else None

        self.current_value = value

        # rebuild the member
        is_in_mini_view = self.parent.parent.parent.__class__.__name__ != 'MemberProxy'
        if is_in_mini_view:
            if self.is_member_header:
                workflow_settings = self.parent.parent.parent.parent
                member_config_widget = self.parent.parent.parent
                member_id = getattr(member_config_widget.config_widget, 'member_id', None)
                if member_id and member_id in workflow_settings.members_in_view:
                    workflow_settings.members_in_view[member_id].member_config['_TYPE'] = value
                    if new_name:
                        workflow_settings.members_in_view[member_id].member_config['name'] = new_name
            else:  
                # is workflow header
                # _TYPE inserted here
                workflow_settings = self.parent.parent.parent
                # user_members = [m for m in workflow_settings.members_in_view.values() if m.member_config.get('_TYPE', 'agent') == 'user']
                # non_user_members = [m for m in workflow_settings.members_in_view.values() if not m.member_config.get('_TYPE', 'agent') == 'user']
                # ORDER BY loc_x
                user_members = sorted(workflow_settings.members_in_view.values(), key=lambda m: m.x())
                user_members = [m for m in user_members if m.member_config.get('_TYPE', 'agent') == 'user']
                non_user_members = sorted(workflow_settings.members_in_view.values(), key=lambda m: m.x())
                non_user_members = [m for m in non_user_members if m.member_config.get('_TYPE', 'agent') != 'user']

                if len(non_user_members) > 1:
                    return
                elif len(non_user_members) == 1:
                    member_id_to_update = non_user_members[0].id
                elif len(user_members) > 0:
                    member_id_to_update = user_members[-1].id
                else:
                    return

                # member_id_to_update = non_user_members[0].id # next((k for k, m in workflow_settings.members_in_view.items() if not m.member_config.get('_TYPE', 'agent') == 'user'), None)
                workflow_settings.members_in_view[member_id_to_update].member_config['_TYPE'] = value
                if new_name:
                    workflow_settings.members_in_view[member_id_to_update].member_config['name'] = new_name
        else:  
            # is in member proxy
            member_proxy = self.parent.parent.parent
            draggable_member = member_proxy.parent
            workflow_settings = member_proxy.workflow_settings
            draggable_member.member_config['_TYPE'] = value
            if new_name:
                draggable_member.member_config['name'] = new_name

        workflow_settings.update_config()
        workflow_settings.load()

    def add_contxt_menu_header(self, menu, title):  # todo dedupe
        section = QAction(title, self)
        section.setEnabled(False)
        font = QFont()
        font.setPointSize(8)
        section.setFont(font)
        menu.addAction(section)

    def update_config(self):
        """Implements same method as ConfigWidget, as a workaround to avoid inheriting from it"""
        if hasattr(self.parent, 'update_config'):
            self.parent.update_config()

        if hasattr(self, 'save_config'):
            self.save_config()

    def open_library(self):
        """Open the LibraryDialog to choose a saved item."""
        from gui.util import LibraryDialog
        member_modules = system.manager.modules.get_modules_in_folder(
            module_type='Members',
            fetch_keys=('name', 'kind_folder',)
        )
        kind = next(
            (kf for n, kf in member_modules
             if n == self.current_value),
            None,
        )
        dialog = LibraryDialog(
            parent=self,
            callback=self.on_library_selected,
            kind=kind,
        )
        dialog.open()

    def on_library_selected(self, item, link=False):
        """Replace current member's config with selected library item."""
        item_config = json.loads(
            item.data(0, Qt.UserRole).get('config', '{}')
        )

        draggable_member = None
        is_in_mini_view = (
            self.parent.parent.parent.__class__.__name__
            != 'MemberProxy'
        )
        if is_in_mini_view:
            if self.is_member_header:
                workflow_settings = self.parent.parent.parent.parent
                member_config_widget = self.parent.parent.parent
                member_id = getattr(
                    member_config_widget.config_widget,
                    'member_id', None,
                )
                if (member_id
                        and member_id in workflow_settings.members_in_view):
                    draggable_member = (
                        workflow_settings.members_in_view[member_id]
                    )
                    draggable_member.member_config = item_config
            else:
                # Workflow header — replace the entire workflow
                workflow_settings = self.parent.parent.parent
                from utils.helpers import merge_config_into_workflow_config
                new_config = merge_config_into_workflow_config(item_config)

                if not link:
                    for m in new_config.get('members', []):
                        m.pop('linked_id', None)

                if link:
                    from utils.helpers import (
                        has_circular_link, resolve_linked_config,
                    )
                    from gui.util import display_message
                    source_table = item.data(
                        0, Qt.UserRole
                    ).get('table')
                    source_uuid = item.data(
                        0, Qt.UserRole
                    ).get('id')
                    linked_id = (
                        f'{source_table}.{source_uuid}'
                        if source_table and source_uuid
                        else None
                    )
                    if linked_id:
                        if has_circular_link(linked_id):
                            display_message(
                                message='Cannot link: circular reference.',
                                icon='Warning',
                            )
                            return
                        new_config['linked_id'] = linked_id
                workflow_settings.load_config(new_config)
                self.current_value = item_config.get(
                    '_TYPE', self.current_value
                )
                workflow_settings.load()
                workflow_settings.update_config()
                return
        else:
            member_proxy = self.parent.parent.parent
            draggable_member = member_proxy.parent
            workflow_settings = member_proxy.workflow_settings
            draggable_member.member_config = item_config

        if link and draggable_member is not None:
            from utils.helpers import has_circular_link, resolve_linked_config
            from gui.util import display_message

            members = item_config.get('members', [])
            linked_id = None
            for m in members:
                if m.get('linked_id'):
                    linked_id = m['linked_id']
                    break
            if not linked_id:
                linked_id = item_config.get('linked_id')
            if linked_id:
                existing_chain = set()
                for m_id, m in workflow_settings.members_in_view.items():
                    if (m.linked_id
                            and m.id != draggable_member.id):
                        existing_chain.add(m.linked_id)
                if has_circular_link(
                    linked_id, existing_chain=existing_chain
                ):
                    display_message(
                        message='Cannot link: circular reference.',
                        icon='Warning',
                    )
                else:
                    resolved = resolve_linked_config(linked_id)
                    if resolved is not None:
                        draggable_member.member_config.clear()
                        draggable_member.member_config.update(resolved)
                    draggable_member.linked_id = linked_id

        self.current_value = item_config.get(
            '_TYPE', self.current_value
        )
        workflow_settings.update_config()
        workflow_settings.load()

    def show_menu(self):
        """Show the dropdown menu"""
        # clear the menu
        self.menu.clear()

        self.menu.addAction('Choose from library', self.open_library)
        self.menu.addSeparator()

        # populate the menu
        member_modules = system.manager.modules.get_modules_in_folder(
            module_type='Members',
            fetch_keys=('name', 'kind_folder', 'class',)
        )

        value_kind = next((kind_folder for name, kind_folder, module_class in member_modules if name == self.current_value), None)

        type_dict = {}
        for module_name, kind_folder, module_class in member_modules:
            if kind_folder not in type_dict:
                type_dict[kind_folder] = []
            type_dict[kind_folder].append((module_name, module_class))

        for module_kind, kind_modules in type_dict.items():
            if not module_kind:
                continue
            if value_kind:
                if value_kind != module_kind:
                    continue
            else:
                self.add_contxt_menu_header(self.menu, module_kind.capitalize())

            for module_name, module_class in kind_modules:
                if value_kind and module_name == self.current_value:
                    continue
                default_name = getattr(module_class, 'default_name', module_name.capitalize())
                workflow_insert_mode = getattr(module_class, 'workflow_insert_mode', None)
                # if workflow_insert_mode == 'single':
                self.menu.addAction(module_name.capitalize(), partial(
                    self.set_member_type,
                    module_name
                ))
                # elif workflow_insert_mode == 'list':
                #     self.menu.addAction(module_name.capitalize(), partial(self.choose_member, 'AGENT'))
                # else:
                #     continue

        # set_kind = next((kind_folder for name, kind_folder in module_type_modules if name == value), None)

        # for module_name, module_class, baked, kind_folder in module_type_modules:

        button_rect = self.rect()
        menu_pos = self.mapToGlobal(button_rect.bottomLeft())
        self.menu.exec(menu_pos)