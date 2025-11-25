import os
from dotenv import load_dotenv

load_dotenv()

# Deployment mode
DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "local")  # "local" or "cloud"
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")  # "ollama", "anthropic", "gemini"

# LLM Configuration
if DEPLOYMENT_MODE == "cloud":
    # Use Anthropic, Gemini, or other cloud APIs
    API_KEY = os.getenv("API_KEY", "")
    MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-sonnet-20241022")
else:
    # Use local Ollama
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:70b")
    OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llama3.2-vision:11b")

# OCR Configuration
USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "en")  # English by default

# Grading Configuration
MAX_RUBRIC_ITEMS = int(os.getenv("MAX_RUBRIC_ITEMS", "10"))
DEFAULT_GRADING_TEMPERATURE = float(os.getenv("GRADING_TEMPERATURE", "0.1"))
