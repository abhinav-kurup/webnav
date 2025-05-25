from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from app.navigator import WebNavigator
from app.llm_interface import LLMInterface
import uvicorn
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Web Navigator API")

class PromptRequest(BaseModel):
    prompt: str

@app.post("/execute")
async def handle_navigation(request: PromptRequest):
    try:
        # Initialize Chrome options
        chrome_options = Options()
        if os.getenv('BROWSER_HEADLESS', 'True').lower() == 'true':
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
                                                               
        # Initialize WebDriver     
        driver = webdriver.Chrome(options=chrome_options)
        
        # Initialize LLM interface and WebNavigator
        llm_interface = LLMInterface()
        navigator = WebNavigator(driver, llm_interface)
        
        # Handle the navigation task
        result = navigator.handle_prompt(request.prompt)
        
        # Clean up
        # driver.quit()
        
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
