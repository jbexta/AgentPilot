
class Member:
    def __init__(self, context, m_id, agent, inputs):
        self.context = context
        self.main = context.main
        self.m_id = m_id
        self.agent = agent
        self.inputs = inputs  # [member_id]
        self.task = None
        self.last_output = ''

    async def respond(self):
        for key, chunk in self.agent.receive(stream=True):
            if self.context.stop_requested:
                self.context.stop_requested = False
                break
            if key in ('assistant', 'message'):
                self.main.new_sentence_signal.emit(self.m_id, chunk)  # Emitting the signal with the new sentence.
            else:
                break