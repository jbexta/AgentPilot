
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_joined import ConfigJoined
from gui.widgets.config_fields import ConfigFields
from gui.widgets.config_table import ConfigTable
from utils.sql import define_table

define_table('youtube_channels')
define_table('youtube_channel_playlists', relations=['channel_id'])
define_table('youtube_channel_videos', relations=['playlist_id', 'channel_id'])


class Page_Youtube(ConfigDBTree):
    display_name = 'Youtube'
    icon_path = ":/resources/icon-image.png"
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            table_name='youtube_channels',
            query="""
                SELECT
                    name,
                    id,
                    config,
                    folder_id
                FROM youtube_channels
                ORDER BY pinned DESC, name COLLATE NOCASE""",
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
                {
                    'text': 'config',
                    'type': str,
                    'visible': False,
                },
            ],
            readonly=False,
            layout_type='horizontal',
            tree_header_hidden=True,
            config_widget=self.Youtuber_Config_Widget(parent=self),
            folder_key='youtubers',
            # support_item_nesting=True,
            searchable=True,
            add_item_options={'title': 'Add channel', 'prompt': 'Enter channel URL or handle (e.g., @username):'},
            del_item_options={'title': 'Delete channel', 'prompt': 'Are you sure you want to delete this channel?'},
        )
        self.splitter.setSizes([400, 1000])

    # def after_init(self):
    #     btn_sync = IconButton(
    #         parent=self.tree_buttons,
    #         icon_name='fa.refresh',
    #         tooltip='Sync Channel',
    #         size=18,
    #     )
    #     btn_sync.clicked.connect(self.sync_channel)
    #     self.tree_buttons.layout.insertWidget(1, btn_sync)

    # def sync_channel(self):
    #     item_id = self.get_selected_item_id()
    #     if not item_id:
    #         display_message("Please select a channel to sync", "warning")
    #         return

    #     self.sync_channel_by_id(item_id, show_message=True)

    # def sync_channel_by_id(self, item_id, show_message=False):
    #     try:
    #         import json
    #         from datetime import datetime

    #         channel_handle = self.db_connector.get_scalar(
    #             f"SELECT name FROM {self.table_name} WHERE id = ?",
    #             (item_id,)
    #         )
    #         channel_url = f'https://www.youtube.com/{channel_handle}'

    #         channel_info = YouTubeManager.get_channel_info(channel_url)
    #         videos = YouTubeManager.get_channel_videos(channel_url, max_results=50)

    #         config = {
    #             'channel_id': channel_info['channel_id'],
    #             'channel_url': channel_info['channel_url'],
    #             'channel_handle': channel_info['channel_handle'],
    #             'thumbnail_url': channel_info['thumbnail_url'],
    #             'description': channel_info['description'],
    #             'subscriber_count': channel_info['subscriber_count'],
    #             'video_count': channel_info['video_count'],
    #             'last_sync': datetime.now().isoformat(),
    #         }

    #         metadata = {
    #             'videos': videos
    #         }

    #         self.db_connector.execute(
    #             f"""UPDATE {self.table_name}
    #                 SET config = ?, metadata = ?
    #                 WHERE id = ?""",
    #             (json.dumps(config), json.dumps(metadata), item_id)
    #         )

    #         self.config_widget.load()
    #         if show_message:
    #             display_message("Channel synced successfully", "info")

    #     except Exception as e:
    #         if show_message:
    #             display_message(f"Failed to sync channel: {str(e)}", "error")

    class Youtuber_Config_Widget(ConfigJoined):
        def __init__(self, parent):
            super().__init__(
                parent=parent,
                layout_type='vertical',
                resizable=True,
            )
            self.widgets = [
                self.Channel_Info_Widget(parent=self),
                self.Videos_Widget(parent=self),
            ]

        class Videos_Widget(ConfigTable):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    table_name='youtube_channel_videos',
                    query="""
                        SELECT
                            name,
                            id,
                            config
                        FROM youtube_channel_videos
                        ORDER BY pinned DESC, name COLLATE NOCASE""",
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
                        {
                            'text': 'config',
                            'type': str,
                            'visible': False,
                        },
                    ],
                    readonly=False,
                    layout_type='horizontal',
                    tree_header_hidden=True,
                    searchable=True,
                )


        class Channel_Info_Widget(ConfigFields):
            def __init__(self, parent):
                super().__init__(
                    parent=parent,
                    schema=[
                        {
                            'text': 'Channel Name',
                            'key': 'name',
                            'type': str,
                            'label_position': 'top',
                        },
                        {
                            'text': 'Channel URL',
                            'key': 'channel_url',
                            'type': str,
                            'label_position': 'top',
                            'conf_namespace': 'config',
                            'read_only': True,
                        },
                        {
                            'text': 'Channel Handle',
                            'key': 'channel_handle',
                            'type': str,
                            'conf_namespace': 'config',
                        },
                        {
                            'text': 'Description',
                            'key': 'description',
                            'type': str,
                            'num_lines': 3,
                            'label_position': 'top',
                            'conf_namespace': 'config',
                            'read_only': True,
                        },
                        {
                            'text': 'Subscribers',
                            'key': 'subscriber_count',
                            'type': int,
                            'conf_namespace': 'config',
                            'read_only': True,
                        },
                        {
                            'text': 'Total Videos',
                            'key': 'video_count',
                            'type': int,
                            'conf_namespace': 'config',
                            'read_only': True,
                        },
                        {
                            'text': 'Last Sync',
                            'key': 'last_sync',
                            'type': str,
                            'conf_namespace': 'config',
                            'read_only': True,
                        },
                        {
                            'text': 'Auto Sync',
                            'key': 'auto_sync',
                            'type': bool,
                            'conf_namespace': 'config',
                        },
                        {
                            'text': 'Sync Frequency (hours)',
                            'key': 'sync_frequency',
                            'type': int,
                            'conf_namespace': 'config',
                            'minimum': 1,
                            'maximum': 168,
                            'default': 24,
                        },
                    ],
                    auto_label_width=True,
                )
