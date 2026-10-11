from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy


@workflow.defn
class CaseWorkflow:
    def __init__(self):
        self.queue: list[str] = []

    @workflow.signal
    def event(self, event_id: str):
        if event_id not in self.queue:
            self.queue.append(event_id)

    @workflow.run
    async def run(self, case_id: str, pending: list[str]) -> None:
        self.queue.extend(pending)
        while True:
            await workflow.wait_condition(lambda: bool(self.queue))
            event_id = self.queue.pop(0)
            result = await workflow.execute_activity(
                "process_case_event",
                event_id,
                start_to_close_timeout=timedelta(minutes=4),
                retry_policy=RetryPolicy(initial_interval=timedelta(seconds=2), maximum_attempts=3),
            )
            if result == "pending":
                await workflow.sleep(30)
                self.queue.append(event_id)
            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new(args=[case_id, self.queue])


@workflow.defn
class ConversationWorkflow:
    def __init__(self):
        self.queue: list[str] = []

    @workflow.signal
    def event(self, event_id: str):
        if event_id not in self.queue:
            self.queue.append(event_id)

    @workflow.run
    async def run(self, object_id: str, pending: list[str]) -> None:
        self.queue.extend(pending)
        while True:
            await workflow.wait_condition(lambda: bool(self.queue))
            event_id = self.queue.pop(0)
            result = await workflow.execute_activity(
                "process_work_event",
                event_id,
                start_to_close_timeout=timedelta(minutes=7),
                retry_policy=RetryPolicy(
                    initial_interval=timedelta(seconds=2), maximum_interval=timedelta(seconds=30),
                ),
            )
            if result == "pending":
                await workflow.sleep(5)
                self.queue.append(event_id)
            if workflow.info().is_continue_as_new_suggested():
                workflow.continue_as_new(args=[object_id, self.queue])
