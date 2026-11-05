from gui.gui_utils.custom_menu import CustomMenu


class TreeButtons(CustomMenu):
    def __init__(self, parent, extra_buttons=[]):
        super().__init__(parent)
        self.schema = [
            {
                'text': 'Add',
                'icon_path': ':/resources/icon-new.png',
                'target': parent.add_item,
            },
            {
                'text': 'Delete',
                'icon_path': ':/resources/icon-minus.png',
                'target': parent.delete_item,
            },
            {
                'text': 'New Folder',
                'icon_path': ':/resources/icon-new-folder.png',
                'visibility_predicate': lambda: getattr(parent, 'folder_key', None) is not None,
                # lambda: triggered(bool) would otherwise pass `checked` as the name
                'target': lambda: parent.add_folder(),
            },
            {
                'text': 'Search',
                'icon_path': ':/resources/icon-search.png',
                'visibility_predicate': lambda: getattr(parent, 'searchable', False),
                'target': lambda checked: parent.toggle_search(checked),
                'checkable': True,
            },
            # {
            #     'text': 'Search',
            #     'icon_path': ':/resources/icon-search.png',
            #     'visibility_predicate': lambda: getattr(parent, 'searchable', False),
            #     'target': parent.search_rows,
            # },
        ]
        self.schema.extend(extra_buttons)

        self.create_toolbar(parent)
