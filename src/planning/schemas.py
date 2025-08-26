from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

@dataclass
class ActionSchema:
    """Schema for defining available actions."""
    action_id: str
    description: str
    required_parameters: List[str] = field(default_factory=list)
    optional_parameters: List[str] = field(default_factory=list)
    expected_output: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Step:
    """A step in a plan that specifies an action to execute."""
    step_id: str
    action_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: Optional[str] = None
    depends_on: List[str] = field(default_factory=list)  # IDs of steps this step depends on
    
    def validate(self, available_actions: Dict[str, ActionSchema]) -> bool:
        """
        Validate that this step references a valid action and has all required parameters.
        
        Args:
            available_actions: Dictionary of available actions
            
        Returns:
            True if valid, False otherwise
        """
        if self.action_id not in available_actions:
            return False
            
        action = available_actions[self.action_id]
        
        # Check that all required parameters are present
        for param in action.required_parameters:
            if param not in self.parameters:
                return False
                
        return True

@dataclass
class PlanSchema:
    """Schema for a plan consisting of ordered steps."""
    plan_id: str
    goal: str
    strategy: str = "sequential"
    steps: List[Step] = field(default_factory=list)
    parent_plan_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def add_step(self, step: Step):
        """
        Add a step to the plan.
        
        Args:
            step: Step to add
        """
        self.steps.append(step)
        
    def remove_step(self, step_id: str) -> bool:
        """
        Remove a step from the plan by ID.
        
        Args:
            step_id: ID of the step to remove
            
        Returns:
            True if step was found and removed, False otherwise
        """
        for i, step in enumerate(self.steps):
            if step.step_id == step_id:
                self.steps.pop(i)
                return True
        return False
        
    def get_step(self, step_id: str) -> Optional[Step]:
        """
        Get a step by ID.
        
        Args:
            step_id: ID of the step to get
            
        Returns:
            The step or None if not found
        """
        for step in self.steps:
            if step.step_id == step_id:
                return step
        return None
        
    def validate(self, available_actions: Dict[str, ActionSchema]) -> bool:
        """
        Validate that all steps in the plan are valid.
        
        Args:
            available_actions: Dictionary of available actions
            
        Returns:
            True if all steps are valid, False otherwise
        """
        # Check that each step is valid
        for step in self.steps:
            if not step.validate(available_actions):
                return False
                
        # Check that all dependency references are valid
        step_ids = {step.step_id for step in self.steps}
        for step in self.steps:
            for dep_id in step.depends_on:
                if dep_id not in step_ids:
                    return False
                    
        return True
        
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert the plan to a dictionary.
        
        Returns:
            Dictionary representation of the plan
        """
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "strategy": self.strategy,
            "steps": [
                {
                    "step_id": step.step_id,
                    "action_id": step.action_id,
                    "parameters": step.parameters,
                    "description": step.description,
                    "depends_on": step.depends_on
                }
                for step in self.steps
            ],
            "parent_plan_id": self.parent_plan_id,
            "metadata": self.metadata
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanSchema':
        """
        Create a PlanSchema from a dictionary.
        
        Args:
            data: Dictionary representation of a plan
            
        Returns:
            A PlanSchema object
        """
        plan = cls(
            plan_id=data["plan_id"],
            goal=data["goal"],
            strategy=data.get("strategy", "sequential"),
            parent_plan_id=data.get("parent_plan_id"),
            metadata=data.get("metadata", {})
        )
        
        for step_data in data.get("steps", []):
            step = Step(
                step_id=step_data["step_id"],
                action_id=step_data["action_id"],
                parameters=step_data.get("parameters", {}),
                description=step_data.get("description"),
                depends_on=step_data.get("depends_on", [])
            )
            plan.add_step(step)
            
        return plan