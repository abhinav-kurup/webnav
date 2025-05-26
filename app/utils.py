from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import base64
import os
import logging
from datetime import datetime

def setup_logging(name: str = None) -> logging.Logger:
    """Set up logging configuration for the application.
    
    Args:
        name: Optional name for the logger. If not provided, uses the module name.
    
    Returns:
        A configured logger instance.
    """
    # Get the absolute path to the project root
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Create logs directory in project root if it doesn't exist
    logs_dir = os.path.join(project_root, 'logs')
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)
    
    # Create a log file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(logs_dir, f'web_navigator_{timestamp}.log')
    
    # Configure logging if it hasn't been configured yet
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
    
    # Get or create a logger with the specified name
    logger = logging.getLogger(name or __name__)
    return logger

def capture_screenshot(driver) -> bytes:
    """Capture and return a screenshot of the current page."""
    return driver.get_screenshot_as_png()

def extract_dom_elements(driver) -> list:
    """Extract relevant DOM elements with their attributes and multiple selector strategies."""
    elements = []
    
    # Extract clickable elements
    clickable_elements = driver.find_elements(By.CSS_SELECTOR, 
        'button, [role="button"], a, input[type="submit"], input[type="button"]')
    for element in clickable_elements:
        try:
            selectors = _get_all_selectors(element)
            elements.append({
                "type": "clickable",
                "tag": element.tag_name,
                "text": element.text.strip(),
                "id": element.get_attribute("id"),
                "name": element.get_attribute("name"),
                "class": element.get_attribute("class"),
                "selectors": selectors
            })
        except:
            continue

    # Extract input fields
    input_elements = driver.find_elements(By.CSS_SELECTOR, 
        'input[type="text"], input[type="email"], input[type="password"], textarea')
    for element in input_elements:
        try:
            selectors = _get_all_selectors(element)
            elements.append({
                "type": "input",
                "tag": element.tag_name,
                "placeholder": element.get_attribute("placeholder"),
                "id": element.get_attribute("id"),
                "name": element.get_attribute("name"),
                "class": element.get_attribute("class"),
                "selectors": selectors
            })
        except:
            continue

    # Extract links
    links = driver.find_elements(By.TAG_NAME, "a")
    for link in links:
        try:
            selectors = _get_all_selectors(link)
            elements.append({
                "type": "link",
                "text": link.text.strip(),
                "href": link.get_attribute("href"),
                "id": link.get_attribute("id"),
                "class": link.get_attribute("class"),
                "selectors": selectors
            })
        except:
            continue

    return elements

def _get_all_selectors(element) -> dict:
    """Get all possible selector strategies for an element."""
    selectors = {}
    
    # ID selector
    if element.get_attribute("id"):
        selectors["id"] = element.get_attribute("id")
    
    # Name selector
    if element.get_attribute("name"):
        selectors["name"] = element.get_attribute("name")
    
    # CSS selector
    selectors["css"] = _get_css_selector(element)
    
    # XPath selector
    selectors["xpath"] = _get_xpath_selector(element)
    
    # Link text (for anchor tags)
    if element.tag_name == "a" and element.text.strip():
        selectors["link_text"] = element.text.strip()
    
    # Class name
    if element.get_attribute("class"):
        selectors["class_name"] = element.get_attribute("class")
    
    return selectors

def _get_css_selector(element) -> str:
    """Get the best CSS selector for an element."""
    if element.get_attribute("id"):
        return f"#{element.get_attribute('id')}"
    elif element.get_attribute("name"):
        return f"[name='{element.get_attribute('name')}']"
    elif element.get_attribute("class"):
        return f".{element.get_attribute('class').replace(' ', '.')}"
    else:
        return element.tag_name

def _get_xpath_selector(element) -> str:
    """Get a reliable XPath selector for an element."""
    # Try to use ID if available
    if element.get_attribute("id"):
        return f"//*[@id='{element.get_attribute('id')}']"
    
    # Try to use name if available
    if element.get_attribute("name"):
        return f"//*[@name='{element.get_attribute('name')}']"
    
    # Try to use text content for links and buttons
    if element.tag_name in ["a", "button"] and element.text.strip():
        return f"//{element.tag_name}[contains(text(), '{element.text.strip()}')]"
    
    # Fallback to a basic XPath
    return f"//{element.tag_name}"
