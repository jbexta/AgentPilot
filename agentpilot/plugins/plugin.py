from utils.apis import llm


class AgentPlugin:  # todo - refactor
    def __init__(self):
        self.agent_object = None
        self.stream_object_base = None
        self.system_msg = ''

    def stream(self, messages, msgs_in_system=False, system_msg='', model='gpt-3.5-turbo', use_davinci=False):  # TEMPORARY STREAM AS PLUGIN
        if not use_davinci:
            stream, initial_prompt = llm.get_chat_response(messages if not msgs_in_system else [],
                                                           system_msg,
                                                           model=model,
                                                           temperature=0.7)  # todo - add setting for temperature on each part
            for resp in stream:
                delta = resp.choices[0].get('delta', {})
                if not delta: continue
                text = delta.get('content', '')
                yield 'assistant', text
        else:
            stream = llm.get_completion(system_msg)
            for resp in stream:
                delta = resp.choices[0].get('delta', {})
                if not delta: continue
                text = delta.get('content', '')
                yield 'assistant', text



class TaskPlugin:
    def __init__(self):
        super().__init__()