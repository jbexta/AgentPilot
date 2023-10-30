


class SequentialIterator:
    def __init__(self, context):
        self.context = context

    def cycle(self):
        participants = self.context.participants  # {prev_part_id: [Agent()]}  # todo restructure
        for prev_part_id, next_agents in participants.items():
            yield next_agents
        # for agent in participants.values():
        #     yield agent
