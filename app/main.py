from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from app.navigator import WebNavigator
from app.llm_interface import LLMInterface
from app.utils import setup_logging
import uvicorn
import os
from dotenv import load_dotenv

load_dotenv()

logger = setup_logging(__name__)

app = FastAPI(title="Web Navigator API")

class PromptRequest(BaseModel):
    prompt: str

@app.post("/execute")
async def handle_navigation(request: PromptRequest):
    """Handle a navigation request by executing the specified prompt."""
    driver = None
    try:
        # browser = os.getenv('BROWSER', 'chrome').lower()
        # browser = "edge"
        browser = "chrome"
        driver = None
        if browser == 'firefox':
            from selenium.webdriver.firefox.options import Options as FirefoxOptions
            firefox_options = FirefoxOptions()
            # if os.getenv('BROWSER_HEADLESS', 'True').lower() == 'true':
                # firefox_options.add_argument("--headless")
            driver = webdriver.Firefox(options=firefox_options)
        elif browser == 'edge':
            from selenium.webdriver.edge.options import Options as EdgeOptions
            edge_options = EdgeOptions()
            # if os.getenv('BROWSER_HEADLESS', 'True').lower() == 'true':
                # edge_options.add_argument("--headless")
            driver = webdriver.Edge(options=edge_options)
        else:  # Default to Chrome
            chrome_options = Options()
            # if os.getenv('BROWSER_HEADLESS', 'True').lower() == 'true':
            #     chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            driver = webdriver.Chrome(options=chrome_options)

        llm_interface = LLMInterface()
        navigator = WebNavigator(driver, llm_interface)

        result = navigator.handle_prompt(request.prompt)

        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error handling navigation request: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if driver:
            try:
                driver.quit()
            except Exception as e:
                logger.error(f"Error closing WebDriver: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
