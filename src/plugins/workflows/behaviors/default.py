import asyncio
import json

from utils import sql


class DefaultBehavior:
    def __init__(self, workflow):
        self.workflow = workflow

    def stop(self):
        """Signal the workflow to stop."""
        self.workflow.stop_requested = True

    async def start(self, from_member_id: str = None, feed_back: bool = False):
        async for key, chunk in self.receive(from_member_id, feed_back):
            pass

    async def receive(self, from_member_id: str = None, feed_back: bool = False):

        if len(self.workflow.members) == 0:
            return

        self.workflow.responding = True
        filter_role = self.workflow.config.get('config', {}).get('filter_role', 'All').lower()
        found_source = True if from_member_id is None else False

        def get_async_members() -> list[str]:
            nonlocal found_source

            """Return member IDs whose inputs are all satisfied (or have no inputs)."""
            runnable = []
            for member_id, member in self.workflow.members.items():
                if not found_source and member.member_id == from_member_id:
                    found_source = True
                if member.turn_output is not None:
                    continue
                if not found_source:
                    continue  # todo clean mechanism
                if not all(
                    self.workflow.members[inp_id].turn_output is not None 
                    for inp_id in getattr(member, "inputs", [])
                ):
                    break
                if getattr(member, 'break_on_run', False):
                    break
                runnable.append(member_id)

                if self.workflow.member_looper_output(member_id) is not None:
                    break

            return runnable

        async def run_member_task(member_id):  # todo dirty
            member = self.workflow.members[member_id]
            async for _ in member.run():
                pass
        
        try:
            alt_turn_state = self.workflow.message_history.alt_turn_state
            while True:
                runnable_member_ids = get_async_members()
                if not runnable_member_ids:
                    break  # done
                
                if len(runnable_member_ids) > 1:
                    # run all ready members concurrently
                    await asyncio.gather(*[
                        run_member_task(member_id)
                        for member_id in runnable_member_ids
                    ])
                else:
                    # # Run individual member
                    only_member = self.workflow.members[runnable_member_ids[0]]
                    nem = self.workflow.next_expected_member()  # !looper! #
                    is_final_message = self.workflow.next_expected_is_last_member() and only_member == nem
                    try:
                        async for key, chunk in only_member.run():
                            if is_final_message and (key == filter_role or filter_role == 'all'):
                                yield key, chunk

                    except StopIteration:  # todo still needed?
                        raise NotImplementedError()

                for member_id in runnable_member_ids:
                    member = self.workflow.members[member_id]
                    if member.turn_output is None:
                        member.turn_output = ''

                self.workflow.message_history.refresh_messages()
                if self.workflow.chat_widget:
                    self.workflow.chat_widget.message_collection.refresh(block_autorun=True)
                
                if any(
                    getattr(self.workflow.members[member_id], 'break_on_run', False)
                    for member_id in runnable_member_ids
                ):
                    return

                run_finished = alt_turn_state != self.workflow.message_history.alt_turn_state
                if run_finished:
                    break

            # # if not self.workflow.autorun:
            # #     break

            # handle final message
            if self.workflow._parent_workflow is not None:
                final_message = self.workflow.get_final_message()
                if final_message:
                    full_member_id = self.workflow.full_member_id()
                    log_obj = sql.get_scalar(
                        "SELECT log FROM contexts_messages WHERE id = ?",
                        (final_message['id'],),
                    )
                    self.workflow.save_message(
                        final_message['role'],
                        final_message['content'],
                        full_member_id,
                        json.loads(log_obj)
                    )

        finally:
            self.workflow.responding = False