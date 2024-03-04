from src.agent.base import Agent
# from agentpilot.plugins.selfoperatingcomputer.src import main
from src.utils.api import apis


class SelfOperatingComputer:  # (Agent):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # # def load_agent(self):
    # #     super().load_agent()
    # #
    # #     current_model =
    # #
    # #     main.client.api_key = apis['openai']['priv_key']
    # #     main.client.base_url = os.getenv("OPENAI_API_BASE_URL", client.base_url)
    #
    # def stream(self, *args, **kwargs):
    #     # model kwarg
    #     model_obj = kwargs.get('model', None)
    #     if model_obj is None:
    #         raise Exception('No model specified')
    #
    #     model, model_config = model_obj
    #     main.client.api_key = model_config.get('priv_key', apis['openai']['priv_key'])
    #     main.client.base_url = model_config.get('api_base', '')
    #
    #     messages = self.context.message_history.get(llm_format=True, calling_member_id=self.member_id)
    #     last_user_msg = messages[-1]
    #
    #     main.main(model, True, last_user_msg['content'], self.context)
    #
    #     yield 'assistant', ''

