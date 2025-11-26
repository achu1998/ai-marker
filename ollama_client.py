import httpx
import json
import base64
import re
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
            rubric = json.loads(response)
            
            # Validate rubric structure
            if not isinstance(rubric, dict):
                raise ValueError("Rubric must be a dictionary")
            
            # Check for required top-level fields
            if "rubric_type" not in rubric:
                print("WARNING: Rubric missing rubric_type, assuming 'simple'")
                rubric["rubric_type"] = "simple"
            
            if "criteria" not in rubric or not isinstance(rubric.get("criteria"), list):
                raise ValueError("Rubric must have criteria array")
            
            if len(rubric["criteria"]) == 0:
                raise ValueError("Rubric has no criteria defined")
            
            # Check totalpoints exists and is numeric
            if "total_points" not in rubric:
                print("WARNING: Computing total_points from criteria")
                rubric["total_points"] = sum(c.get("max_points", 0) for c in rubric["criteria"])
            
            print(f"Rubric extracted successfully: {len(rubric['criteria'])} criteria, {rubric['total_points']} total points")
            return rubric
            
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse rubric extraction: {str(e)}")
            print(f"Response preview: {response[:300]}")
            # Return fallback rubric
            return {
                "rubric_type": "simple",
                "criteria": [],
                "total_points": 0,
                "error": "Failed to extract rubric"
            }

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

    def normalize_grading_structure(self, result: Dict, rubric: Dict) -> Dict:
        """Normalize LLM response to standard grading structure
        
        Handles various field name variations from different LLMs
        Maps "score" to "awarded_points", handles singular/plural variations, etc.
        """
        
        # Step 1: Find and normalize criteria_evaluation field
        print("STEP 1: Normalizing criteria_evaluation field")
        criteria_eval = None
        
        # Check for correct field name first
        if "criteria_evaluation" in result and isinstance(result["criteria_evaluation"], list):
            criteria_eval = result["criteria_evaluation"]
            print(f"  Found 'criteria_evaluation': {len(criteria_eval)} items")
        
        # Check for alternative field names (singular, different spellings)
        elif "criterion_evaluation" in result and isinstance(result["criterion_evaluation"], list):
            print("  Found 'criterion_evaluation' (singular), converting...")
            criteria_eval = result["criterion_evaluation"]
            result["criteria_evaluation"] = criteria_eval
        
        elif "evaluation" in result and isinstance(result["evaluation"], list):
            print("  Found 'evaluation', converting...")
            criteria_eval = result["evaluation"]
            result["criteria_evaluation"] = criteria_eval
        
        elif "evaluations" in result and isinstance(result["evaluations"], list):
            print("  Found 'evaluations', converting...")
            criteria_eval = result["evaluations"]
            result["criteria_evaluation"] = criteria_eval
        
        # Step 2: Normalize each criterion's structure
        print("STEP 2: Normalizing individual criteria")
        if criteria_eval is None:
            print("  WARNING: No criteria found, creating empty list")
            result["criteria_evaluation"] = []
            criteria_eval = []
        
        normalized_criteria = []
        for i, criterion in enumerate(criteria_eval):
            if not isinstance(criterion, dict):
                print(f"  WARNING: Criterion {i} is not a dict, skipping")
                continue
            
            normalized = {}
            
            # Map criterion name
            normalized["criterion_name"] = (
                criterion.get("criterion_name") or
                criterion.get("name") or
                criterion.get("id") or
                f"Criterion {i+1}"
            )
            
            # Map awarded points (CRITICAL: LLM might use "score" instead of "awarded_points")
            score_value = None
            if "awarded_points" in criterion:
                score_value = criterion.get("awarded_points")
            elif "score" in criterion:
                # "score": 85 means 85/100 or percentage - this is the awarded_points
                score_value = criterion.get("score")
            elif "points" in criterion:
                score_value = criterion.get("points")
            
            try:
                normalized["awarded_points"] = float(score_value) if score_value is not None else 0
            except (ValueError, TypeError):
                print(f"  WARNING: Criterion {i} score not numeric: {score_value}")
                normalized["awarded_points"] = 0
            
            # Map max_points
            max_val = (
                criterion.get("max_points") or
                criterion.get("max_score") or
                100  # Default to 100
            )
            try:
                normalized["max_points"] = float(max_val)
            except (ValueError, TypeError):
                normalized["max_points"] = 100
            
            # Map satisfied status (true if score >= 70% of max_points)
            normalized["satisfied"] = criterion.get("satisfied", normalized["awarded_points"] >= (normalized["max_points"] * 0.7))
            
            # Map evidence
            normalized["evidence"] = criterion.get("evidence") or criterion.get("comment") or ""
            
            # Map feedback
            normalized["feedback"] = criterion.get("feedback") or criterion.get("description") or ""
            
            print(f"  Criterion {i}: '{normalized['criterion_name']}' = {normalized['awarded_points']}/{normalized['max_points']}")
            normalized_criteria.append(normalized)
        
        result["criteria_evaluation"] = normalized_criteria
        
        # Step 3: Ensure all required top-level fields exist
        print("STEP 3: Adding required top-level fields")
        required_fields = {
            "total_score": 0,
            "max_score": 0,
            "percentage": 0.0,
            "overall_feedback": "",
            "strengths": [],
            "areas_for_improvement": []
        }
        
        for field, default_value in required_fields.items():
            if field not in result:
                print(f"  Adding missing field: {field}")
                result[field] = default_value
        
        return result

    def grade_submission(self, student_answer: str, question: str, rubric: Dict) -> Dict:
        """
        Grade a student submission against rubric
        
        Args:
            student_answer: Extracted text from student's answer
            question: The assignment/exam question
            rubric: Structured rubric dictionary
        
        Returns:
            Grading result dictionary with scores and feedback
        """
        print("-" * 60)
        print("GRADING START")
        print("-" * 60)
        print(f"Rubric type: {rubric.get('rubric_type', 'unknown')}")
        print(f"Number of criteria: {len(rubric.get('criteria', []))}")
        print(f"Student answer length: {len(student_answer)} chars")
        print(f"Question provided: {bool(question and question.strip())}")
        
        system_prompt = AI_MARKER_SYSTEM_PROMPT
        
        # Check rubric type
        rubric_type = rubric.get("rubric_type", "simple")
        
        if rubric_type == "banded":
            print("Banded rubric detected - using percentage-based scoring")
            
            # Build band reference from actual rubric
            band_examples = []
            for criterion in rubric.get("criteria", [])[:1]:  # Use first criterion as example
                band_examples.append(
                    f"Example with actual rubric data:\n"
                    f"- Criterion: {criterion.get('criterion_name', 'Unnamed')}\n"
                    f"- Max Points: {criterion.get('max_points', 0)}\n"
                    f"- If student work matches 60-69 band:\n"
                    f"  1. Pick percentage: 65 (middle of 60-69)\n"
                    f"  2. Calculate points: (65 / 100) * {criterion.get('max_points', 0)} = {int(criterion.get('max_points', 0) * 0.65)}\n"
                    f"  3. Award: {int(criterion.get('max_points', 0) * 0.65)} points"
                )
            
            grading_instructions = (
                f"Banded Rubric Scoring Guide\n"
                f"CRITICAL: These bands represent PERCENTAGE bands, NOT point bands.\n\n"
                f"Step-by-step process:\n"
                f"1. Read each criterion and its band descriptions\n"
                f"2. Determine which band describes the student's work\n"
                f"3. Select a percentage from that band (use middle value as default)\n"
                f"4. MULTIPLY by the criterion's max_points to get awarded_points\n\n"
                f"Percentage Bands:\n"
                f"- 0-49: Unsatisfactory\n"
                f"- 50-59: Below Average\n"
                f"- 60-69: Average\n"
                f"- 70-79: Above Average\n"
                f"- 80-89: Very Good\n"
                f"- 90-100: Excellent\n\n"
                f"Formula: awarded_points = (percentage / 100) * max_points\n\n"
                f"{''.join(band_examples)}\n\n"
                f"NEVER put the percentage itself as awarded_points!\n"
                f"ALWAYS multiply by max_points!"
            )
        else:
            print("Simple rubric detected - using fixed-point scoring")
            grading_instructions = "Each criterion has a maximum point value. Determine if the criterion is satisfied and award full or partial points based on the rubric requirements."
        
        prompt = (
            f"Grading Task:\n{grading_instructions}\n\n"
            f"Question (if provided):\n{question if question else 'No specific question provided'}\n\n"
            f"Student Answer:\n{student_answer}\n\n"
            f"Grading Rubric:\n{json.dumps(rubric, indent=2)}\n\n"
            f"Evaluate this student answer against the rubric following these steps:\n"
            f"1. Read the rubric structure carefully (banded or simple)\n"
            f"2. For banded rubrics: Identify which band each criterion falls into\n"
            f"3. For simple rubrics: Determine if each criterion is satisfied\n"
            f"4. Provide specific evidence from the student's answer\n"
            f"5. Calculate total score accurately\n"
            f"6. Generate constructive feedback\n\n"
            f"CRITICAL REQUIREMENTS:\n"
            f"- Return ONLY valid JSON, no markdown, no explanation, no extra text\n"
            f"- Quote specific parts of student answer as evidence\n"
            f"- Be fair but maintain standards\n"
            f"- For banded rubrics: Use the full score range, not just minimum\n"
            f"- Provide actionable improvement suggestions\n"
            f"- Ensure arithmetic is correct\n"
            f"- Include criteria_evaluation array with all criteria\n\n"
            f"Return your evaluation in the specified JSON format."
        )
        
        response = self._make_request(
            prompt=prompt,
            system=system_prompt,
            temperature=0.1,  # Low temperature for consistency
            max_tokens=3000,
            response_format="json"
        )
        
        print(f"Received response: {len(response)} chars")
        print(f"Received response: {response}")
        
        grading_result = self._parse_and_repair_json(response)
        
        # Validate before returning
        print("VALIDATION (before normalization):")
        print(f"- criteria_evaluation length: {len(grading_result.get('criteria_evaluation', []))}")
        print(f"- total_score: {grading_result.get('total_score', 0)}")
        
        # Normalize the structure
        grading_result = self.normalize_grading_structure(grading_result, rubric)
        
        # Validate and calculate scores
        grading_result = self.validate_grading_result(grading_result, rubric)
        
        print("VALIDATION (after normalization):")
        print(f"- criteria_evaluation length: {len(grading_result.get('criteria_evaluation', []))}")
        print(f"- total_score: {grading_result.get('total_score', 0)}")
        print(f"- max_score: {grading_result.get('max_score', 0)}")
        print(f"- percentage: {grading_result.get('percentage', 0)}")
        print("-" * 60)
        
        return grading_result

    def _parse_and_repair_json(self, response: str) -> Dict:
        """Parse JSON response with comprehensive error repair"""
        try:
            grading_result = json.loads(response)
            print("JSON parsed successfully")
            return grading_result
        except json.JSONDecodeError as e:
            print(f"WARNING: Initial JSON parse failed: {str(e)}")
            
            # Try to fix common JSON issues
            response = response.strip()
            
            # Remove markdown code blocks if present
            if response.startswith("```"):
                response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]
            
            # Remove leading/trailing whitespace from extracted content
            response = response.strip()
            
            # Fix trailing commas
            response = re.sub(r',(\s*[}\]])', r'\1', response)
            
            # Add missing closing braces
            if response.count('{') > response.count('}'):
                response += '}' * (response.count('{') - response.count('}'))
            
            # Try parsing again
            try:
                grading_result = json.loads(response)
                print("Fixed JSON after repair attempts")
                return grading_result
            except json.JSONDecodeError:
                print(f"CRITICAL: Could not parse LLM response as JSON after repairs")
                print(f"Response preview: {response[:500]}")
                
                # Return error structure with all required fields
                return {
                    "criteria_evaluation": [],
                    "total_score": 0,
                    "max_score": 0,
                    "percentage": 0,
                    "overall_feedback": "Grading failed: Could not parse LLM response",
                    "strengths": [],
                    "areas_for_improvement": [],
                    "error": "Failed to parse LLM response as JSON",
                    "raw_response": response[:500]
                }

    def validate_grading_result(self, result: Dict, rubric: Dict) -> Dict:
        """Validate grading result and fix any arithmetic errors"""
        
        print("Validating and calculating final scores...")
        
        # Ensure criteria_evaluation exists and is non-empty
        if "criteria_evaluation" not in result:
            print(f"ERROR: No criteria_evaluation in LLM response. Result keys: {result.keys()}")
            result["criteria_evaluation"] = []
            result["total_score"] = 0
            result["max_score"] = 0
            result["percentage"] = 0
            return result
        
        if not isinstance(result["criteria_evaluation"], list):
            print(f"ERROR: criteria_evaluation is not a list, it's {type(result['criteria_evaluation'])}")
            result["criteria_evaluation"] = []
        
        if len(result["criteria_evaluation"]) == 0:
            print(f"ERROR: criteria_evaluation is empty! No criteria to grade.")
            result["total_score"] = 0
            result["max_score"] = 0
            result["percentage"] = 0
            return result
        
        # Validate each criterion has required fields
        valid_criteria = []
        for i, criterion in enumerate(result.get("criteria_evaluation", [])):
            if not isinstance(criterion, dict):
                print(f"WARNING: Criterion {i} is not a dict, skipping")
                continue
            
            if "awarded_points" not in criterion:
                print(f"WARNING: Criterion {i} missing awarded_points. Keys: {criterion.keys()}")
                criterion["awarded_points"] = 0
            
            # Ensure awarded_points is numeric
            try:
                criterion["awarded_points"] = float(criterion.get("awarded_points", 0))
            except (ValueError, TypeError):
                print(f"WARNING: Criterion {i} awarded_points is not numeric: {criterion.get('awarded_points')}")
                criterion["awarded_points"] = 0
            
            valid_criteria.append(criterion)
        
        result["criteria_evaluation"] = valid_criteria
        
        # Recalculate total score
        calculated_total = sum(
            criterion.get("awarded_points", 0)
            for criterion in result.get("criteria_evaluation", [])
        )
        
        print(f"DEBUG: Calculated total from {len(result['criteria_evaluation'])} criteria: {calculated_total}")
        
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
        
        # Ensure max_score is valid
        if max_score <= 0:
            print("WARNING: max_score is 0. This will cause division by zero.")
            max_score = 100  # Fallback
        
        # Override LLM calculations with correct arithmetic
        result["total_score"] = calculated_total
        result["max_score"] = max_score
        result["percentage"] = round((calculated_total / max_score * 100), 2) if max_score > 0 else 0
        
        print(f"Validated Score: {calculated_total}/{max_score} = {result['percentage']}%")
        # Add metadata
        result["model_used"] = self.model
        result["grading_method"] = "rubric_based_llm"
        result["rubric_type"] = rubric_type
        return result
