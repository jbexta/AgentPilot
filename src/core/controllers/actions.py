from core.managers.modules import ModulesController


class ActionsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system,
            module_type='actions',
            load_to_path='core.actions',
            class_based=True,
            inherit_from='UndoableAction',
            description="Undo-able user actions",
            long_description="Action modules represent discrete undo-able user actions. Each action captures the data needed to undo and redo itself, and is recorded to the app's undo history."
        )
