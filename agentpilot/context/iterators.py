

class SequentialIterator:
    def __init__(self, context):
        self.context = context

    def cycle(self):
        # All root members (members without inputs) use group_type
        # All child members are stored in a struct until able to respond
        # Member responses must be saved in contexts_messages with a reference to the member
        #   So that member get_messages can be queried through sql ? Or can we get it from the context?

        members = self.context.members
        member_inputs = self.context.member_inputs

        root_members = [m_id for m_id, agent in members.items() if len(member_inputs[m_id]) == 0]

        pass





        # participant_steps = self.context.participant_steps  # {prev_part_id: [Agent()]}  # todo restructure
        # for prev_part_id, next_agents in participant_steps.items():
        #     yield next_agents
        # # for agent in participants.values():
        # #     yield agent

