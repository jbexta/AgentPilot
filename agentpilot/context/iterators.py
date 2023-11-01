


class SequentialIterator:
    def __init__(self, context):
        self.context = context

    def cycle(self):
        participant_steps = self.context.participant_steps  # {prev_part_id: [Agent()]}  # todo restructure
        for prev_part_id, next_agents in participant_steps.items():
            yield next_agents
        # for agent in participants.values():
        #     yield agent
