
import requests
import json
import base64
from typing import List, Dict, Union, Optional
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
import os
import logging
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

class WebAction(BaseModel):
    action: str = Field(description="The action to perform: navigate, click, type, wait, or extract")
    target: Union[str, dict] = Field(description="The target element information with strategy and value, or URL for navigation")
    value: Optional[str] = Field(description="Optional value for type actions", default=None)
    explanation: Optional[str] = Field(description="Explanation of why this action was chosen", default=None)  # Making explanation optional with default=None
    target_achieved: Optional[Union[str, bool]] = Field(description="Status updated when all the targets are achieved", default=False)

class LLMInterface:
    def __init__(self):
        self.api_url = os.getenv('LLM_API_URL', 'http://localhost:11434/api/chat')
        self.model = os.getenv('LLM_MODEL', 'llama3')
        self.parser = PydanticOutputParser(pydantic_object=WebAction)
        self.conversation_history = []
        logger.info(f"Initialized LLMInterface with API URL: {self.api_url} and model: {self.model}")

    def _prepare_prompt(self, prompt: str, page_content: dict, action_history: List[Dict] = None) -> str:
        """Prepare the prompt for the LLM."""
        format_instructions = self.parser.get_format_instructions()
        # Get the last 5 actions for context
        recent_actions = action_history[-5:] if action_history else []
        logger.info(f"prepare prompt action history: {action_history}")
        
        # Format recent actions
        action_context = ""
        if recent_actions:
            action_context = "\nRecent actions taken:\n"
            for i, action in enumerate(recent_actions, 1):
                action_context += f"{i}. {action['action'].upper()}: "
                if isinstance(action['target'], dict):
                    action_context += f"{action['target'].get('strategy', 'unknown')}: {action['target'].get('value', 'unknown')}"
                else:
                    action_context += f"{action['target']}"
                if action.get('value'):
                    action_context += f" with value: {action['value']}"
                action_context += f" at {action.get('url', 'unknown URL')}\n"
        logger.info(f"action context: {action_context}")

        # Structure page information
        page_info = {
            "url": page_content.get("url", ""),
            "title": page_content.get("title", ""),
            "elements": {
                "inputs": [],
                "buttons": [],
                "links": [],
                "others": []
            }
        }

        # Process DOM elements
        if page_content.get("dom_elements"):
            for element in page_content["dom_elements"]:
                element_data = {
                    "text": element.get("text", "").strip(),
                    "id": element.get("id", "").strip(),
                    "name": element.get("name", "").strip(),
                    "class": element.get("class", "").strip(),
                    "tag": element.get("tag", ""),
                    "type": element.get("type", ""),
                    "placeholder": element.get("placeholder", "").strip() if element.get("type") == "input" else "",
                    "href": element.get("href", "").strip() if element.get("type") == "link" else "",
                    "selectors": element.get("selectors", {})
                }

                # Only add elements that have meaningful content
                if any(value for value in element_data.values() if value):
                    if element.get("type") == "input":
                        page_info["elements"]["inputs"].append(element_data)
                    elif element.get("type") == "clickable":
                        page_info["elements"]["buttons"].append(element_data)
                    elif element.get("type") == "link":
                        page_info["elements"]["links"].append(element_data)
                    else:
                        page_info["elements"]["others"].append(element_data)

        # Format the page info for the prompt
        formatted_page_info = f"""
Current page:
URL: {page_info['url']}
Title: {page_info['title']}

Available elements:
"""
        if page_info["elements"]["inputs"]:
            formatted_page_info += "\nInput fields:\n"
            for input_elem in page_info["elements"]["inputs"]:
                formatted_page_info += f"- Input: {input_elem['placeholder'] or 'No placeholder'}"
                if input_elem['id']:
                    formatted_page_info += f" (ID: {input_elem['id']})"
                if input_elem['name']:
                    formatted_page_info += f" (Name: {input_elem['name']})"
                if input_elem['class']:
                    formatted_page_info += f" (Class: {input_elem['class']})"
                if input_elem['selectors']:
                    selectors = ', '.join(f"{k}={v}" for k, v in input_elem['selectors'].items() if v)
                    formatted_page_info += f" [Selectors: {selectors}]"
                formatted_page_info += "\n"

        if page_info["elements"]["buttons"]:
            formatted_page_info += "\nButtons and clickable elements:\n"
            for button in page_info["elements"]["buttons"]:
                formatted_page_info += f"- {button['tag'].upper()}: {button['text'] or 'No text'}"
                if button['id']:
                    formatted_page_info += f" (ID: {button['id']})"
                if button['name']:
                    formatted_page_info += f" (Name: {button['name']})"
                if button['class']:
                    formatted_page_info += f" (Class: {button['class']})"
                if button['selectors']:
                    selectors = ', '.join(f"{k}={v}" for k, v in button['selectors'].items() if v)
                    formatted_page_info += f" [Selectors: {selectors}]"
                formatted_page_info += "\n"

        if page_info["elements"]["links"]:
            formatted_page_info += "\nLinks:\n"
            for link in page_info["elements"]["links"]:
                formatted_page_info += f"- Link: {link['text'] or 'No text'}"
                if link['href']:
                    formatted_page_info += f" -> {link['href']}"
                if link['class']:
                    formatted_page_info += f" (Class: {link['class']})"
                if link['selectors']:
                    selectors = ', '.join(f"{k}={v}" for k, v in link['selectors'].items() if v)
                    formatted_page_info += f" [Selectors: {selectors}]"
                formatted_page_info += "\n"

        return f"""You are an intelligent agent navigating websites step-by-step to accomplish a task. Your job is to examine the current page's visual and structural context and generate the next valid action(s). 

## OBJECTIVE
Your ultimate goal is to complete the following user-defined task:
{prompt}

## CONTEXT YOU'RE GIVEN
{format_instructions}

{formatted_page_info}

{action_context}

Available actions:
1. click : Click an element using a selector.
   Examples:
   {{"action": "click", "target": {{"strategy": "css", "value": "#submit"}}, "explanation": "Clicking the submit button"}}
   {{"action": "click", "target": {{"strategy": "xpath", "value": "//button[text()='Continue']"}}, "explanation": "Clicking the continue button"}}

2. type : Type text into an input field.
   Example:
   {{"action": "type", "target": {{"strategy": "name", "value": "email"}}, "value": "example@example.com", "explanation": "Typing in the email"}}

3. wait : Wait for a given number of seconds.
   Example:
   {{"action": "wait", "target": "5", "explanation": "Waiting for content to load"}}

4. extract : Extract text from a specified element.
   Example:
   {{"action": "extract", "target": {{"strategy": "class", "value": "price"}}, "explanation": "Extracting the price text"}}

5. navigate : Go to a specific URL.
   Example:
   {{"action": "navigate", "target": "https://example.com", "explanation": "Navigating to the example site"}}

## RULES FOR ACTIONS
- Use the most specific and reliable selector (prefer ID or name).
- DO NOT REPEAT any action already in the prior_actions list.
- If an action failed, try a different strategy.
- DO NOT perform actions that **change the structure/content of the page** unless it's the final action of the step.
- Only select actions possible on the current page.
- Always include a clear, concise explanation for your action.
- Include `"task_complete": true` in the last object only if the task has been successfully completed.

Output:
Return only a valid JSON object with:
- action
- target (with strategy and value)
- value (if action is type)
- explanation

Example 1 (Single action):
[{{
  "action": "click",
  "target": {{ "strategy": "css", "value": "#submit" }},
  "explanation": "Clicking the submit button to proceed"
}}]

Example 2 (Multiple actions):
[
    {{
        "action": "type",
        "target": {{"strategy": "name", "value": "q"}},
        "value": "web navigator",
        "explanation": "Typing search query"
    }},
    {{
        "action": "click",
        "target": {{"strategy": "name", "value": "btnK"}},
        "explanation": "Clicking search button",
        "task_complete": true
    }}
]"""

    def _send_to_llm(self, prompt: str) -> Union[dict, List[dict]]:
        """
        Send the prompt to the LLM and retrieve the JSON response using chat API.
        Returns either a single action dict or a list of action dicts.
        """
        try:
            logger.info("Entering send to llm")
            logger.debug(f"Sending prompt to LLM: {prompt[:100]}...")
            
            # Prepare messages for chat API
            messages = [
                {"role": "system", "content": "You are a web navigation assistant that responds with structured JSON actions."},
                *self.conversation_history,
                {"role": "user", "content": prompt}
            ]
            
            response = requests.post(self.api_url, json={
                "model": self.model,
                "messages": messages,
                "stream": False
            })
            try:
                with open('prompt.json', 'a') as f:
                    json.dump(messages, f)
                    f.write('\n')
            except Exception as e:
                logger.warning(f"Failed to log response to file: {str(e)}")
            
            # Append response to response.json file
            try:
                with open('response.json', 'a') as f:
                    json.dump(response.json(), f)
                    f.write('\n')
            except Exception as e:
                logger.warning(f"Failed to log response to file: {str(e)}")
            
            # Get the response text and extract JSON
            response_data = response.json()
            response_text = response_data.get("message", {}).get("content", "").strip()
            try:
                with open('res.json', 'a') as f:
                    json.dump(response_text, f)
                    f.write('\n')
            except Exception as e:
                logger.warning(f"Failed to log response to file: {str(e)}")
            
            
            if not response_text:
                raise ValueError("Empty response from LLM")
                
            logger.debug(f"Raw LLM response: {response_text[:200]}...")
            
            # Update conversation history
            self.conversation_history.append({"role": "user", "content": prompt})
            self.conversation_history.append({"role": "assistant", "content": response_text})
            
            # Keep only last 10 messages to prevent context window overflow
            if len(self.conversation_history) > 10:
                self.conversation_history = self.conversation_history[-10:]
            
            return self._parse_response(response_text)
        except Exception as e:
                logger.error(f"Failed to get LLM response: {e}")
                raise ValueError(f"Failed to get LLM response: {e}")




    def _parse_response(self, response_text: str) -> Union[dict, List[dict]]:
            # Try to parse the response
            try:
                # First try to parse as JSON
                try:
                    actions = json.loads(response_text)
                except json.JSONDecodeError:
                    # If not valid JSON, try to extract JSON from the text
                    json_start = response_text.find("[")
                    if json_start == -1:
                        json_start = response_text.find("{")
                    if json_start == -1:
                        raise ValueError("No JSON object found in response")
                    json_str = response_text[json_start:]
                    actions = json.loads(json_str)
                
                # Handle both single action and multiple actions
                if isinstance(actions, list):
                    if not actions:
                        raise ValueError("Empty action list received")
                    # Process all actions in the list
                    processed_actions = []
                    for action in actions:
                        # Validate each action
                        if not isinstance(action, dict):
                            raise ValueError(f"Action is not a dictionary: {action}")
                        if "action" not in action:
                            raise ValueError(f"Action missing 'action' field: {action}")
                        if "target" not in action:
                            raise ValueError(f"Action missing 'target' field: {action}")
                        
                        # Add missing fields with defaults
                        if "explanation" not in action:
                            action["explanation"] = None
                        if "value" not in action:
                            action["value"] = None
                        if "target_achieved" not in action:
                            action["target_achieved"] = False
                            
                        processed_actions.append(action)
                    
                    return processed_actions
                else:
                    # Single action object
                    if not isinstance(actions, dict):
                        raise ValueError("Response is not a dictionary")
                    if "action" not in actions:
                        raise ValueError("Response missing 'action' field")
                    if "target" not in actions:
                        raise ValueError("Response missing 'target' field")
                    
                    # Add missing fields with defaults
                    if "explanation" not in actions:
                        actions["explanation"] = None
                    if "value" not in actions:
                        actions["value"] = None
                    if "target_achieved" not in actions:
                        actions["target_achieved"] = False
                    
                    return actions
                
            except Exception as e:
                logger.error(f"Failed to parse LLM response: {str(e)}")
                logger.error(f"Raw response: {response_text}")
                raise ValueError(f"Failed to parse LLM response: {str(e)}")
                
        
    def _validate_response(self, response: dict) -> bool:
        """
        Validate the response from LLM to ensure it's actionable.
        """
        if not isinstance(response, dict):
            return False

        if "action" not in response or "target" not in response:
            return False

        if response["action"] not in ["navigate", "click", "type", "wait", "extract"]:
            return False

        if response["action"] == "type" and "value" not in response:
            return False

        return True

    def parse_user_prompt(self, user_prompt: str) -> dict:
        """
        Handle initial prompt and decide whether to navigate directly or search.
        """
        initial_prompt = f"""
        You are an intelligent web automation agent. Your goal is to help complete the user's task step-by-step on websites.

        User Task: {user_prompt}

        Respond with a SINGLE JSON object describing the initial action to take.

        Return format:
        {{
        "action": "navigate" | "search",
        "target": "<URL or search query>",
        "explanation": "<why you chose this action>"
        }}

        Guidelines:
        - If the task mentions a specific website, use "navigate" action with the website URL
        - If no specific website is mentioned, use "search" action with a relevant search query
        - For search queries, be specific and include relevant keywords
        - ALWAYS include an explanation field
        - DO NOT include any explanation outside the JSON object
        - Do not include any special characters which will cause errors in the JSON object
        """

        response = self._send_to_llm(initial_prompt)
        if not isinstance(response, dict) or "action" not in response or "target" not in response:
            raise ValueError("LLM returned an invalid initial action")

        if response["action"] not in ["navigate", "search"]:
            raise ValueError("Invalid initial action type")

        return response

    def decide_next_action(self, screenshot: bytes, dom_elements: list, prompt: str, current_url: str = None, page_title: str = None, action_history: List[Dict] = None) -> Union[dict, List[dict]]:
        """Decide the next action(s) based on the prompt and page content."""
        try:
            # Prepare the prompt
            logger.info(f"Deciding next action for prompt:{prompt}")
            
            full_prompt = self._prepare_prompt(prompt, {
                "url": current_url,
                "title": page_title,
                "dom_elements": dom_elements
            }, action_history)
            if full_prompt is None:
                logger.error("Full prompt is None")
            logger.info(f"Full prompt: {full_prompt}")
            # Get response from LLM
            response = self._send_to_llm(full_prompt)
            
            # Handle both single action and list of actions
            if isinstance(response, list):
                # Validate each action in the list
                for action in response:
                    if not self._validate_response(action):
                        raise ValueError(f"Invalid action format in list: {action}")
                return response
            else:
                # Validate single action
                if not self._validate_response(response):
                    raise ValueError(f"Invalid action format: {response}")
                return response
                
        except Exception as e:
            logger.error(f"Error deciding next action: {str(e)}")
            # Return a fallback action
            return None
            # return [{
            #     "action": "wait",
            #     "target": "5",
            #     "explanation": f"Error occurred: {str(e)}. Waiting before retry."
            # }]