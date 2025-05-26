from app.llm_interface import LLMInterface
from app.utils import capture_screenshot, extract_dom_elements, setup_logging
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
from typing import List, Dict, Union
import os
from datetime import datetime
from dotenv import load_dotenv
import json
# Load environment variables
load_dotenv()

class WebNavigator:
    def __init__(self, driver, llm_interface: LLMInterface):
        self.driver = driver
        self.llm_interface = llm_interface
        self.max_retries = int(os.getenv('BROWSER_MAX_RETRIES', 3))
        self.wait_timeout = int(os.getenv('BROWSER_TIMEOUT', 10))
        self.action_history: List[Dict] = []
        # self.llm_responses: List[Dict] = []
        self.logger = setup_logging(__name__)

    def handle_prompt(self, prompt: str):
        """Handle the user's prompt and execute the necessary actions."""
        self.logger.info(f"Starting new task with prompt: {prompt}")
        
        try:
            # Get initial action from LLM
            initial_action = self.llm_interface.parse_user_prompt(prompt)
            initial_action = initial_action[0]
            self.logger.info(f"Initial action decided: {initial_action}")
            
            # Execute initial navigation
            if initial_action["action"] == "navigate":
                self.driver.get(initial_action["target"])
                self.action_history.append({
                    "action": "navigate",
                    "target": initial_action["target"],
                    "url": initial_action["target"]
                })
            elif initial_action["action"] == "search":
                self.driver.get(f"https://www.google.com/search?q={initial_action['target']}")
                self.action_history.append({
                    "action": "search",
                    "target": initial_action["target"],
                    "url": f"https://www.google.com/search?q={initial_action['target']}"
                })
            else:
                raise ValueError("Initial action must be navigation")
            
            # Main action loop
            retry_count = 0
            while retry_count < self.max_retries:
                try:
                    # Capture current page state
                    screenshot = capture_screenshot(self.driver)
                    dom_elements = extract_dom_elements(self.driver)
                    current_url = self.driver.current_url
                    page_title = self.driver.title
                    
                    self.logger.info(f"Current page: {current_url} - {page_title}")
                    
                    # Get next actions from LLM
                    actions = self.llm_interface.decide_next_action(
                        screenshot, dom_elements, prompt,
                        current_url, page_title,
                        self.action_history
                    )
                    
                    if not actions:
                        self.logger.error("No actions returned from LLM")
                        break
                    
                    # Execute each action
                    for action in actions:
                        self.logger.info(f"Executing action: {action}")
                        
                        if not self._validate_action(action):
                            self.logger.warning("Invalid action received. Retrying...")
                            retry_count += 1
                            continue
                        
                        result = self.perform_action(action)
                        self.logger.info(f"Action performed successfully: {action['action']}")
                        
                        # Add action to history
                        action_record = {
                            "action": action["action"],
                            "target": action["target"],
                            "url": current_url,
                            "result": result
                        }
                        if "value" in action:
                            action_record["value"] = action["value"]
                        self.action_history.append(action_record)
                        
                        # Check if task is complete
                        if action.get("target_achieved", False):
                            self.logger.info("Task completed successfully")
                            return result
                    
                    # Reset retry count on successful action
                    retry_count = 0
                    
                except Exception as e:
                    self.logger.error(f"Error in action loop: {str(e)}")
                    retry_count += 1
                    if retry_count >= self.max_retries:
                        raise
            
            return "Task completed with maximum retries"
            
        except Exception as e:
            self.logger.error(f"Error handling prompt: {str(e)}")
            raise

    def _validate_action(self, action: dict) -> bool:
        """Validate that an action has the required fields and valid values."""
        if not isinstance(action, dict):
            return False
        
        required_fields = ["action", "target"]
        if not all(field in action for field in required_fields):
            return False
        
        valid_actions = ["navigate", "click", "type", "wait", "extract"]
        if action["action"] not in valid_actions:
            return False
        
        if action["action"] == "type" and "value" not in action:
            return False
        
        return True

    def perform_action(self, action: dict):
        """Execute a single action on the web page."""
        try:
            if action["action"] == "navigate":
                self.driver.get(action["target"])
                return f"Navigated to {action['target']}"
                
            elif action["action"] == "click":
                element = self._find_element(action["target"])
                element.click()
                return f"Clicked element: {action['target']}"
                
            elif action["action"] == "type":
                element = self._find_element(action["target"])
                element.clear()
                element.send_keys(action["value"])
                return f"Typed '{action['value']}' into {action['target']}"
                
            elif action["action"] == "wait":
                time.sleep(float(action["target"]))
                return f"Waited for {action['target']} seconds"
                
            elif action["action"] == "extract":
                element = self._find_element(action["target"])
                return element.text
                
            else:
                raise ValueError(f"Unknown action: {action['action']}")
                
        except Exception as e:
            self.logger.error(f"Error performing action: {str(e)}")
            raise

    def _find_element(self, target: Union[str, dict]) -> webdriver.remote.webelement.WebElement:
        """Find an element on the page using the specified target information."""
        if isinstance(target, str):
            # Direct selector
            return WebDriverWait(self.driver, self.wait_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, target))
            )
        else:
            # Structured selector with strategy
            strategy = target.get("strategy", "css")
            value = target.get("value")
            
            if not value:
                raise ValueError("No selector value provided")
            
            by_map = {
                "id": By.ID,
                "name": By.NAME,
                "class": By.CLASS_NAME,
                "tag": By.TAG_NAME,
                "link": By.LINK_TEXT,
                "partial": By.PARTIAL_LINK_TEXT,
                "css": By.CSS_SELECTOR,
                "xpath": By.XPATH
            }
            
            if strategy not in by_map:
                raise ValueError(f"Invalid selector strategy: {strategy}")
            
            return WebDriverWait(self.driver, self.wait_timeout).until(
                EC.presence_of_element_located((by_map[strategy], value))
            )

