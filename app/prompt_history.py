import json
import os
from datetime import datetime
from typing import Dict, List

class PromptHistory:
    def __init__(self):
        self.history_file = 'data/prompt_history.json'
        self._ensure_data_directory()
        self._load_history()

    def _ensure_data_directory(self):
        """Ensure the data directory exists."""
        if not os.path.exists('data'):
            os.makedirs('data')

    def _load_history(self):
        """Load the prompt history from the JSON file."""
        if os.path.exists(self.history_file):
            with open(self.history_file, 'r') as f:
                self.history = json.load(f)
        else:
            self.history = []

    def _save_history(self):
        """Save the prompt history to the JSON file."""
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def add_entry(self, prompt: str, actions: List[Dict], result: str = None, llm_responses: List[Dict] = None):
        """
        Add a new entry to the prompt history.
        
        Args:
            prompt (str): The user's prompt
            actions (List[Dict]): List of actions taken
            result (str, optional): The final result of the task
            llm_responses (List[Dict], optional): List of LLM responses during the task
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "actions": actions,
            "result": result,
            "llm_responses": llm_responses or []
        }
        
        self.history.append(entry)
        self._save_history()

    def get_recent_entries(self, limit: int = 10) -> List[Dict]:
        """Get the most recent entries from the history."""
        return self.history[-limit:]

    def get_entry_by_prompt(self, prompt: str) -> List[Dict]:
        """Get all entries that match the given prompt."""
        return [entry for entry in self.history if entry["prompt"] == prompt]

    def clear_history(self):
        """Clear the entire prompt history."""
        self.history = []
        self._save_history() 