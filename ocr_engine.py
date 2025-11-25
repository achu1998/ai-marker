# OCR Engine for text extraction from images and handwritten documents

from paddleocr import PaddleOCR
import base64
from typing import Dict, Optional
from config import USE_GPU, OCR_LANGUAGE

class OCREngine:
    """Handles OCR for printed and handwritten text extraction"""
    
    def __init__(self):
        # Initialize PaddleOCR
        self.paddle_ocr = PaddleOCR(
            use_angle_cls=True,
            lang=OCR_LANGUAGE,
        )
    
    def extract_text_from_image(self, image_path: str) -> Dict:
        """
        Extract text from image using PaddleOCR
        
        Args:
            image_path: Path to image file
        
        Returns:
            Dict with extracted text and confidence score
        """
        try:
            result = self.paddle_ocr.ocr(image_path, cls=True)
            
            if not result or not result[0]:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "method": "paddleocr",
                    "success": False
                }
            
            # Combine all detected text blocks
            text_blocks = []
            total_confidence = 0
            
            for line in result[0]:
                text = line[1][0]
                confidence = line[1][1]
                text_blocks.append(text)
                total_confidence += confidence
            
            avg_confidence = total_confidence / len(result[0]) if result[0] else 0
            
            return {
                "text": "\n".join(text_blocks),
                "confidence": avg_confidence,
                "method": "paddleocr",
                "success": True,
                "num_lines": len(text_blocks)
            }
            
        except Exception as e:
            return {
                "text": "",
                "confidence": 0.0,
                "method": "paddleocr",
                "success": False,
                "error": str(e)
            }
    
    def extract_handwritten_text(self, image_path: str, 
                                 ollama_client = None) -> Dict:
        """
        Extract handwritten text using vision LLM (fallback for low OCR confidence)
        
        Args:
            image_path: Path to image file
            ollama_client: OllamaClient instance with vision model
        
        Returns:
            Dict with extracted text
        """
        if ollama_client is None:
            return {
                "text": "",
                "confidence": 0.0,
                "method": "vision_llm",
                "success": False,
                "error": "No vision model client provided"
            }
        
        try:
            # This would call the vision model
            # Implementation depends on whether using local Llama 3.2-Vision or cloud API
            extracted = ollama_client.extract_text_from_image(image_path)
            
            return {
                "text": extracted,
                "confidence": 0.85,  # Vision models don't provide confidence typically
                "method": "vision_llm",
                "success": True
            }
            
        except Exception as e:
            return {
                "text": "",
                "confidence": 0.0,
                "method": "vision_llm",
                "success": False,
                "error": str(e)
            }
    
    def smart_extract(self, image_path: str, ollama_client = None, 
                     confidence_threshold: float = 0.75) -> str:
        """
        Intelligently extract text using best available method
        
        Tries PaddleOCR first, falls back to vision LLM if confidence low
        
        Args:
            image_path: Path to image file
            ollama_client: OllamaClient instance (optional, for fallback)
            confidence_threshold: Minimum confidence for PaddleOCR
        
        Returns:
            Extracted text string
        """
        # Try PaddleOCR first
        ocr_result = self.extract_text_from_image(image_path)
        
        if ocr_result["success"] and ocr_result["confidence"] >= confidence_threshold:
            return ocr_result["text"]
        
        # Fall back to vision LLM if available
        if ollama_client is not None:
            vision_result = self.extract_handwritten_text(image_path, ollama_client)
            if vision_result["success"]:
                return vision_result["text"]
        
        # Return what we have, even if low confidence
        return ocr_result.get("text", "")
