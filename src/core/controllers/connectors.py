from core.managers.modules import ModulesController


class ConnectorsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='connectors', 
            load_to_path='core.connectors',
            class_based=True,
            inherit_from=None,
            description="Database connection modules",
            long_description="Connector modules handle connections to external sources such as databases"
        )