import asyncio
import logging

logger = logging.getLogger(__name__)

class TaskManager:
    def __init__(self):
        # dict map: user_id -> { task_type -> asyncio.Task }
        self.tasks = {}

    def add_task(self, user_id: int, task_type: str, coro):
        if user_id not in self.tasks:
            self.tasks[user_id] = {}
        
        # Stop existing task of same type
        if task_type in self.tasks[user_id]:
            self.tasks[user_id][task_type].cancel()
        
        task = asyncio.create_task(coro)
        self.tasks[user_id][task_type] = task
        logger.info(f"✅ Task '{task_type}' iniciada para usuário {user_id}")
        return task

    def stop_task(self, user_id: int, task_type: str) -> bool:
        if user_id in self.tasks and task_type in self.tasks[user_id]:
            task = self.tasks[user_id][task_type]
            if not task.done():
                task.cancel()
            del self.tasks[user_id][task_type]
            logger.info(f"🛑 Task '{task_type}' parada para usuário {user_id}")
            return True
        return False

    def is_running(self, user_id: int, task_type: str) -> bool:
        if user_id in self.tasks and task_type in self.tasks[user_id]:
            return not self.tasks[user_id][task_type].done()
        return False

task_mgr = TaskManager()
