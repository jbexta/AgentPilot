from src.context.member import Member


class Tool(Member):
    def __init__(self, member_id=None, workflow=None, inputs=None):
        super().__init__(main=None, workflow=workflow, m_id=member_id, inputs=inputs)
        pass

    async def run_member(self):
        pass
