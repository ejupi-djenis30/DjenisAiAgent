import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Deque
from collections import deque
import json
import os

class ShortTermMemory:
    """
    Implements a short-term memory system for the AI agent to remember recent events,
    observations and context across multiple interaction turns.
    """
    def __init__(self, max_items: int = 50, expiry_seconds: Optional[float] = None):
        """
        Initialize the short-term memory.
        
        Args:
            max_items: Maximum number of items to store
            expiry_seconds: Optional time in seconds after which items expire
        """
        self.memory: Dict[str, Dict[str, Any]] = {}
        self.recent_keys: Deque[str] = deque(maxlen=max_items)
        self.max_items = max_items
        self.expiry_seconds = expiry_seconds
        
    def store(self, key: str, value: Any, metadata: Optional[Dict[str, Any]] = None):
        """
        Store a value in memory with optional metadata.
        
        Args:
            key: Key to store the value under
            value: Value to store
            metadata: Optional metadata associated with the value
        """
        timestamp = time.time()
        
        # Create the memory entry
        memory_item = {
            "value": value,
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp).isoformat(),
            "metadata": metadata or {}
        }
        
        # Store in memory
        self.memory[key] = memory_item
        
        # Add to recent keys, maintaining order
        if key in self.recent_keys:
            self.recent_keys.remove(key)
        self.recent_keys.append(key)
        
        # Clean up old entries if needed
        self._clean_expired_items()
        
    def retrieve(self, key: str, default: Any = None) -> Any:
        """
        Retrieve a value from memory.
        
        Args:
            key: Key to retrieve
            default: Default value if key not found
            
        Returns:
            The stored value or default if not found
        """
        self._clean_expired_items()
        
        if key in self.memory:
            # Update access timestamp for LRU-like behavior
            self.memory[key]["last_accessed"] = time.time()
            return self.memory[key]["value"]
        else:
            return default
            
    def retrieve_with_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a value with its metadata.
        
        Args:
            key: Key to retrieve
            
        Returns:
            Dictionary with value and metadata, or None if key not found
        """
        self._clean_expired_items()
        
        if key in self.memory:
            # Update access timestamp
            self.memory[key]["last_accessed"] = time.time()
            return self.memory[key]
        else:
            return None
            
    def get_recent_items(self, count: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get the most recent items stored in memory.
        
        Args:
            count: Number of recent items to retrieve (None for all)
            
        Returns:
            List of recent items with their metadata
        """
        self._clean_expired_items()
        
        # Determine how many items to return
        num_items = count if count is not None else len(self.recent_keys)
        num_items = min(num_items, len(self.recent_keys))
        
        # Get the most recent keys
        recent_keys = list(self.recent_keys)[-num_items:]
        
        # Return the items
        return [
            {
                "key": key,
                **self.memory[key]
            }
            for key in recent_keys if key in self.memory
        ]
            
    def clear(self):
        """Clear all items from memory."""
        self.memory.clear()
        self.recent_keys.clear()
        
    def remove(self, key: str) -> bool:
        """
        Remove an item from memory.
        
        Args:
            key: Key to remove
            
        Returns:
            True if item was removed, False if not found
        """
        if key in self.memory:
            del self.memory[key]
            try:
                self.recent_keys.remove(key)
            except ValueError:
                pass
            return True
        return False
        
    def _clean_expired_items(self):
        """Clean up expired or excess items from memory."""
        # Check for expired items if expiry is set
        if self.expiry_seconds is not None:
            current_time = time.time()
            expired_keys = [
                key for key, item in self.memory.items()
                if current_time - item["timestamp"] > self.expiry_seconds
            ]
            
            for key in expired_keys:
                self.remove(key)
                
        # Check if we have too many items and remove oldest
        while len(self.memory) > self.max_items:
            if self.recent_keys:
                oldest_key = self.recent_keys[0]
                self.remove(oldest_key)
            else:
                # If recent_keys is empty but memory isn't, clear everything
                self.clear()
                break
                
    def save_to_file(self, file_path: str):
        """
        Save the current memory state to a JSON file.
        
        Args:
            file_path: Path to save the memory to
        """
        try:
            # Create a serializable version of the memory
            serializable = {
                "memory": {
                    key: {
                        # Handle non-serializable values
                        "value": str(item["value"]) if not isinstance(item["value"], (str, int, float, bool, list, dict)) else item["value"],
                        "timestamp": item["timestamp"],
                        "datetime": item["datetime"],
                        "metadata": item["metadata"]
                    }
                    for key, item in self.memory.items()
                },
                "recent_keys": list(self.recent_keys),
                "max_items": self.max_items,
                "expiry_seconds": self.expiry_seconds,
                "saved_at": datetime.now().isoformat()
            }
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
            
            # Save to file
            with open(file_path, 'w') as f:
                json.dump(serializable, f, indent=2)
                
            return True
        except Exception as e:
            print(f"Error saving memory to file: {str(e)}")
            return False
            
    def load_from_file(self, file_path: str) -> bool:
        """
        Load memory state from a JSON file.
        
        Args:
            file_path: Path to load the memory from
            
        Returns:
            True if loaded successfully, False otherwise
        """
        try:
            if not os.path.exists(file_path):
                return False
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            # Clear current memory
            self.clear()
            
            # Set parameters
            self.max_items = data.get("max_items", self.max_items)
            self.expiry_seconds = data.get("expiry_seconds", self.expiry_seconds)
            
            # Load memory items
            for key, item in data.get("memory", {}).items():
                self.memory[key] = item
                
            # Load recent keys
            for key in data.get("recent_keys", []):
                if key not in self.recent_keys and key in self.memory:
                    self.recent_keys.append(key)
                    
            return True
        except Exception as e:
            print(f"Error loading memory from file: {str(e)}")
            return False