"""Base class for AI-powered media operations."""


class BaseOperation:
    """Base class for AI-powered media operations.

    Parameters
    ----------
    studio : VideoStudio
        The parent studio widget.
    clips_to_modify : list
        Direct references to the timeline clips being modified.
    """

    display_name = ''
    description = ''
    icon_path = ''

    def __init__(self, studio, clips_to_modify):
        self.studio = studio
        self.clips_to_modify = clips_to_modify

    def run(self):
        """Entry point called by the studio.

        Should show a dialog or execute directly.
        Subclasses must implement this.
        """
        raise NotImplementedError
