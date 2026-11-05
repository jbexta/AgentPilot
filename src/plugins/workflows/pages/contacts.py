import asyncio
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from gui import system
from utils import sql
from utils.helpers import display_message
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from plugins.workflows.widgets.workflow_settings import WorkflowSettings


class Page_Contacts(ConfigDBTree):
    display_name = 'Contacts'
    icon_path = ":/resources/icon-user.png"
    page_type = 'main'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='contacts',
            query="""
                SELECT
                    name,
                    id,
                    config,
                    uuid,
                    folder_id
                FROM entities
                WHERE kind = :kind
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
            schema=[
                {
                    'text': 'Name',
                    'key': 'name',
                    'type': str,
                    'stretch': True,
                    'image_key': 'config',
                },
                {
                    'text': 'id',
                    'key': 'id',
                    'type': int,
                    'visible': False,
                },
                {
                    'text': 'config',
                    'type': str,
                    'visible': False,
                },
                {
                    'text': 'uuid',
                    'key': 'uuid',
                    'type': str,
                    'visible': False,
                },
            ],
            layout_type='horizontal',
            config_widget=self.Contact_Config_Widget(parent=self),
            tree_header_hidden=True,
            readonly=True,
            searchable=True,
            kind='CONTACT',
            folder_key='contacts',
            extra_buttons=[
                {
                    'text': 'Call',
                    'icon_path': ':/resources/icon-call.png',
                    'target': self.call_contact,
                },
                {
                    'text': 'Call options',
                    'icon_path': ':/resources/icon-call-as.png',
                    'target': self.call_options,
                },
            ],
        )
        self.splitter.setSizes([400, 1000])

    def on_context_menu(self, menu):
        menu.addSeparator()
        menu.addAction('Call').triggered.connect(self.call_contact)
        menu.addAction('Call options').triggered.connect(self.call_options)

    def selected_contact(self):
        """Returns (name, phone_number) of the selected contact, or None."""
        item_id = self.tree.get_selected_item_id()
        if item_id is None:
            return None
        name, config = sql.get_results(
            "SELECT name, config FROM entities WHERE id = ?", (item_id,), return_type='tuple')
        config = json.loads(config)
        members = config.get('members', [])
        member_config = members[0].get('config', {}) if members else config
        return name, member_config.get('phone_number', '')

    @staticmethod
    def telephony():
        telephony = getattr(system.manager, 'telephony', None)
        if telephony is None:
            display_message('The telephony plugin is not loaded.', icon=QMessageBox.Warning)
        return telephony

    def call_contact(self):
        contact = self.selected_contact()
        if not contact:
            return
        name, phone_number = contact
        if not phone_number:
            display_message(f'{name} has no phone number', icon=QMessageBox.Warning)
            return
        telephony = self.telephony()
        if telephony:
            telephony.start_call(phone_number)

    def call_options(self):
        if self.telephony():
            self.call_options_dialog = self.CallOptions(parent=self)
            self.call_options_dialog.show()

    class CallOptions(ConfigFields):
        """Saved in the telephony state and used by every Call."""
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.propagate_config = False
            self.setWindowFlags(Qt.Dialog)
            self.setWindowTitle('Call options')
            self.setMinimumWidth(350)
            self.auto_label_width = True
            self.schema = [
                {
                    'text': 'Call from',
                    'type': 'combo',
                    'items': [],
                    'width': 200,
                    'default': '',
                    'tooltip': 'The numbers the provider account owns or has verified.',
                },
                {
                    'text': 'Live Agent',
                    'key': 'call_agent',
                    'type': 'entity',
                    'entity_table': 'entities',
                    'default': '',
                },
            ]
            self.build_schema()
            self.load_config()
            self.load()
            asyncio.ensure_future(self.load_caller_ids())

        def load_config(self, json_config=None):
            super().load_config(system.manager.telephony.state())

        def save_config(self):
            system.manager.telephony.save_state(**self.get_config())

        async def load_caller_ids(self):
            self.call_from_wgt.items = await system.manager.telephony.caller_ids()
            self.call_from_wgt.load()
            self.load()

    class Contact_Config_Widget(WorkflowSettings):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                kind='CONTACT',
            )
