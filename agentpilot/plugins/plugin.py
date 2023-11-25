from agentpilot.utils.apis import llm


class AgentPlugin:  # todo - refactor
    def __init__(self):  # , member_id):
        self.agent_object = None
        self.stream_object_base = None
        # self.member_id = member_id
        self.system_msg = ''
        self.logging_obj = None

    def stream(self, messages, msgs_in_system=False, system_msg='', model='gpt-3.5-turbo', use_davinci=False):  # TEMPORARY STREAM AS PLUGIN
        if not use_davinci:
            stream = llm.get_chat_response(messages if not msgs_in_system else [],
                                                           system_msg,
                                                           model=model,
                                                           temperature=0.7)  # todo - add setting for temperature on each part
            self.logging_obj = stream.logging_obj
            for resp in stream:
                delta = resp.choices[0].get('delta', {})
                if not delta: continue
                text = delta.get('content', '')
                yield 'assistant', text
        else:
            raise NotImplementedError()
            # stream = llm.get_completion(system_msg)
            # for resp in stream:
            #     delta = resp.choices[0].get('delta', {})
            #     if not delta: continue
            #     text = delta.get('content', '')
            #     yield 'assistant', text



class TaskPlugin:
    def __init__(self):
        super().__init__()