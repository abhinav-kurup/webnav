from app.llm_interface import LLMInterface
from app.utils import capture_screenshot, extract_dom_elements
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import re
from typing import List, Dict
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
import json
# Load environment variables
load_dotenv()

# Configure logging
def setup_logging():
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Create a log file with timestamp
    log_file = f'logs/web_navigator_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)

class WebNavigator:
    def __init__(self, driver, llm_interface: LLMInterface):
        self.driver = driver
        self.llm_interface = llm_interface
        self.max_retries = int(os.getenv('BROWSER_MAX_RETRIES', 3))
        self.wait_timeout = int(os.getenv('BROWSER_TIMEOUT', 10))
        self.action_history: List[Dict] = []
        # self.llm_responses: List[Dict] = []
        self.logger = setup_logging()

    def handle_prompt(self, prompt: str):
        self.logger.info(f"Starting new task with prompt: {prompt}")
        
        # Get initial action from LLM
        # initial_action = self.llm_interface.parse_user_prompt(prompt)
        initial_action = {"action": "navigate", "target": "https://www.google.com"}
        self.logger.info(f"Initial action decided: {initial_action}")
        
        # Store the initial LLM response
        # self.llm_responses.append({
        #     "type": "initial_action",
        #     "prompt": prompt,
        #     "response": initial_action
        # })
        
        if initial_action["action"] == "search":
            self.logger.info("Performing Google search")
            # Navigate to Google and perform the search
            self.driver.get("https://www.google.com")
            search_box = WebDriverWait(self.driver, self.wait_timeout).until(
                EC.presence_of_element_located((By.NAME, "q"))
            )
            search_box.send_keys(initial_action["target"])
            search_box.submit()
            
            # Add search action to history
            self.action_history.append({
                "action": "search",
                "query": initial_action["target"],
                "url": "https://www.google.com"
            })
            self.logger.info(f"Search performed with query: {initial_action['target']}")
            
            # Wait for search results and let LLM analyze them
            time.sleep(2)  # Wait for search results to load
            screenshot = capture_screenshot(self.driver)
            dom_elements = extract_dom_elements(self.driver)
            current_url = self.driver.current_url
            page_title = self.driver.title
            
            # Let LLM decide which search result to click
            result_action = self.llm_interface.decide_next_action(
                screenshot, dom_elements, prompt,
                current_url, page_title,
                self.action_history
            )
            self.logger.info(f"Search result action: {result_action}")
            
            # Store the search result LLM response
            # self.llm_responses.append({
            #     "type": "search_result_action",
            #     "prompt": prompt,
            #     "page_content": {
            #         "url": current_url,
            #         "title": page_title,
            #         "dom_elements": dom_elements
            #     },
            #     "response": result_action
            # })
            
            if result_action["action"] == "click":
                self.perform_action(result_action)
                # Add click action to history
                self.action_history.append({
                    "action": "click",
                    "target": result_action["target"],
                    "url": current_url
                })
                self.logger.info(f"Clicked search result: {result_action['target']}")
            else:
                self.logger.error("LLM failed to select a search result")
                raise Exception("LLM failed to select a search result")
        else:
            # Navigate directly to the specified URL
            self.logger.info(f"Navigating directly to: {initial_action['target']}")
            self.driver.get(initial_action["target"])
            # Add navigation action to history
            self.action_history.append({
                "action": "navigate",
                "target": initial_action["target"],
                "url": initial_action["target"]
            })
        
        # Main action loop
        self.logger.info("Starting main action loop")
        retry_count = 0
        final_result = None
        while retry_count < self.max_retries:
            try:
                screenshot = capture_screenshot(self.driver)
                dom_elements = extract_dom_elements(self.driver)
                current_url = self.driver.current_url
                page_title = self.driver.title
                
            
                self.logger.info(f"Current page: {current_url} - {page_title}")
                try:
                    with open('dom.json', 'a') as f:
                        json.dump(dom_elements, f)
                        f.write('\n')
                except Exception as e:
                    self.logger.warning(f"Failed to dom response to file: {str(e)}")
                actions = self.llm_interface.decide_next_action(
                    screenshot, dom_elements, prompt,
                    current_url, page_title,
                    self.action_history
                )
                if actions is None:
                    self.logger.error("No actions returned from LLM")
                    return
                # actions = [
                #     {
                #         "action": "type",
                #         "target": {"strategy": "name", "value": "q"},
                #         "value": "web navigator",
                #         "task_complete": True
                #     },
                    # {
                    #     "action": "click",
                    #     "target": {"strategy": "name", "value": "btnK"},
                    #     "task_complete": True
                    # }
                # ]
                for action in actions:
                # action = {"action": "type", "target": {"strategy": "name", "value": "q"}, "value": "web navigator"}
                    self.logger.info(f"Next action decided: {action}")
                    
                    # Store the LLM response for each action
                    # self.llm_responses.append({
                    #     "type": "next_action",
                    #     "prompt": prompt,
                    #     "page_content": {
                    #         "url": current_url,
                    #         "title": page_title,
                    #         "dom_elements": dom_elements
                    #     },
                    #     "response": action
                    # })
                    
                    if not self._validate_action(action):
                        self.logger.warning("Invalid action received. Retrying...")
                        retry_count += 1
                        continue
                    
                    # Perform the action
                    result = self.perform_action(action)
                    self.logger.info(f"Action performed successfully: {action['action']} on {action['target']}")
                    
                    # Add action to history
                    action_record = {
                        "action": action["action"],
                        "target": action["target"],
                        "url": current_url
                    }
                    if action["action"] == "type":
                        action_record["value"] = action["value"]
                    self.action_history.append(action_record)
                    
                # Check if the task is complete
                    if self._is_task_complete(action, result, prompt):
                        self.logger.info("Task completed successfully")
                        return result
                    
                
                    retry_count = 0  # Reset retry count on successful action
                
            except Exception as e:
                self.logger.error(f"Error during navigation: {str(e)}")
                retry_count += 1
                if retry_count >= self.max_retries:
                    self.logger.error("Maximum retries exceeded")
                    raise Exception("Maximum retries exceeded")
        
        return final_result

    def _is_task_complete(self, action: dict, result: str, task: str) -> bool:
        """Determine if the task is complete based on the action and result."""
        if action.get("task_complete", False):
            self.logger.info("Task marked as complete by action")
            return True
            
            
        return False

    def _validate_action(self, action: dict) -> bool:
        """Validate that the LLM response is a valid action."""
        required_keys = ["action", "target"]
        if not all(key in action for key in required_keys):
            self.logger.warning(f"Missing required keys: {[k for k in required_keys if k not in action]}")
            return False
            
        if action.get("action") not in ["navigate", "click", "type", "wait", "extract"]:
            self.logger.warning(f"Invalid action type: {action.get('action')}")
            return False
            
        target = action.get("target")
        if not isinstance(target, (str, dict)):
            self.logger.warning("Target must be either a string or a dictionary")
            return False
            
        if isinstance(target, dict):
            if "strategy" not in target or "value" not in target:
                self.logger.warning("Target dictionary missing required fields")
                return False
            if target["strategy"] not in ["id", "name", "css", "xpath", "link_text", "partial_link_text", "class_name", "tag_name"]:
                self.logger.warning(f"Invalid selector strategy: {target['strategy']}")
                return False
                
        if action["action"] == "type" and "value" not in action:
            self.logger.warning("Type action missing value")
            return False
            
        return True

    def perform_action(self, action: dict):
        """Perform the action based on the LLM response."""
        action_type = action.get("action")
        selector_info = action.get("target")
        value = action.get("value", "")

        try:
            # Determine the selector strategy and value
            if isinstance(selector_info, dict):
                # If target is a dict, it contains selector strategy and value
                selector_strategy = selector_info.get("strategy", "css")
                selector_value = selector_info.get("value")
            else:
                # If target is a string, use CSS selector by default
                selector_strategy = "css"
                selector_value = selector_info

            # Map selector strategy to Selenium's By
            by_map = {
                "id": By.ID,
                "name": By.NAME,
                "css": By.CSS_SELECTOR,
                "xpath": By.XPATH,
                "link_text": By.LINK_TEXT,
                "partial_link_text": By.PARTIAL_LINK_TEXT,
                "class_name": By.CLASS_NAME,
                "tag_name": By.TAG_NAME
            }

            if selector_strategy not in by_map:
                raise ValueError(f"Invalid selector strategy: {selector_strategy}")

            by = by_map[selector_strategy]

            if action_type == "click":
                self.logger.info(f"Attempting to click element using {selector_strategy}: {selector_value}")
                element = WebDriverWait(self.driver, self.wait_timeout).until(
                    EC.element_to_be_clickable((by, selector_value))
                )
                element.click()
            elif action_type == "type":
                self.logger.info(f"Attempting to type in element using {selector_strategy}: {selector_value}")
                element = WebDriverWait(self.driver, self.wait_timeout).until(
                    EC.presence_of_element_located((by, selector_value))
                )
                element.clear()
                element.send_keys(value)
            elif action_type == "wait":
                self.logger.info(f"Waiting for {selector_value} seconds")
                time.sleep(int(selector_value))
            elif action_type == "extract":
                self.logger.info(f"Attempting to extract text using {selector_strategy}: {selector_value}")
                element = WebDriverWait(self.driver, self.wait_timeout).until(
                    EC.presence_of_element_located((by, selector_value))
                )
                return element.text
            elif action_type == "navigate":
                self.logger.info(f"Navigating to: {selector_value}")
                self.driver.get(selector_value)
                # Wait for page load
                WebDriverWait(self.driver, self.wait_timeout).until(
                    lambda driver: driver.execute_script('return document.readyState') == 'complete'
                )
            
            return "Action completed successfully"
            
        except TimeoutException:
            self.logger.error(f"Timeout waiting for element using {selector_strategy}: {selector_value}")
            raise Exception(f"Timeout waiting for element using {selector_strategy}: {selector_value}")
        except NoSuchElementException:
            self.logger.error(f"Element not found using {selector_strategy}: {selector_value}")
            raise Exception(f"Element not found using {selector_strategy}: {selector_value}")
        except Exception as e:
            self.logger.error(f"Error performing action: {str(e)}")
            raise Exception(f"Error performing action: {str(e)}")

