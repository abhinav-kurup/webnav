import requests
import json
import base64
from typing import List, Dict, Union, Optional
from langchain_core.output_parsers import PydanticOutputParser
from langchain_core.prompts import PromptTemplate
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from app.utils import setup_logging

# Load environment variables
load_dotenv()

# Configure logging
logger = setup_logging(__name__)

class WebAction(BaseModel):
    action: str = Field(description="The action to perform: navigate, click, type, wait, or extract")
    target: Union[str, dict] = Field(description="The target element information with strategy and value, or URL for navigation")
    value: Optional[str] = Field(description="Optional value for type actions", default=None)
    explanation: Optional[str] = Field(description="Explanation of why this action was chosen", default=None)
    target_achieved: Optional[Union[str, bool]] = Field(description="Status updated when all the targets are achieved", default=False)

class LLMInterface:
    def __init__(self):
        self.api_url = os.getenv('LLM_API_URL', 'http://localhost:11434/api/generate')
        self.model = os.getenv('LLM_MODEL', 'llama3')
        self.parser = PydanticOutputParser(pydantic_object=WebAction)
        logger.info(f"Initialized LLMInterface with API URL: {self.api_url} and model: {self.model}")

    def _prepare_prompt(self, prompt: str, page_content: dict, action_history: List[Dict] = None) -> str:
        """Prepare the prompt for the LLM."""
        format_instructions = self.parser.get_format_instructions()
        recent_actions = action_history[-5:] if action_history else []
        logger.info(f"prepare prompt action history: {action_history}")
        
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
            "elements": self._process_dom_elements(page_content.get("dom_elements", []))
        }

        formatted_page_info = self._format_page_info(page_info)
        # - {format_instructions}: Output format

        return f""" You are a step-by-step website navigation agent. Your goal is to complete the following task:

>> OBJECTIVE: {prompt}

You are provided with:
- {formatted_page_info}: Structured elements on the current page
- {action_context}: List of previously taken actions


---

## Available Actions
1. **click** - Click an element
   - Example: {"action": "click", "target": {"strategy": "css", "value": "#submit"}, "explanation": "Clicking the submit button"}

2. **type** - Type into an input field
   - Example: {"action": "type", "target": {"strategy": "name", "value": "email"}, "value": "user@example.com", "explanation": "Typing in the email"}

3. **wait** - Pause for a few seconds
   - Example: {"action": "wait", "target": "5", "explanation": "Waiting for the page to load"}

4. **extract** - Get text from an element
   - Example: {"action": "extract", "target": {"strategy": "class", "value": "price"}, "explanation": "Extracting price info"}

5. **navigate** - Go to a different URL
   - Example: {"action": "navigate", "target": "https://example.com", "explanation": "Navigating to the example site"}

---

## Action Guidelines
- Use the most **precise and reliable** selector (prefer ID > name > class > xpath).
- **Do not repeat** actions from `action_context`.
- Avoid actions that **change the page structure** unless completing the task.
- Choose only actions that are valid on the **current page**.
- Provide a **clear explanation** for each action.
- If task is fully completed, add `"task_complete": true` to the final action.

---

## Output Format
- A **JSON array** of 1 or more actions.
- Each object: `action`, `target`, `value` (for type), `explanation`
- No extra text. Return only the JSON.

---

## Example (Multi-action):
[
  {
    "action": "type",
    "target": {"strategy": "name", "value": "q"},
    "value": "web navigator",
    "explanation": "Typing the search query"
  },
  {
    "action": "click",
    "target": {"strategy": "name", "value": "btnK"},
    "explanation": "Clicking the search button",
    "task_complete": true
  }
]
"""


    def _process_dom_elements(self, elements: List[Dict]) -> Dict:
        """Process DOM elements into a structured format."""
        processed = {
            "inputs": [],
            "buttons": [],
            "links": [],
            "others": []
        }
        
        for element in elements:
            element_data = {
                "text": str(element.get("text", "")).strip(),
                "id": str(element.get("id", "")).strip(),
                "name": str(element.get("name", "")).strip(),
                "class": str(element.get("class", "")).strip(),
                "tag": element.get("tag", ""),
                "type": element.get("type", ""),
                "placeholder": str(element.get("placeholder", "")).strip() if element.get("type") == "input" else "",
                "href": str(element.get("href", "")).strip() if element.get("type") == "link" else "",
                "selectors": element.get("selectors", {})
            }

            if any(value for value in element_data.values() if value):
                if element.get("type") == "input":
                    processed["inputs"].append(element_data)
                elif element.get("type") == "clickable":
                    processed["buttons"].append(element_data)
                elif element.get("type") == "link":
                    processed["links"].append(element_data)
                else:
                    processed["others"].append(element_data)
        
        return processed

    def _format_page_info(self, page_info: Dict) -> str:
        """Format page information for the prompt."""
        formatted = f"\nCurrent page: {page_info['url']} - {page_info['title']}\n\nAvailable elements:"
        
        if page_info["elements"]["inputs"]:
            formatted += "\nInput fields:"
            for input_elem in page_info["elements"]["inputs"]:
                formatted += self._format_element(input_elem, "Input")
        
        if page_info["elements"]["buttons"]:
            formatted += "\nButtons and clickable elements:"
            for button in page_info["elements"]["buttons"]:
                formatted += self._format_element(button, button['tag'].upper())
        
        if page_info["elements"]["links"]:
            formatted += "\nLinks:"
            for link in page_info["elements"]["links"]:
                formatted += self._format_element(link, "Link")
        
        return formatted

    def _format_element(self, element: Dict, element_type: str) -> str:
        """Format a single element for the prompt."""
        formatted = f"\n- {element_type}: {element['text'] or 'No text'}"
        
        if element['id']:
            formatted += f" (ID: {element['id']})"
        if element['name']:
            formatted += f" (Name: {element['name']})"
        if element['class']:
            formatted += f" (Class: {element['class']})"
        if element['placeholder']:
            formatted += f" [Placeholder: {element['placeholder']}]"
        if element['href']:
            formatted += f" -> {element['href']}"
        if element['selectors']:
            selectors = ', '.join(f"{k}={v}" for k, v in element['selectors'].items() if v)
            formatted += f" [Selectors: {selectors}]"
        
        return formatted

    def _send_to_llm(self, prompt: str) -> Union[dict, List[dict]]:
        """Send prompt to LLM and get response."""
        try:
            headers = {"Content-Type": "application/json"}
            data = {
                "model": self.model,
                "prompt": prompt,
                "stream": False
            }
            
            response = requests.post(self.api_url, headers=headers, json=data)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Raw LLM response: {result}")
            
            # Extract the response string and parse it as JSON
            response_str = result.get("response", "")
            if not response_str:
                logger.error("Empty response from LLM")
                raise ValueError("Empty response from LLM")
            
            # Parse the response string as JSON
            try:
                content = json.loads(response_str)
                logger.info(f"Parsed response content: {content}")
                verified_response = self._parse_response(content)
                logger.info(f"verified response: {verified_response}")
                return verified_response
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response string as JSON: {str(e)}")
                raise
            
        except Exception as e:
            logger.error(f"Error sending request to LLM: {str(e)}")
            raise

    def _parse_response(self, response_data: Union[dict, List[dict]]) -> Union[dict, List[dict]]:
        """Parse the LLM response into structured actions."""
        try:
            logger.info(f"entered parse response")
            # If response is empty or just "[]", return a default navigation action
            if not response_data or response_data == []:
                logger.warning("Empty response from LLM, returning default navigation")
                return [{
                    "action": "navigate",
                    "target": "https://www.google.com",
                    "explanation": "Default navigation to Google search"
                }]
            
            # Validate the actions
            logger.info(f"response_data: {response_data}")
            if isinstance(response_data, list):
                for action in response_data:
                    if not self._validate_response(action):
                        raise ValueError(f"Invalid action format: {action}")
                logger.info("response_data is a list")
                return response_data
            elif isinstance(response_data, dict):
                if not self._validate_response(response_data):
                    raise ValueError(f"Invalid action format: {response_data}")
                logger.info("response_data is a dict")
                return [response_data]
            else:
                logger.info("response_data is not a list or dict")
                raise ValueError("Response must be a JSON object or array")
        except Exception as e:
            logger.error(f"Error processing LLM response: {str(e)}")
            # Return default navigation on error
            return [{
                "action": "navigate",
                "target": "https://www.google.com",
                "explanation": "Default navigation after error"
            }]

    def _validate_response(self, response: dict) -> bool:
        """Validate the structure of an action response."""
        required_fields = ["action", "target"]
        return all(field in response for field in required_fields)

    def decide_next_action(self, screenshot: bytes, dom_elements: list, prompt: str, current_url: str = None, page_title: str = None, action_history: List[Dict] = None) -> Union[dict, List[dict]]:
        """Decide the next action based on the current page state."""
        page_content = {
            "url": current_url,
            "title": page_title,
            "dom_elements": dom_elements
        }
        
        formatted_prompt = self._prepare_prompt(prompt, page_content, action_history)
        return self._send_to_llm(formatted_prompt)

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
        logger.info(f"response of main: {response}")

        return response