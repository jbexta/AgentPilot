class Pitch:
    display_name = 'Pitch'
    description = 'Adjust pitch of audio'

    @staticmethod
    def apply(clip, semitones=2):
        """Apply pitch shift effect to an audio clip."""
        factor = 2 ** (semitones / 12)
        return clip.fx(lambda audio: audio.set_fps(int(audio.fps * factor)))
