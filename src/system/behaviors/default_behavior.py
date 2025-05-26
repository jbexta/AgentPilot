import asyncio
import json

from src.utils import sql


class DefaultBehavior:
    def __init__(self, workflow):
        self.workflow = workflow
        # self.tasks = []

    async def start(self, from_member_id: int = None, feed_back: bool = False):
        async for key, chunk in self.receive(from_member_id, feed_back):
            pass

    async def receive(self, from_member_id: int = None, feed_back: bool = False):
        processed_members = set()

        def create_async_group_task(member_ids):
            """ Helper function to create and return a coroutine that runs all members in the member_async_group """
            async def run_group():
                group_tasks = []
                for member_id in member_ids:
                    if member_id not in processed_members:
                        m = self.workflow.members[member_id]
                        sub_task = asyncio.create_task(run_member_task(m))
                        group_tasks.append(sub_task)
                        processed_members.add(member_id)
                try:
                    await asyncio.gather(*group_tasks)
                except StopIteration:
                    return

            return run_group

        async def run_member_task(member):  # todo dirty
            async for _ in member.run_member():
                pass

        if len(self.workflow.members) == 0:
            return

        # first_member = next(iter(self.workflow.members.values()))
        # if first_member.config.get('_TYPE', 'agent') == 'user':  #!33!#
        #     from_member_id = first_member.member_id

        filter_role = self.workflow.config.get('config', {}).get('filter_role', 'All').lower()
        self.workflow.responding = True
        try:
            found_source = True if from_member_id is None else False
            for member in self.workflow.members.values():
                if not found_source and member.member_id == from_member_id:
                    found_source = True
                if not found_source:
                    continue  # todo clean mechanism
                ignore_turn_output = feed_back and member.member_id == from_member_id
                if (member.turn_output is not None and not ignore_turn_output) or member.member_id in processed_members:
                    continue
                if self.workflow.chat_page:
                    self.workflow.chat_page.workflow_settings.refresh_member_highlights()

                async_group_member_ids = self.workflow.get_member_async_group(member.member_id)
                if async_group_member_ids:
                    self.workflow.gen_members = async_group_member_ids
                    # Create a single coroutine to handle the entire member async group
                    run_method = create_async_group_task(async_group_member_ids)
                    result = await run_method()
                    if result is True:
                        return
                else:
                    nem = self.workflow.next_expected_member()  # !looper! #
                    is_final_message = self.workflow.next_expected_is_last_member() and member == nem
                    # # Run individual member
                    try:
                        async for key, chunk in member.run_member():
                            if key == 'SYS' and chunk == 'BREAK':
                                # break
                                is_base_workflow = self.workflow._parent_workflow is None
                                if is_base_workflow:
                                    return
                                break

                            if is_final_message and (key == filter_role or filter_role == 'all'):
                                yield key, chunk

                    except StopIteration:  # todo still needed?
                        return

                if not self.workflow.autorun:
                    return

            if self.workflow._parent_workflow is not None:  # todo
                # last_member = list(self.workflow.members.values())[-1]
                final_message = self.workflow.get_final_message(filter_role=filter_role)
                if final_message:
                    full_member_id = self.workflow.full_member_id()
                    log_obj = sql.get_scalar("SELECT log FROM contexts_messages WHERE id = ?", (final_message['id'],))
                    self.workflow.save_message(final_message['role'], final_message['content'], full_member_id, json.loads(log_obj))

        except asyncio.CancelledError:
            pass  # task was cancelled, so we ignore the exception
        except Exception as e:
            raise e
        finally:
            self.workflow.responding = False

    def stop(self):
        self.workflow.stop_requested = True
