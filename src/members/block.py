from src.members.base import Member


class Block(Member):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        pass

    def load(self):
        pass

    async def run_member(self):
        """The entry response method for the member."""
        async for key, chunk in self.receive():  # stream=True):
            if self.workflow.stop_requested:
                self.workflow.stop_requested = False
                break
            self.main.new_sentence_signal.emit(key, self.member_id, chunk)

    async def receive(self):
        yield ''
