from utils.helpers import BaseManager


class ContactManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='entities',
            folder_key='contacts',
            load_columns=['uuid', 'config'],
            default_fields={
                'kind': 'CONTACT',
                'config': {'_TYPE': 'contact'},
            },
            add_item_options={'title': 'Add Contact', 'prompt': 'Enter a name for the contact:'},
            del_item_options={'title': 'Delete Contact', 'prompt': 'Are you sure you want to delete this contact?'},
            config_is_workflow=True,
        )
