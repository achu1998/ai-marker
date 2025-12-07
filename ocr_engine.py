# OCR Engine for text extraction from images and handwritten documents (EasyOCR version)

import easyocr
from typing import Dict

class OCREngine:
    """Handles OCR for printed and handwritten text extraction using EasyOCR"""
    
    def __init__(self, languages=None):
        """
        Initialize EasyOCR
        Args:
            languages: List of languages (default: English)
        """
        if languages is None:
            languages = ['en']  # Equivalent to OCR_LANGUAGE
            
        # EasyOCR loads GPU automatically if available (safe on M-series)
        self.reader = easyocr.Reader(languages)
    
    def extract_text_from_image(self, image_path: str) -> Dict:
        """
        Extract text from image using EasyOCR
        
        Returns:
            Dict with extracted text and confidence score
        """
        try:
            # EasyOCR returns: [ [bbox, text, confidence], ... ]
            result = self.reader.readtext(image_path, detail=1, paragraph=False)

            if not result:
                return {
                    "text": "",
                    "confidence": 0.0,
                    "method": "easyocr",
                    "success": False
                }
            
            text_blocks = []
            confidences = []

            for block in result:
                _, text, conf = block
                text_blocks.append(text)
                confidences.append(conf)

            avg_conf = sum(confidences) / len(confidences) if confidences else 0

            return {
                "text": "\n".join(text_blocks),
                "confidence": avg_conf,
                "method": "easyocr",
                "success": True,
                "num_lines": len(text_blocks)
            }

        except Exception as e:
            return {
                "text": "",
                "confidence": 0.0,
                "method": "easyocr",
                "success": False,
                "error": str(e)
            }
    
    def extract_handwritten_text(self, image_path: str, ollama_client=None) -> Dict:
        """
        Extract handwritten text using a Vision LLM fallback
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
            extracted = ollama_client.extract_text_from_image(image_path)
            
            return {
                "text": extracted,
                "confidence": 0.85,  # Vision LLMs don't provide confidence
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
    
    def smart_extract(self, image_path: str, ollama_client=None, 
                      confidence_threshold: float = 0.75) -> str:
        """
        Uses EasyOCR first, falls back to Vision LLM if confidence is low
        """
        ocr_result = self.extract_text_from_image(image_path)
        
        if ocr_result["success"] and ocr_result["confidence"] >= confidence_threshold:
            return ocr_result["text"]
        
        # Fall back to vision model if provided
        if ollama_client is not None:
            vision_result = self.extract_handwritten_text(image_path, ollama_client)
            if vision_result["success"]:
                return vision_result["text"]
        
        # Return low-confidence OCR result anyway
        return ocr_result.get("text", "")
