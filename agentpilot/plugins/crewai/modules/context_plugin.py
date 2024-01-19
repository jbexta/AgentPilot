from agentpilot.context.base import ContextBehaviour


class CrewAI_Context(ContextBehaviour):
    def __init__(self, context):
        self.context = context
        self.group_key = 'crewai'

    def start(self):
        for member in self.context.members.values():
            member.task = self.context.loop.create_task(self.run_member(member))

        self.context.responding = True
        try:
            # if True:  # sequential todo
            t = asyncio.gather(*[m.task for m in self.context.members.values()])
            self.context.loop.run_until_complete(t)
            # self.loop.run_until_complete(asyncio.gather(*[m.task for m in self.members.values()]))
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            # self.main.finished_signal.emit()
            raise e

    def stop(self):
        self.context.stop_requested = True
        for member in self.context.members.values():
            if member.task is not None:
                member.task.cancel()

    async def run_member(self, member):
        try:
            if member.inputs:
                await asyncio.gather(*[self.context.members[m_id].task
                                       for m_id in member.inputs
                                       if m_id in self.context.members])

            member.agent.respond()  # respond()  #
        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
