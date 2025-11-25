# Document processor for handling PDFs and images

import PyPDF2
import io
from PIL import Image
import cv2
import numpy as np
from typing import Optional, Dict, List
import os

class DocumentProcessor:
    """Handles PDF and image processing for answer sheets, questions, and rubrics"""
    
    def __init__(self, temp_dir: str = "temp_processing"):
        self.temp_dir = temp_dir
        os.makedirs(temp_dir, exist_ok=True)
    
    def process_pdf(self, uploaded_file, document_type: str = "answer_sheet") -> Dict:
        """
        Process uploaded PDF file
        
        Args:
            uploaded_file: Streamlit UploadedFile object
            document_type: "answer_sheet", "question_paper", or "rubric"
        
        Returns:
            Dict with extracted data and metadata
        """
        try:
            # Try text extraction first
            pdf_reader = PyPDF2.PdfReader(uploaded_file)
            
            text_content = []
            images = []
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                
                if text and len(text.strip()) > 50:
                    # Has extractable text
                    text_content.append({
                        "page": page_num + 1,
                        "text": self._clean_text(text),
                        "has_text": True
                    })
                else:
                    # Likely scanned or handwritten - save for OCR
                    text_content.append({
                        "page": page_num + 1,
                        "text": "",
                        "has_text": False,
                        "requires_ocr": True
                    })
            
            return {
                "type": document_type,
                "pages": text_content,
                "num_pages": len(pdf_reader.pages),
                "has_extractable_text": any(p["has_text"] for p in text_content),
                "requires_ocr": any(p.get("requires_ocr", False) for p in text_content)
            }
            
        except Exception as e:
            raise Exception(f"Error processing PDF: {str(e)}")
    
    def process_image(self, uploaded_file, document_type: str = "answer_sheet") -> Dict:
        """
        Process uploaded image file (JPG, PNG)
        
        Args:
            uploaded_file: Streamlit UploadedFile object
            document_type: "answer_sheet", "question_paper", or "rubric"
        
        Returns:
            Dict with image data ready for OCR
        """
        try:
            # Load image
            image = Image.open(uploaded_file)
            
            # Preprocess for better OCR
            processed_image = self.preprocess_image(image)
            
            # Save temporarily
            temp_path = os.path.join(self.temp_dir, f"{document_type}_{uploaded_file.name}")
            processed_image.save(temp_path)
            
            return {
                "type": document_type,
                "image_path": temp_path,
                "requires_ocr": True,
                "original_format": uploaded_file.type
            }
            
        except Exception as e:
            raise Exception(f"Error processing image: {str(e)}")
    
    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocess image for better OCR accuracy
        
        Applies:
        - Grayscale conversion
        - Denoising
        - Contrast enhancement
        - Binarization
        """
        # Convert PIL to OpenCV format
        img_array = np.array(image)
        
        # Convert to grayscale
        if len(img_array.shape) == 3:
            gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array
        
        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray, h=10)
        
        # Increase contrast using CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(denoised)
        
        # Binarization using Otsu's method
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Convert back to PIL Image
        return Image.fromarray(binary)
    
    def _clean_text(self, text: str) -> str:
        """Clean extracted text"""
        # Remove excessive whitespace
        text = ' '.join(text.split())
        
        # Restore paragraph breaks
        lines = text.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        text = '\n'.join(cleaned_lines)
        
        return text
    
    def extract_metadata(self, uploaded_file) -> Dict:
        """Extract metadata from uploaded file"""
        metadata = {
            "filename": uploaded_file.name,
            "size_bytes": uploaded_file.size,
            "file_type": uploaded_file.type
        }
        
        if uploaded_file.type == "application/pdf":
            try:
                pdf_reader = PyPDF2.PdfReader(uploaded_file)
                metadata["num_pages"] = len(pdf_reader.pages)
                
                if pdf_reader.metadata:
                    metadata.update({
                        "author": pdf_reader.metadata.get("/Author", "Unknown"),
                        "creation_date": pdf_reader.metadata.get("/CreationDate", "Unknown")
                    })
            except:
                pass
        
        return metadata
    
    def cleanup_temp_files(self):
        """Clean up temporary processing files"""
        try:
            for file in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, file)
                if os.path.isfile(file_path):
                    os.remove(file_path)
        except Exception as e:
            print(f"Warning: Could not clean up temp files: {e}")
