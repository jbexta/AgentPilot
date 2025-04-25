from src.gui.config import ConfigFields
from src.members.base import Member


class Model(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.receivable_function = self.receive

    # def get_content(self, run_sub_blocks=True):  # todo dupe code 777
    #     from src.system.base import manager
    #     content = self.config.get('data', '')
    #
    #     if run_sub_blocks:
    #         block_type = self.config.get('block_type', 'Text')
    #         nestable_block_types = ['Text', 'Prompt']
    #         if block_type in nestable_block_types:
    #             # # Check for circular references
    #             # if name in visited:
    #             #     raise RecursionError(f"Circular reference detected in blocks: {name}")
    #             # visited.add(name)
    #             content = manager.blocks.format_string(content, ref_workflow=self.workflow)  # additional_blocks=member_blocks_dict)
    #
    #     return content  # manager.blocks.format_string(content, additional_blocks=member_blocks_dict)
    #
    # def default_role(self):  # todo clean
    #     return self.config.get(self.default_role_key, 'block')


class VoiceModel(Model):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def receive(self):
        """The entry response method for the member."""
        # content = self.get_content()
        # yield self.default_role(), content
        # self.workflow.save_message(self.default_role(), content, self.full_member_id())  # , logging_obj)



class VoiceModelSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': 'model_type',
                'type': 'PluginComboBox',
                'plugin_type': 'ModelTypes',
                'allow_none': False,
                'width': 90,
                'default': 'Voice',
                'row_key': 0,
            },
            # {
            #     'text': 'Provider',
            #     'key': 'provider',
            #     'type': 'APIComboBox',
            #     'with_model_kind': 'VOICE',
            #     'allow_none': False,
            #     'width': 90,
            #     'row_key': 0,
            # },
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'model_kind': 'VOICE',
                # 'default': 'mistral/mistral-large-latest',
                'row_key': 0,
            },
            {
                'text': 'Member options',
                'type': 'MemberPopupButton',
                'use_namespace': 'group',
                'member_type': 'voice',
                'label_position': None,
                'default': '',
                'row_key': 0,
            },
        ]


class ImageModelSettings(ConfigFields):
    def __init__(self, parent):
        super().__init__(parent=parent)
        self.schema = [
            {
                'text': 'Type',
                'key': 'model_type',
                'type': 'PluginComboBox',
                'plugin_type': 'ModelTypes',
                'allow_none': False,
                'width': 90,
                'default': 'Voice',
                'row_key': 0,
            },
            # {
            #     'text': 'Provider',
            #     'key': 'provider',
            #     'type': 'APIComboBox',
            #     'with_model_kind': 'IMAGE',
            #     'allow_none': False,
            #     'width': 90,
            #     'row_key': 0,
            # },
            {
                'text': 'Model',
                'type': 'ModelComboBox',
                'model_kind': 'IMAGE',
                # 'default': 'mistral/mistral-large-latest',
                'row_key': 0,
            },
            {
                'text': 'Member options',
                'type': 'MemberPopupButton',
                'use_namespace': 'group',
                'member_type': 'image',
                'label_position': None,
                'default': '',
                'row_key': 0,
            },
        ]