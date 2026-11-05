from core.managers.modules import ModulesController


class HighlightersController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='highlighters', 
            load_to_path='gui.highlighters',
            class_based=True,
            inherit_from='QSyntaxHighlighter',
            description="Syntax highlighting modules",
            long_description="Highlighter modules define the syntax highlighting of text areas"
        )