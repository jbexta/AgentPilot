
from plugins.workflows.members import MediaMember
from utils.helpers import set_module_type


@set_module_type(module_type='Members', settings='audio_settings')
class Audio(MediaMember):
    default_role = 'audio'
    default_avatar = ':/resources/icon-audio.png'
    default_name = 'Audio'
    OUTPUT = 'AUDIO'

    async def receive(self):
        """Audio yields its content instead of SKIP."""
        msg_content = await self._process_media()
        yield 'audio', msg_content
