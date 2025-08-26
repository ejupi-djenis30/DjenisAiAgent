import time
import uuid
from typing import Dict, Any, List, Optional, Tuple, Callable
from enum import Enum

from memory.short_term_memory import ShortTermMemory
from memory.task_memory import TaskMemory, Task, TaskStatus
from planning.schemas import ActionSchema, PlanSchema, Step

class PlanningStrategy(Enum):
    """Strategies for planning task execution."""
    SEQUENTIAL = "sequential"  # Execute steps in sequence
    ADAPTIVE = "adaptive"      # Adjust plan based on results of previous steps
    PARALLEL = "parallel"      # Execute multiple steps in parallel when possible

class Planner:
    """
    Plans and manages the execution of tasks by breaking them down into steps,
    tracking their execution, and adapting based on feedback.
    """
    def __init__(self, 
                short_term_memory: Optional[ShortTermMemory] = None,
                task_memory: Optional[TaskMemory] = None):
        """
        Initialize the planner.
        
        Args:
            short_term_memory: Optional ShortTermMemory instance
            task_memory: Optional TaskMemory instance
        """
        # Initialize memories if not provided
        self.short_term_memory = short_term_memory or ShortTermMemory()
        self.task_memory = task_memory or TaskMemory()
        
        # Current context, resources and state
        self.current_context = {}
        self.available_resources = {}
        self.available_actions = {}
        self.current_plan = None
        self.current_task_id = None
        
    def register_action(self, action_schema: ActionSchema):
        """
        Register an available action with the planner.
        
        Args:
            action_schema: Schema defining the action
        """
        self.available_actions[action_schema.action_id] = action_schema
        
    def set_context(self, context: Dict[str, Any]):
        """
        Set the current planning context.
        
        Args:
            context: Dictionary of context information
        """
        self.current_context = context
        self.short_term_memory.store("planning_context", context)
        
    def update_context(self, key: str, value: Any):
        """
        Update a specific item in the current context.
        
        Args:
            key: Context key to update
            value: New value
        """
        self.current_context[key] = value
        self.short_term_memory.store("planning_context", self.current_context)
        
    def register_resource(self, resource_id: str, resource: Any):
        """
        Register an available resource with the planner.
        
        Args:
            resource_id: ID for the resource
            resource: The resource object
        """
        self.available_resources[resource_id] = resource
        
    def create_plan(self, 
                   goal: str, 
                   strategy: PlanningStrategy = PlanningStrategy.SEQUENTIAL) -> PlanSchema:
        """
        Create a plan to achieve a goal.
        
        Args:
            goal: Description of the goal to achieve
            strategy: Strategy for planning and execution
            
        Returns:
            A plan schema
        """
        # Create a new plan
        plan = PlanSchema(
            plan_id=str(uuid.uuid4()),
            goal=goal,
            strategy=strategy.value
        )
        
        # Store the current goal in memory
        self.short_term_memory.store("current_goal", goal)
        
        # Create task for this plan in task memory
        self.current_task_id = self.task_memory.create_task(
            description=f"Achieve goal: {goal}",
            metadata={"plan_id": plan.plan_id, "strategy": strategy.value}
        )
        
        # Set as current plan
        self.current_plan = plan
        
        # Return the plan (currently empty, steps will be added later)
        return plan
    
    def add_step_to_plan(self, 
                        action_id: str, 
                        parameters: Dict[str, Any] = None,
                        description: str = None) -> Step:
        """
        Add a step to the current plan.
        
        Args:
            action_id: ID of the action to perform
            parameters: Parameters for the action
            description: Optional description of the step
            
        Returns:
            The created step
        """
        if not self.current_plan:
            raise ValueError("No active plan. Call create_plan first.")
            
        if action_id not in self.available_actions:
            raise ValueError(f"Unknown action: {action_id}")
            
        # Create step
        step = Step(
            step_id=str(uuid.uuid4()),
            action_id=action_id,
            parameters=parameters or {},
            description=description or self.available_actions[action_id].description
        )
        
        # Add to plan
        self.current_plan.add_step(step)
        
        # Add to task memory if we have a current task
        if self.current_task_id:
            self.task_memory.add_task_step(
                self.current_task_id, 
                f"Planned: {step.description}",
                metadata={
                    "step_id": step.step_id,
                    "action_id": action_id,
                    "parameters": parameters
                }
            )
            
        return step
    
    def execute_plan(self, 
                    action_handlers: Dict[str, Callable] = None,
                    max_steps: int = None) -> Dict[str, Any]:
        """
        Execute the current plan.
        
        Args:
            action_handlers: Dictionary mapping action IDs to handler functions
            max_steps: Maximum number of steps to execute
            
        Returns:
            Dictionary with execution results
        """
        if not self.current_plan:
            raise ValueError("No active plan to execute.")
            
        if not action_handlers:
            raise ValueError("No action handlers provided.")
            
        # Update task status
        if self.current_task_id:
            self.task_memory.update_task_status(self.current_task_id, TaskStatus.IN_PROGRESS)
            
        # Execute steps based on strategy
        results = {
            "plan_id": self.current_plan.plan_id,
            "goal": self.current_plan.goal,
            "steps_executed": 0,
            "steps_succeeded": 0,
            "steps_failed": 0,
            "step_results": []
        }
        
        # Get steps to execute
        steps = self.current_plan.steps[:max_steps] if max_steps else self.current_plan.steps
        
        # Execute each step
        for idx, step in enumerate(steps):
            # Check if we have a handler for this action
            handler = action_handlers.get(step.action_id)
            if not handler:
                step_result = {
                    "step_id": step.step_id,
                    "action_id": step.action_id,
                    "success": False,
                    "error": f"No handler for action: {step.action_id}"
                }
                results["steps_failed"] += 1
            else:
                try:
                    # Execute the step
                    start_time = time.time()
                    
                    # Update step status in task memory
                    if self.current_task_id:
                        step_idx = self.task_memory.add_task_step(
                            self.current_task_id,
                            f"Executing: {step.description}",
                            metadata={
                                "step_id": step.step_id,
                                "action_id": step.action_id,
                                "parameters": step.parameters
                            }
                        )
                    
                    # Call the handler
                    action_result = handler(step.parameters)
                    
                    # Record execution time
                    execution_time = time.time() - start_time
                    
                    # Update task memory with result
                    if self.current_task_id and step_idx is not None:
                        self.task_memory.update_task_step(
                            self.current_task_id,
                            step_idx,
                            result=action_result,
                            metadata={"execution_time": execution_time}
                        )
                    
                    # Create step result
                    step_result = {
                        "step_id": step.step_id,
                        "action_id": step.action_id,
                        "success": True,
                        "execution_time": execution_time,
                        "result": action_result
                    }
                    
                    # Store in short-term memory
                    self.short_term_memory.store(
                        f"step_result_{step.step_id}", 
                        step_result,
                        {"plan_id": self.current_plan.plan_id, "index": idx}
                    )
                    
                    results["steps_succeeded"] += 1
                    
                except Exception as e:
                    step_result = {
                        "step_id": step.step_id,
                        "action_id": step.action_id,
                        "success": False,
                        "error": str(e)
                    }
                    
                    # Update task memory with error
                    if self.current_task_id and step_idx is not None:
                        self.task_memory.update_task_step(
                            self.current_task_id,
                            step_idx,
                            result={"error": str(e)},
                            metadata={"success": False}
                        )
                        
                    results["steps_failed"] += 1
                    
                    # Handle failure based on strategy
                    if self.current_plan.strategy == PlanningStrategy.SEQUENTIAL.value:
                        # In sequential mode, stop on first failure
                        break
            
            results["step_results"].append(step_result)
            results["steps_executed"] += 1
            
        # Update task status based on results
        if self.current_task_id:
            if results["steps_failed"] == 0:
                self.task_memory.update_task_status(self.current_task_id, TaskStatus.COMPLETED)
            else:
                self.task_memory.update_task_status(self.current_task_id, TaskStatus.FAILED)
                
        return results
    
    def adapt_plan(self, 
                  execution_results: Dict[str, Any], 
                  analyzer_fn: Callable[[Dict[str, Any], Dict[str, Any]], List[Step]]) -> PlanSchema:
        """
        Adapt the current plan based on execution results.
        
        Args:
            execution_results: Results from execute_plan
            analyzer_fn: Function to analyze results and suggest new steps
            
        Returns:
            Updated plan
        """
        if not self.current_plan:
            raise ValueError("No active plan to adapt.")
            
        # Analyze results and get suggested steps
        new_steps = analyzer_fn(execution_results, self.current_context)
        
        # Create a new adapted plan
        adapted_plan = PlanSchema(
            plan_id=str(uuid.uuid4()),
            goal=self.current_plan.goal,
            strategy=self.current_plan.strategy,
            parent_plan_id=self.current_plan.plan_id
        )
        
        # Add the new steps
        for step in new_steps:
            adapted_plan.add_step(step)
            
        # Store relation in short-term memory
        self.short_term_memory.store(
            f"plan_adaptation_{self.current_plan.plan_id}",
            {
                "original_plan_id": self.current_plan.plan_id,
                "adapted_plan_id": adapted_plan.plan_id,
                "adaptation_reason": "Execution results analysis"
            }
        )
        
        # Update the current plan
        self.current_plan = adapted_plan
        
        # Create a new task for the adapted plan
        self.current_task_id = self.task_memory.create_task(
            description=f"Adapted plan for goal: {adapted_plan.goal}",
            metadata={
                "plan_id": adapted_plan.plan_id,
                "parent_plan_id": adapted_plan.parent_plan_id,
                "strategy": adapted_plan.strategy
            }
        )
        
        return adapted_plan
        
    def get_current_plan(self) -> Optional[PlanSchema]:
        """
        Get the current plan.
        
        Returns:
            The current plan or None if no plan exists
        """
        return self.current_plan