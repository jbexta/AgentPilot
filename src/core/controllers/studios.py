from core.managers.modules import ModulesController


class StudiosController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='studios', 
            load_to_path='gui.studios',
            class_based=True,
            # inherit_from='MessageBubble',
            description="Studio modules",
            long_description="Studio modules define editors for creating and modifying different types of content."
        )