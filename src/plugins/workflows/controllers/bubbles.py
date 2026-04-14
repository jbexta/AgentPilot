from core.managers.modules import ModulesController
from utils.helpers import convert_to_safe_case


class BubblesController(ModulesController):
    def __init__(self, system):
        super().__init__(
            system, 
            module_type='bubbles', 
            load_to_path='plugins.workflows.bubbles',
            class_based=True,
            inherit_from='MessageBubble',
            description="Chat message bubble modules",
            long_description="Bubble modules define the appearance and behavior of message bubbles"
        )

    def initial_content(self, module_name: str):
        safe_name = convert_to_safe_case(module_name).capitalize()
        return f"""
            from plugins.workflows.bubbles import MessageBubble, MessageButton

            class Bubble_{safe_name}(MessageBubble):
                from utils.helpers import message_button, message_extension

                def __init__(self, parent, message):
                    super().__init__(
                        parent=parent,
                        message=message,
                    )

                def setMarkdownText(self, text):
                    super().setMarkdownText(text)
        """