# LLM Client for AI Marker - supports local Ollama and cloud providers

import httpx
import json
import base64
from typing import Dict, Tuple, Optional
from anthropic import Anthropic
from google import genai

from config import DEPLOYMENT_MODE, LLM_PROVIDER
if DEPLOYMENT_MODE == "local":
    from config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_VISION_MODEL
else:
    OLLAMA_BASE_URL = None
    OLLAMA_MODEL = None
    OLLAMA_VISION_MODEL = None
    from config import API_KEY, MODEL_NAME

from prompts import (
    AI_MARKER_SYSTEM_PROMPT,
    get_rubric_extraction_prompt,
    get_answer_extraction_prompt,
    get_question_extraction_prompt
)

class OllamaClient:
    """Client for interacting with local Ollama or cloud LLM providers"""
    
    def __init__(self):
        """Initialize LLM client based on config.py settings"""
        self.deployment_mode = DEPLOYMENT_MODE
        self.timeout = 1200.0  # 10 minutes for complex grading
        self.provider = LLM_PROVIDER
        
        if self.deployment_mode == "cloud":
            # Cloud deployment
            self.api_key = API_KEY
            if not self.api_key:
                raise ValueError("API_KEY is required for cloud deployment. Check your .env file.")
            
            if self.provider == "anthropic":
                self.anthropic_client = Anthropic(api_key=self.api_key)
            elif self.provider == "gemini":
                self.gemini_client = genai.Client(api_key=self.api_key)
            
            self.model = MODEL_NAME
            print(f"🌐 Using cloud model: {self.model}")
        else:
            # Local deployment - Ollama
            self.base_url = OLLAMA_BASE_URL
            self.model = OLLAMA_MODEL
            self.vision_model = OLLAMA_VISION_MODEL
            print(f"💻 Using local Ollama: {self.model}")
            print(f"👁️  Vision model: {self.vision_model}")
    
    def _make_request(self, prompt: str, system: str, temperature: float = 0.1,
                     max_tokens: int = 2000, response_format: str = None) -> str:
        """Make request to appropriate LLM provider"""
        if self.provider == "ollama":
            return self._make_ollama_request(prompt, system, temperature, max_tokens, response_format)
        elif self.provider == "anthropic":
            return self._make_anthropic_request(prompt, system, temperature, max_tokens)
        else:
            return self._make_gemini_request(prompt, system, temperature, max_tokens)
    
    def _make_ollama_request(self, prompt: str, system: str, temperature: float,
                            max_tokens: int, response_format: str = None) -> str:
        """Make request to local Ollama"""
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "temperature": temperature,
            "top_p": 0.9,
            "num_predict": max_tokens,
            "stream": False
        }
        
        if response_format == "json":
            payload["format"] = "json"
        
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/api/generate",
                    json=payload
                )
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
        except httpx.TimeoutException:
            raise Exception("Request timed out. Grading may take longer for complex submissions.")
        except httpx.ConnectError:
            raise Exception("Cannot connect to Ollama. Please ensure Ollama is running.")
        except Exception as e:
            raise Exception(f"Error communicating with Ollama: {str(e)}")
    
    def _make_anthropic_request(self, prompt: str, system: str, temperature: float,
                               max_tokens: int) -> str:
        """Make request to Anthropic Claude"""
        try:
            message = self.anthropic_client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                system=system,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            raise Exception(f"Error communicating with Anthropic: {str(e)}")
    
    def _make_gemini_request(self, prompt: str, system: str, temperature: float,
                            max_tokens: int) -> str:
        """Make request to Google Gemini"""
        try:
            full_prompt = f"{system}\n\nUser: {prompt}"
            response = self.gemini_client.models.generate_content(
                model=self.model,
                contents=full_prompt,
                config={
                    "temperature": temperature,
                    "max_output_tokens": max_tokens
                }
            )
            return response.text
        except Exception as e:
            raise Exception(f"Error communicating with Gemini: {str(e)}")
    
    def extract_rubric_structure(self, rubric_text: str) -> Dict:
        """
        Extract structured rubric from plain text
        
        Args:
            rubric_text: Raw rubric text
        
        Returns:
            Structured rubric dictionary
        """
        system_prompt = get_rubric_extraction_prompt()
        prompt = f"""Rubric Text:
{rubric_text}

Extract this into structured JSON format following the specified schema."""
        
        response = self._make_request(
            prompt=prompt,
            system=system_prompt,
            temperature=0.1,
            max_tokens=1500,
            response_format="json"
        )
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # Fallback: try to fix common JSON issues
            response = response.strip()
            if not response.startswith("{"):
                response = "{" + response
            if not response.endswith("}"):
                response = response + "}"
            return json.loads(response)
    
    def extract_text_from_image(self, image_path: str) -> str:
        """
        Extract text from image using vision model
        
        Args:
            image_path: Path to image file
        
        Returns:
            Extracted text
        """
        # Read and encode image
        with open(image_path, 'rb') as img_file:
            img_base64 = base64.b64encode(img_file.read()).decode('utf-8')
        
        system_prompt = get_answer_extraction_prompt()
        
        if self.provider == "ollama":
            # Use Ollama vision model
            payload = {
                "model": self.vision_model,
                "prompt": "Extract all text from this image. Transcribe exactly what you see, preserving structure and formatting.",
                "images": [img_base64],
                "stream": False
            }
            
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.base_url}/api/generate",
                        json=payload
                    )
                    response.raise_for_status()
                    result = response.json()
                    return result.get("response", "")
            except Exception as e:
                raise Exception(f"Error extracting text with vision model: {str(e)}")
        else:
            # Cloud providers would use their vision APIs
            # This is a placeholder - actual implementation depends on provider
            raise NotImplementedError("Vision extraction for cloud providers not yet implemented")
    
    def grade_submission(self, student_answer: str, question: str, 
                        rubric: Dict) -> Dict:
        """
        Grade a student submission against rubric
        
        Args:
            student_answer: Extracted text from student's answer
            question: The assignment/exam question
            rubric: Structured rubric dictionary
        
        Returns:
            Grading result dictionary with scores and feedback
        """
        system_prompt = AI_MARKER_SYSTEM_PROMPT
        
        # Check rubric type
        rubric_type = rubric.get("rubric_type", "simple")
        
        if rubric_type == "banded":
            grading_instructions = """
        ## Banded Rubric Instructions

        **HOW BANDED RUBRICS WORK:**
        Each criterion has score bands (0-49, 50-59, 60-69, 70-79, 80-89, 90-100).
        These bands represent performance quality AS A PERCENTAGE.

        **YOUR JOB:**
        1. For each criterion, find which band describes the student's work
        2. Pick a percentage from that band (use middle if unsure: 55 for 50-59, 65 for 60-69, 75 for 70-79, etc.)
        3. Convert percentage to points: (percentage ÷ 100) × max_points

        **EXAMPLE:**
        - Criterion: "Literature Review" (max_points: 40)
        - Student work matches: "60-69: Moderate literature review"
        - Choose: 65% (middle of 60-69 band)
        - Calculate: 65 ÷ 100 × 40 = 26 points
        - Result: awarded_points = 26

        **IMPORTANT:**
        - Use middle of band as default (55, 65, 75, 85, 95)
        - NEVER put the percentage as the awarded_points
        - ALWAYS multiply by max_points to get actual points
        """


        else:
            grading_instructions = """
    ## Simple Rubric Grading Instructions
    Each criterion has a maximum point value. Determine if the criterion is satisfied
    and award full or partial points based on the rubric requirements.
    """
        
        prompt = f"""# Grading Task

    {grading_instructions}

    ## Question (if provided)
    {question}

    ## Student Answer
    {student_answer}

    ## Grading Rubric
    {json.dumps(rubric, indent=2)}

    ## Your Task
    Evaluate this student answer against the rubric following these steps:

    1. Read the rubric structure carefully (banded or simple)
    2. For banded rubrics: Identify which band each criterion falls into
    3. For simple rubrics: Determine if each criterion is satisfied
    4. Provide specific evidence from the student's answer
    5. Calculate total score accurately
    6. Generate constructive feedback

    ## Critical Requirements
    - Quote specific parts of student answer as evidence
    - Be fair but maintain standards
    - For banded rubrics: Use the full score range, not just minimum
    - Provide actionable improvement suggestions
    - Ensure arithmetic is correct

    Return your evaluation in the specified JSON format."""

        
        response = self._make_request(
            prompt=prompt,
            system=system_prompt,
            temperature=0.1,  # Low temperature for consistency
            max_tokens=3000,
            response_format="json"
        )
        
        try:
            grading_result = json.loads(response)
        except json.JSONDecodeError:
            # Try to fix and re-parse
            response = response.strip()
            grading_result = json.loads(response)
        
        # Validate and recalculate scores (don't trust LLM arithmetic)
        grading_result = self._validate_grading_result(grading_result, rubric)
        
        return grading_result
    
    def _validate_grading_result(self, result: Dict, rubric: Dict) -> Dict:
        """Validate grading result and fix any arithmetic errors"""
        
        # Recalculate total score
        calculated_total = sum(
            criterion.get("awarded_points", 0)
            for criterion in result.get("criteria_evaluation", [])
        )
        
        # Calculate max score from rubric
        rubric_type = rubric.get("rubric_type", "simple")
        
        if rubric_type == "banded":
            # For banded rubrics, sum the max_points from each criterion
            max_score = sum(
                criterion.get("max_points", 0)
                for criterion in rubric.get("criteria", [])
            )
        else:
            # For simple rubrics
            max_score = rubric.get("total_points", 0)
            if max_score == 0:
                max_score = sum(
                    criterion.get("max_points", 0)
                    for criterion in rubric.get("criteria", [])
                )
        
        # Override LLM calculations with correct arithmetic
        result["total_score"] = calculated_total
        result["max_score"] = max_score
        result["percentage"] = round((calculated_total / max_score * 100), 2) if max_score > 0 else 0
        
        # Add metadata
        result["model_used"] = self.model
        result["grading_method"] = "rubric_based_llm"
        result["rubric_type"] = rubric_type
        
        return result
