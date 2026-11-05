import json

from utils import sql
from utils.helpers import BaseManager, convert_model_json_to_obj
from utils.media import play_file
from plugins.workflows.utils.workflows import compute_workflow_async


# Param roles are inferred from the model's synced input_schema; keys are
# tried in order. 'ref_audio' falls back to any media_upload field with a
# voice-ish key name, so unknown models from any provider work automatically.
TEXT_PARAM_KEYS = ['gen_text', 'text', 'prompt', 'script']
REF_AUDIO_PARAM_KEYS = [
    'audio_prompt', 'speaker_audio', 'ref_audio', 'ref_audio_url',
    'reference_audio', 'reference_audio_url', 'speaker_reference',
    'voice_file', 'custom_voice', 'audio_url', 'speaker', 'audio',
]
REF_TEXT_PARAM_KEYS = ['ref_text', 'reference_text', 'text_reference', 'audio_prompt_text', 'transcript']

# Per-model corrections where inference isn't enough. Param keys may be
# dotted paths for nested payloads. 'extra' holds fixed params required to
# enter voice-clone mode. Models that clone in a separate step declare
# 'clone_model' / 'clone_input' / 'clone_output' and a 'voice_id' param.
REPLICATE_MINIMAX = {'voice_id': 'voice_id', 'clone_model': 'minimax/voice-cloning', 'clone_input': 'voice_file', 'clone_output': 'voice_id'}
FAL_MINIMAX = {'voice_id': 'voice_setting.voice_id', 'clone_model': 'fal-ai/minimax/voice-clone', 'clone_input': 'audio_url', 'clone_output': 'custom_voice_id'}

VOICE_MODEL_OVERRIDES = {
    'replicate': {
        'afiaka87/tortoise-tts': {'ref_audio': 'custom_voice', 'extra': {'voice_a': 'custom_voice'}},
        'qwen/qwen3-tts': {'extra': {'mode': 'voice_clone'}},
        'minimax/speech-2.8-hd': REPLICATE_MINIMAX,
        'minimax/speech-2.8-turbo': REPLICATE_MINIMAX,
        'minimax/speech-02-hd': REPLICATE_MINIMAX,
        'minimax/speech-02-turbo': REPLICATE_MINIMAX,
    },
    'fal': {
        'fal-ai/f5-tts': {'extra': {'model_type': 'F5-TTS'}},
        'fal-ai/minimax/speech-2.8-hd': FAL_MINIMAX,
        'fal-ai/minimax/speech-2.8-turbo': FAL_MINIMAX,
        'fal-ai/minimax/speech-2.6-hd': FAL_MINIMAX,
        'fal-ai/minimax/speech-2.6-turbo': FAL_MINIMAX,
        'fal-ai/minimax/speech-02-hd': FAL_MINIMAX,
        'fal-ai/minimax/speech-02-turbo': FAL_MINIMAX,
    },
}


def set_nested_param(params, key, value):
    parts = key.split('.')
    for part in parts[:-1]:
        params = params.setdefault(part, {})
    params[parts[-1]] = value


class VoiceManager(BaseManager):
    def __init__(self, system):
        super().__init__(
            system,
            table_name='voices',
            load_columns=['uuid', 'config'],
        )
        self.voice_id_names = {}

    def load(self):
        sql.define_table('voices')
        voices_data =sql.get_results("SELECT name, config FROM voices", return_type='dict')
        self.voice_id_names = sql.get_results("SELECT uuid, name FROM voices", return_type='dict')
        self.clear()
        self.update({name: json.loads(config) for name, config in voices_data.items()})

    def get_param_map(self, model_obj):
        """Infer the model's voice param roles from its input_schema,
        then apply any per-model overrides."""
        model_key = (model_obj['provider'], model_obj['kind'], model_obj['_model_name'])
        metadata = self.system.manager.models.model_metadata.get(model_key, {})
        input_schema = metadata.get('input_schema', [])
        schema_keys = [f.get('key') for f in input_schema]

        param_map = {}
        for role, candidates in (
            ('text', TEXT_PARAM_KEYS),
            ('ref_audio', REF_AUDIO_PARAM_KEYS),
            ('ref_text', REF_TEXT_PARAM_KEYS),
        ):
            for key in candidates:
                if key in schema_keys:
                    param_map[role] = key
                    break

        if 'ref_audio' not in param_map:
            for field in input_schema:
                key = field.get('key', '')
                if field.get('type') == 'media_upload' and any(s in key for s in ('audio', 'voice', 'speaker', 'ref')):
                    param_map['ref_audio'] = key
                    break

        base_name = model_obj.get('_model_name', '').split(':', 1)[0]
        overrides = VOICE_MODEL_OVERRIDES.get(model_obj['provider'], {}).get(base_name, {})
        param_map.update(overrides)

        if 'text' not in param_map:
            raise ValueError(f"Couldn't find a text param for model '{base_name}'")
        if 'ref_audio' not in param_map and 'voice_id' not in param_map:
            raise ValueError(f"Model '{base_name}' doesn't support voice cloning (no reference audio param found)")
        return param_map

    async def prepare_model(self, voice_config, text, voice_name=None):
        """Build a runnable model_obj from a voice config, injecting the text,
        reference clip and reference transcript into model_params."""
        model_obj = convert_model_json_to_obj(voice_config.get('model'))
        param_map = self.get_param_map(model_obj)

        params = model_obj.setdefault('model_params', {})
        set_nested_param(params, param_map['text'], text)
        if 'ref_audio' in param_map:
            set_nested_param(params, param_map['ref_audio'], voice_config.get('reference_audio', ''))
        if 'ref_text' in param_map:
            set_nested_param(params, param_map['ref_text'], voice_config.get('reference_text', ''))
        if 'voice_id' in param_map:
            voice_id = await self._ensure_voice_id(voice_config, model_obj['provider'], param_map, voice_name)
            set_nested_param(params, param_map['voice_id'], voice_id)
        for key, value in param_map.get('extra', {}).items():
            set_nested_param(params, key, value)
        return model_obj

    def find_model_obj(self, base_name, provider_name, kind='AUDIO'):
        """Find a registered model by its unversioned name."""
        for provider, k, model_name in self.system.manager.models.keys():
            if provider == provider_name and k == kind and model_name.split(':', 1)[0] == base_name:
                return {'provider': provider, 'kind': k, '_model_name': model_name}
        return None

    async def _ensure_voice_id(self, voice_config, provider_name, param_map, voice_name=None):
        """Run the model's separate clone step once and persist the returned
        voice id into the voice's config, keyed by the clone model."""
        clone_model = param_map['clone_model']
        voice_ids = voice_config.get('voice_ids', {})
        if voice_ids.get(clone_model):
            return voice_ids[clone_model]

        reference = voice_config.get('reference_audio', '')
        try:
            obj = json.loads(reference)
            if isinstance(obj, dict) and 'url' in obj:
                reference = obj['url']
        except (json.JSONDecodeError, TypeError):
            pass
        if not reference:
            raise ValueError("A reference audio clip is required to clone this voice")

        clone_model_obj = self.find_model_obj(clone_model, provider_name)
        if clone_model_obj is None:
            raise ValueError(f"Model '{clone_model}' not found, sync voice models first")
        clone_model_obj['model_params'] = {param_map['clone_input']: reference}

        provider = self.system.manager.providers.get(provider_name)
        gen = await self.system.manager.models.run_model(clone_model_obj)
        first = json.loads(next(gen))
        output = await provider.get_transcription_result(first['model_name'], first['request_id'])
        voice_id = output.get(param_map['clone_output']) if isinstance(output, dict) else None
        if not voice_id:
            raise ValueError(f"Voice cloning with '{clone_model}' returned no voice id: {output}")

        voice_ids[clone_model] = voice_id
        voice_config['voice_ids'] = voice_ids
        if voice_name and voice_name in self:
            sql.execute(
                "UPDATE voices SET config = json_set(config, '$.voice_ids', json(?)) WHERE name = ?",
                (json.dumps(voice_ids), voice_name),
            )
        return voice_id

    async def generate_async(self, voice_name, text, voice_config=None):
        """Synthesize `text` with a cloned voice, return the audio filepath."""
        if voice_config is None:
            voice_config = self.get(voice_name)
            if voice_config is None:
                raise ValueError(f"Voice '{voice_name}' not found")
        model_obj = await self.prepare_model(voice_config, text, voice_name=voice_name)
        wf_config = {
            "_TYPE": "workflow",
            "config": {"autorun": True},
            "inputs": [],
            "members": [
                {
                    "config": {
                        "_TYPE": "audio",
                        "mode": "Model",
                        "model": model_obj,
                        "use_cache": True,
                        "wait_until_finished": True,
                    },
                    "id": "1",
                    "loc_x": 0,
                    "loc_y": 0,
                }
            ],
            "params": [],
        }
        result = await compute_workflow_async(wf_config, main=self.system._main_gui)
        if not result:
            return None
        try:
            return json.loads(result).get('filepath')
        except json.JSONDecodeError:
            raise ValueError(result)

    async def speak_async(self, voice_name, text, blocking=False):
        filepath = await self.generate_async(voice_name, text)
        if filepath:
            play_file(filepath, blocking=blocking, interrupt=False)
        return filepath
