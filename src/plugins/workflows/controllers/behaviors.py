from core.managers.modules import ModulesController


class BehaviorsController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='behaviors', 
            load_to_path='plugins.workflows.behaviors',
            class_based=True,
            inherit_from=None,
            description="Workflow behavior modules",
            long_description="Behavior modules define how a workflow is executed, there is only one built-in behavior. Behaviors can be adapted to support different types of workflows."
        )
        #     class_args=[
        #         {
        #             'name': 'workflow',
        #             'description': 'The workflow of the behavior',
        #             'type': 'Workflow',
        #             'required': True,
        #         },
        #     ],
        #     class_methods=[
        #         {
        #             'name': 'start',
        #             'description': 'Start the behavior',
        #             'arguments': {
        #                 'from_member_id': {'type': 'string'},
        #                 'feed_back': {'type': 'boolean'},
        #             },
        #         },
        #         {
        #             'name': 'receive',
        #             'description': 'Receive a message from a member',
        #             'parameters': {
        #                 'type': 'object',
        #                 'properties': {
        #                     'from_member_id': {'type': 'string'},
        #                     'feed_back': {'type': 'boolean'},
        #                 },
        #             },
        #         },
        #         {
        #             'name': 'stop',
        #             'description': 'Stop the behavior',
        #         },
        #     ],
        # )