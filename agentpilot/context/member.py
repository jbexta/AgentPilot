from abc import abstractmethod


class Member:
    def __init__(self, main, workflow, m_id, inputs):
        self.main = main
        self.workflow = workflow
        self.m_id = m_id
        # self.agent = agent
        self.inputs = inputs if inputs else []
        self.response_task = None
        self.last_output = ''

    @abstractmethod
    def run_member(self):
        """The entry response method for the member."""
        pass

    # async def respond(self):
    #     for key, chunk in self.agent.receive(stream=True):
    #         if self.context.stop_requested:
    #             self.context.stop_requested = False
    #             break
    #         if key in ('assistant', 'message'):
    #             # todo - move this to agent class
    #             self.main.new_sentence_signal.emit(self.m_id, chunk)  # Emitting the signal with the new sentence.
    #         else:
    #             break