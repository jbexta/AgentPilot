import asyncio

import qasync

from gui import system
from gui.fields.model import ModelComboBox
from gui.gui_utils.helpers import find_main
from gui.widgets.config_db_tree import ConfigDBTree
from gui.widgets.config_fields import ConfigFields
from utils import sql
from utils.helpers import display_message
from utils.media import play_file

# Known cloning-capable TTS models (plus clone-step models) to seed per
# provider. Any other synced model with a text + reference-audio param
# works too — the param roles are inferred from its input_schema.
SEED_VOICE_MODELS = {
    'replicate': [
        'resemble-ai/chatterbox',
        'lucataco/indextts-2',
        'x-lance/f5-tts',
        'jichengdu/fish-speech',
        'lucataco/xtts-v2',
        'afiaka87/tortoise-tts',
        'chenxwh/openvoice',
        'zsxkib/dia',
        'qwen/qwen3-tts',
        'minimax/speech-2.8-hd',
        'minimax/speech-2.8-turbo',
        'minimax/speech-02-hd',
        'minimax/speech-02-turbo',
        'minimax/voice-cloning',
    ],
    'fal': [
        'fal-ai/chatterbox/text-to-speech',
        'fal-ai/index-tts-2/text-to-speech',
        'fal-ai/f5-tts',
        'fal-ai/zonos2',
        'fal-ai/minimax/speech-2.8-hd',
        'fal-ai/minimax/speech-2.8-turbo',
        'fal-ai/minimax/speech-02-hd',
        'fal-ai/minimax/speech-02-turbo',
        'fal-ai/minimax/voice-clone',
    ],
}


class Page_Voice_Settings(ConfigDBTree):
    display_name = 'Voices'
    icon_path = ":/resources/icon-mic.png"
    page_type = 'any'

    def __init__(self, parent):
        super().__init__(
            parent=parent,
            manager='voices',
            query="""
                SELECT
                    name,
                    id,
                    uuid,
                    folder_id
                FROM voices
                ORDER BY pinned DESC, ordr, name COLLATE NOCASE""",
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
                    'text': 'uuid',
                    'key': 'uuid',
                    'type': str,
                    'visible': False,
                },
            ],
            add_item_options={'title': 'Add Voice', 'prompt': 'Enter a name for the voice:'},
            del_item_options={'title': 'Delete Voice', 'prompt': 'Are you sure you want to delete this voice?'},
            readonly=False,
            layout_type='horizontal',
            folder_key='voices',
            config_widget=self.Voice_Config_Widget(parent=self),
            searchable=True,
            extra_buttons=[
                {
                    'text': 'Sync voice models',
                    'icon_path': ':/resources/icon-refresh.png',
                    'target': self.sync_voice_models,
                },
            ],
        )

    def on_edited(self):
        system.manager.voices.load()

    @qasync.asyncSlot()
    async def sync_voice_models(self):
        for provider_name, model_names in SEED_VOICE_MODELS.items():
            provider = system.manager.providers.get(provider_name)
            if provider is None:
                print(f"Skipping voice model sync for '{provider_name}' - provider not found")
                continue
            await provider.sync_models(model_names=model_names, default_kind='AUDIO')
        system.manager.models.load()
        main = find_main()
        for model_combobox in main.findChildren(ModelComboBox):
            model_combobox.load()
        display_message('Voice models synced', 'Success')

    class Voice_Config_Widget(ConfigFields):
        def __init__(self, parent):
            super().__init__(parent=parent)
            self.schema = [
                {
                    'text': 'Model',
                    'key': 'model',
                    'type': 'model',
                    'model_kind': 'AUDIO',
                    'default': '',
                },
                {
                    'text': 'Reference audio',
                    'key': 'reference_audio',
                    'type': 'media_upload',
                    'media_type': 'audio',
                    'default': '',
                    'stretch_x': True,
                },
                {
                    'text': 'Reference text',
                    'key': 'reference_text',
                    'type': str,
                    'num_lines': 3,
                    'default': '',
                    'stretch_x': True,
                },
                {
                    'text': 'Preview text',
                    'key': 'preview_text',
                    'type': str,
                    'num_lines': 2,
                    'default': 'This is a preview of my cloned voice.',
                    'stretch_x': True,
                },
                {
                    'text': 'Preview',
                    'type': 'button',
                    'clicked': '_on_preview_clicked',
                    'label_position': None,
                },
            ]

        def _on_preview_clicked(self):
            asyncio.ensure_future(self._preview())

        async def _preview(self):
            config = self.get_config()
            text = config.get('preview_text', '') or 'This is a preview of my cloned voice.'
            item_id = self.parent.get_selected_item_id()
            voice_name = sql.get_scalar("SELECT name FROM voices WHERE id = ?", (item_id,)) if item_id else None
            try:
                filepath = await system.manager.voices.generate_async(voice_name, text, voice_config=config)
                if filepath:
                    play_file(filepath)
            except Exception as e:
                display_message(str(e), 'Voice preview failed', 'Warning')
