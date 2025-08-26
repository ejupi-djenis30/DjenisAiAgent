import time
import json
import os
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum, auto

class TaskStatus(Enum):
    """Enum for tracking task status."""
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()

class Task:
    """Represents a task with its metadata."""
    def __init__(
        self,
        task_id: str,
        description: str,
        status: TaskStatus = TaskStatus.PENDING,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.task_id = task_id
        self.description = description
        self.status = status
        self.metadata = metadata or {}
        self.created_at = time.time()
        self.updated_at = self.created_at
        self.steps: List[Dict[str, Any]] = []
        
    def update_status(self, status: TaskStatus):
        """Update the task status and timestamp."""
        self.status = status
        self.updated_at = time.time()
        
    def add_step(self, description: str, result: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None):
        """Add a step to the task."""
        step = {
            "timestamp": time.time(),
            "datetime": datetime.fromtimestamp(time.time()).isoformat(),
            "description": description,
            "result": result,
            "metadata": metadata or {}
        }
        self.steps.append(step)
        self.updated_at = time.time()
        return len(self.steps) - 1  # Return the step index
        
    def update_step(self, step_index: int, result: Any = None, metadata: Optional[Dict[str, Any]] = None):
        """Update a step in the task."""
        if 0 <= step_index < len(self.steps):
            if result is not None:
                self.steps[step_index]["result"] = result
            if metadata:
                self.steps[step_index]["metadata"].update(metadata)
            self.steps[step_index]["updated_at"] = time.time()
            self.updated_at = time.time()
            return True
        return False
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert the task to a dictionary."""
        return {
            "task_id": self.task_id,
            "description": self.description,
            "status": self.status.name,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "steps": self.steps
        }
        
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Task':
        """Create a Task from a dictionary."""
        task = Task(
            task_id=data["task_id"],
            description=data["description"],
            status=TaskStatus[data["status"]],
            metadata=data.get("metadata", {})
        )
        task.created_at = data.get("created_at", time.time())
        task.updated_at = data.get("updated_at", time.time())
        task.steps = data.get("steps", [])
        return task

class TaskMemory:
    """
    Manages storage and retrieval of tasks and their execution history.
    Provides methods to track task progress, update task status, and record execution steps.
    """
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize task memory.
        
        Args:
            storage_dir: Optional directory to persist tasks
        """
        self.tasks: Dict[str, Task] = {}
        self.storage_dir = storage_dir
        if storage_dir and not os.path.exists(storage_dir):
            os.makedirs(storage_dir, exist_ok=True)
            
    def create_task(self, 
                   description: str, 
                   metadata: Optional[Dict[str, Any]] = None,
                   task_id: Optional[str] = None) -> str:
        """
        Create a new task and return its ID.
        
        Args:
            description: Description of the task
            metadata: Optional metadata for the task
            task_id: Optional task ID (generated if not provided)
            
        Returns:
            Task ID
        """
        if task_id is None:
            task_id = str(uuid.uuid4())
            
        task = Task(task_id, description, TaskStatus.PENDING, metadata)
        self.tasks[task_id] = task
        
        # Persist if storage_dir is set
        if self.storage_dir:
            self._save_task(task)
            
        return task_id
    
    def add_task(self, task: Task) -> str:
        """
        Add an existing Task object.
        
        Args:
            task: Task object to add
            
        Returns:
            Task ID
        """
        self.tasks[task.task_id] = task
        
        # Persist if storage_dir is set
        if self.storage_dir:
            self._save_task(task)
            
        return task.task_id
        
    def get_task(self, task_id: str) -> Optional[Task]:
        """
        Get a task by its ID.
        
        Args:
            task_id: ID of the task to retrieve
            
        Returns:
            Task object or None if not found
        """
        return self.tasks.get(task_id)
        
    def update_task_status(self, task_id: str, status: TaskStatus) -> bool:
        """
        Update a task's status.
        
        Args:
            task_id: ID of the task to update
            status: New status
            
        Returns:
            True if updated, False if task not found
        """
        task = self.get_task(task_id)
        if task:
            task.update_status(status)
            
            # Persist if storage_dir is set
            if self.storage_dir:
                self._save_task(task)
                
            return True
        return False
        
    def add_task_step(self, 
                     task_id: str, 
                     description: str, 
                     result: Optional[Any] = None, 
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
        """
        Add a step to a task.
        
        Args:
            task_id: ID of the task to update
            description: Description of the step
            result: Optional result of the step
            metadata: Optional metadata for the step
            
        Returns:
            Step index or None if task not found
        """
        task = self.get_task(task_id)
        if task:
            step_index = task.add_step(description, result, metadata)
            
            # Persist if storage_dir is set
            if self.storage_dir:
                self._save_task(task)
                
            return step_index
        return None
        
    def update_task_step(self, 
                        task_id: str, 
                        step_index: int, 
                        result: Optional[Any] = None, 
                        metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update a step in a task.
        
        Args:
            task_id: ID of the task to update
            step_index: Index of the step to update
            result: Optional new result for the step
            metadata: Optional metadata to add/update
            
        Returns:
            True if updated, False if task or step not found
        """
        task = self.get_task(task_id)
        if task and task.update_step(step_index, result, metadata):
            
            # Persist if storage_dir is set
            if self.storage_dir:
                self._save_task(task)
                
            return True
        return False
        
    def remove_task(self, task_id: str) -> bool:
        """
        Remove a task.
        
        Args:
            task_id: ID of the task to remove
            
        Returns:
            True if removed, False if task not found
        """
        if task_id in self.tasks:
            del self.tasks[task_id]
            
            # Remove persisted task if storage_dir is set
            if self.storage_dir:
                task_file = os.path.join(self.storage_dir, f"{task_id}.json")
                if os.path.exists(task_file):
                    try:
                        os.remove(task_file)
                    except Exception as e:
                        print(f"Error removing task file {task_file}: {str(e)}")
                        
            return True
        return False
        
    def get_all_tasks(self) -> List[Task]:
        """
        Get all tasks.
        
        Returns:
            List of all tasks
        """
        return list(self.tasks.values())
        
    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """
        Get tasks by status.
        
        Args:
            status: Status to filter by
            
        Returns:
            List of tasks with the specified status
        """
        return [task for task in self.tasks.values() if task.status == status]
        
    def get_active_tasks(self) -> List[Task]:
        """
        Get active (pending or in-progress) tasks.
        
        Returns:
            List of active tasks
        """
        return [
            task for task in self.tasks.values() 
            if task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS)
        ]
        
    def clear_completed_tasks(self) -> int:
        """
        Clear all completed tasks.
        
        Returns:
            Number of tasks cleared
        """
        completed_ids = [
            task_id for task_id, task in self.tasks.items()
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED)
        ]
        
        for task_id in completed_ids:
            self.remove_task(task_id)
            
        return len(completed_ids)
        
    def clear_memory(self):
        """Clear all tasks from memory."""
        self.tasks.clear()
        
    def _save_task(self, task: Task):
        """Save a task to persistent storage."""
        if not self.storage_dir:
            return
            
        try:
            task_file = os.path.join(self.storage_dir, f"{task.task_id}.json")
            with open(task_file, 'w') as f:
                json.dump(task.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Error saving task {task.task_id}: {str(e)}")
            
    def load_tasks(self) -> int:
        """
        Load tasks from persistent storage.
        
        Returns:
            Number of tasks loaded
        """
        if not self.storage_dir or not os.path.exists(self.storage_dir):
            return 0
            
        loaded = 0
        for filename in os.listdir(self.storage_dir):
            if not filename.endswith('.json'):
                continue
                
            try:
                task_file = os.path.join(self.storage_dir, filename)
                with open(task_file, 'r') as f:
                    task_data = json.load(f)
                    
                task = Task.from_dict(task_data)
                self.tasks[task.task_id] = task
                loaded += 1
                
            except Exception as e:
                print(f"Error loading task from {filename}: {str(e)}")
                
        return loaded
        
    def get_task_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        Get the execution history of a task.
        
        Args:
            task_id: ID of the task
            
        Returns:
            List of steps in the task
        """
        task = self.get_task(task_id)
        if task:
            return task.steps
        return []