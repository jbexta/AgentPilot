class Greyscale:
    display_name = 'Greyscale'
    description = 'Convert image/video to greyscale'

    @staticmethod
    def apply(clip):
        """Apply greyscale effect to a clip."""
        return clip.fx(lambda frame: frame.mean(axis=2, keepdims=True).repeat(3, axis=2).astype('uint8'))
