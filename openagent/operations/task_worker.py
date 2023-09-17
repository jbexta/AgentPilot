import threading
import time

from utils import logs
from queue import Queue, LifoQueue


class TaskWorker:
    def __init__(self, agent):
        self.agent = agent
        self.active_task = None
        self.queued_tasks = Queue()
        self.task_responses = Queue()

        # task_thread = threading.Thread(target=self.task_thread)
        # task_thread.start()

    # def task_thread(self):
    #     while True:
    #         time.sleep(0.05)
    #         is_speaking = self.agent.speech_lock.locked()
    #         last_role = self.agent.context.message_history.last_role()
    #         last_id = self.agent.context.message_history.last_id()
    #
    #         if is_speaking or last_role == 'assistant':
    #             continue
    #
    #         requeue_tasks = []
    #         while not self.queued_tasks.empty():
    #
    #             self.active_task = self.queued_tasks.get(block=True)
    #             if self.active_task.current_msg_id == last_id:
    #                 requeue_tasks.append(self.active_task)
    #                 continue
    #
    #             try:
    #                 task_finished = self.active_task.run()
    #                 if not task_finished:
    #                     self.active_task.current_msg_id = last_id
    #                     requeue_tasks.append(self.active_task)
    #
    #             except Exception as e:
    #                 self.task_responses.put(f'[SAY] "I failed the task" (Task = `{self.active_task.objective}`)')
    #                 logs.insert_log('TASK ERROR', str(e))
    #
    #         for rtask in requeue_tasks:
    #             self.queued_tasks.put(rtask)
    #         self.active_task = None

    def collect_task_responses(self):
        responses = set()
        while not self.task_responses.empty():
            responses.add(self.task_responses.get())
        return self.format_messages(responses)

    # def format_messages(self, messages):
    #     msg = '\n'.join([r.strip() for r in messages if isinstance(r, str)])
    #     dialogue_placeholders = {
    #         '[RES]': '[ITSOC] very briefly respond to the user in no more than [3S] ',
    #         '[INF]': '[ITSOC] very briefly inform the user in no more than [3S] ',
    #         '[ANS]': '[ITSOC] very briefly respond to the user considering the following information: ',
    #         '[Q]': '[ITSOC] Ask the user the following question: ',
    #         '[SAY]': '[ITSOC], say: ',
    #         '[MI]': '[ITSOC] Ask for the following information: ',
    #         '[ITSOC]': 'In the style of {char_name}{verb}, spoken like a genuine dialogue ',
    #         '[WOFA]': 'Without offering any further assistance, ',
    #         '[3S]': 'Three sentences',
    #     }
    #     for k, v in dialogue_placeholders.items():
    #         msg = msg.replace(k, v)
    #
    #     if msg != '':
    #         msg = f"[INSTRUCTIONS-FOR-NEXT-RESPONSE]\n{msg}\n[/INSTRUCTIONS-FOR-NEXT-RESPONSE]"
    #     return msg

    def active_task_fingerprint(self):
        if self.active_task is None:
            return ''
        return self.active_task.fingerprint()
