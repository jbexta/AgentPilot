from agentpilot.utils.apis import llm


class AgentPlugin:  # todo - refactor
    def __init__(self):  # , member_id):
        self.agent_object = None
        self.stream_object_base = None
        # self.member_id = member_id
        self.system_msg = ''
        self.logging_obj = None

    def stream(self, messages, msgs_in_system=False, system_msg='', model=None):
        stream = llm.get_chat_response(messages if not msgs_in_system else [],
                                                       system_msg,
                                                       model_obj=model)
        self.logging_obj = stream.logging_obj
        for resp in stream:
            delta = resp.choices[0].get('delta', {})
            if not delta:
                continue
            text = delta.get('content', '')
            yield 'assistant', text


class TaskPlugin:
    def __init__(self):
        super().__init__()