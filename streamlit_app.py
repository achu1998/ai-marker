# AI Marker Streamlit Application
# Main application file for grading student submissions

import streamlit as st
import json
import uuid
from datetime import datetime
from typing import Dict, List
import os

# Import local modules
from ollama_client import OllamaClient
from document_processor import DocumentProcessor
from ocr_engine import OCREngine
from feedback_generator import FeedbackGenerator
from database import Database
from prompts import AI_MARKER_SYSTEM_PROMPT

# Page configuration
st.set_page_config(
    page_title="AI Marker - Automated Grading Assistant",
    page_icon="📝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1a5490;
        font-weight: bold;
        text-align: center;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .score-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 2rem;
        border-radius: 10px;
        text-align: center;
        margin: 1rem 0;
    }
    .score-value {
        font-size: 3rem;
        font-weight: bold;
    }
    .criterion-satisfied {
        background-color: #d4edda;
        border-left: 4px solid #28a745;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 5px;
    }
    .criterion-not-satisfied {
        background-color: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 5px;
    }
    .feedback-section {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 8px;
        margin: 1rem 0;
    }
    .stProgress > div > div > div > div {
        background-color: #667eea;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
def initialize_session_state():
    """Initialize all session state variables"""
    if 'session_id' not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    
    if 'ollama_client' not in st.session_state:
        try:
            st.session_state.ollama_client = OllamaClient()
        except Exception as e:
            st.error(f"Failed to initialize LLM client: {str(e)}")
            st.stop()
    
    if 'doc_processor' not in st.session_state:
        st.session_state.doc_processor = DocumentProcessor()
    
    if 'ocr_engine' not in st.session_state:
        st.session_state.ocr_engine = OCREngine()
    
    if 'feedback_generator' not in st.session_state:
        st.session_state.feedback_generator = FeedbackGenerator()
    
    if 'database' not in st.session_state:
        st.session_state.database = Database()
    
    if 'grading_results' not in st.session_state:
        st.session_state.grading_results = []
    
    if 'current_rubric' not in st.session_state:
        st.session_state.current_rubric = None
    
    if 'current_question' not in st.session_state:
        st.session_state.current_question = None
    
    if 'assignment_name' not in st.session_state:
        st.session_state.assignment_name = "Untitled Assignment"

# Process uploaded document
def process_document(uploaded_file, document_type: str) -> Dict:
    """Process uploaded document (PDF or image)"""
    try:
        if uploaded_file.type == "application/pdf":
            return st.session_state.doc_processor.process_pdf(uploaded_file, document_type)
        else:
            return st.session_state.doc_processor.process_image(uploaded_file, document_type)
    except Exception as e:
        st.error(f"Error processing {document_type}: {str(e)}")
        return None

# Extract text from document
def extract_text_from_document(doc_data: Dict, use_ocr: bool = False, document_type: str = "document") -> str:
    """Extract text from processed document
    
    Args:
        doc_data: Processed document data
        use_ocr: Force OCR/vision processing
        document_type: Type of document ("answer_sheet", "rubric", "question") for appropriate messaging
    """
    try:
        # For typed documents with extractable text, use direct extraction
        if doc_data.get("has_extractable_text") and not use_ocr:
            text_parts = []
            for page in doc_data["pages"]:
                if page.get("has_text"):
                    text_parts.append(page["text"])
            extracted = "\n\n".join(text_parts)
            if extracted.strip():  # Only return if we got meaningful text
                return extracted
        
        # For scanned/image documents, use OCR/vision
                # For scanned/image documents, use OCR/vision
        if doc_data.get("requires_ocr") or use_ocr:
            # Only show special message for answer sheets
            if document_type == "answer_sheet" and use_ocr:
                st.info("📝 Processing handwritten answer sheet with vision model (this may take longer)...")
            
            # If document processor created images, use them
            if "image_path" in doc_data:
                # For handwritten, use higher threshold to trigger vision model faster
                # For typed (rubric/question), use lower threshold to try PaddleOCR first
                confidence_threshold = 0.9 if use_ocr else 0.70
                return st.session_state.ocr_engine.smart_extract(
                    doc_data["image_path"],
                    st.session_state.ollama_client,
                    confidence_threshold=confidence_threshold
                )
            else:
                # For PDF without embedded text, we need image extraction
                st.warning("⚠️ Handwritten PDF requires image conversion. Please ensure PDF is scanned at 300 DPI.")
                return ""
        else:
            st.error("Document requires OCR but no image available")
            return ""
    except Exception as e:
        st.error(f"Error extracting text: {str(e)}")
        return ""

# Grade submission
def grade_submission(student_name: str, answer_text: str, 
                    question_text: str, rubric: Dict) -> Dict:
    """Grade a student submission"""
    try:
        with st.spinner("🤖 AI is grading the submission..."):
            result = st.session_state.ollama_client.grade_submission(
                student_answer=answer_text,
                question=question_text,
                rubric=rubric
            )
            
            # Add timestamp
            result['grading_timestamp'] = datetime.now().isoformat()
            result['student_name'] = student_name
            
            # Save to database
            submission_id = st.session_state.database.add_submission(
                session_id=st.session_state.session_id,
                student_name=student_name,
                extracted_answer=answer_text
            )
            
            result_id = st.session_state.database.save_grading_result(
                submission_id=submission_id,
                grading_data=result,
                model_used=result.get('model_used', 'unknown')
            )
            
            result['result_id'] = result_id
            
            return result
            
    except Exception as e:
        st.error(f"Error during grading: {str(e)}")
        return None

# Display grading results
def display_grading_results(result: Dict):
    """Display grading results in a formatted way"""
    
    # Score card
    st.markdown(f"""
    <div class="score-card">
        <div class="score-value">{result['total_score']}/{result['max_score']}</div>
        <div style="font-size: 1.5rem; margin-top: 0.5rem;">{result['percentage']:.1f}%</div>
        <div style="margin-top: 0.5rem; opacity: 0.9;">Final Score</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Overall feedback
    st.markdown("### 📋 Overall Feedback")
    st.markdown(f"""
    <div class="feedback-section">
        {result.get('overall_feedback', 'No overall feedback provided.')}
    </div>
    """, unsafe_allow_html=True)
    
    # Strengths
    if result.get('strengths') and len(result['strengths']) > 0:
        st.markdown("### ✅ Strengths")
        for strength in result['strengths']:
            st.success(f"• {strength}")
    
    # Areas for improvement
    if result.get('areas_for_improvement') and len(result['areas_for_improvement']) > 0:
        st.markdown("### 📈 Areas for Improvement")
        for area in result['areas_for_improvement']:
            st.warning(f"• {area}")
    
    # Detailed criterion breakdown
    st.markdown("### 🔍 Detailed Criterion Breakdown")
    
    for criterion in result.get('criteria_evaluation', []):
        satisfied = criterion.get('satisfied', False)
        css_class = "criterion-satisfied" if satisfied else "criterion-not-satisfied"
        status_icon = "✓" if satisfied else "✗"
        
        st.markdown(f"""
        <div class="{css_class}">
            <h4>{status_icon} {criterion['criterion_name']} ({criterion['awarded_points']}/{criterion['max_points']} points)</h4>
            <p><strong>Evidence:</strong> {criterion.get('evidence', 'No evidence provided')}</p>
            <p><strong>Feedback:</strong> {criterion.get('feedback', 'No feedback provided')}</p>
        </div>
        """, unsafe_allow_html=True)

# Main application
def main():
    initialize_session_state()
    
    # Header
    st.markdown('<div class="main-header">📝 AI Marker</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Privacy-First Local Grading Assistant for Universities</div>', 
                unsafe_allow_html=True)
    
    # Sidebar - Configuration and document uploads
    with st.sidebar:
        st.markdown("## ⚙️ Configuration")
        
        # Assignment name
        assignment_name = st.text_input(
            "Assignment Name",
            value=st.session_state.assignment_name,
            placeholder="e.g., Midterm Exam - Chapter 5"
        )
        if assignment_name != st.session_state.assignment_name:
            st.session_state.assignment_name = assignment_name
            st.session_state.database.create_grading_session(
                session_id=st.session_state.session_id,
                assignment_name=assignment_name
            )
        
        st.markdown("---")
        st.markdown("## 📁 Upload Documents")
        
        # Question paper upload
        st.markdown("### 1️⃣ Question Paper")
        question_file = st.file_uploader(
            "Upload question paper",
            type=['pdf'],
            key="question_upload",
            help="Upload the assignment or exam question"
        )
        
        # Rubric upload
        st.markdown("### 2️⃣ Grading Rubric")
        rubric_file = st.file_uploader(
            "Upload grading rubric",
            type=['pdf'],
            key="rubric_upload",
            help="Upload the rubric with grading criteria"
        )
        
        # Process question and rubric
        if question_file and st.button("📤 Process Question & Rubric"):
            with st.spinner("Processing question paper..."):
                question_doc = process_document(question_file, "question_paper")
                if question_doc:
                    question_text = extract_text_from_document(question_doc, document_type="question")
                    st.session_state.current_question = question_text
                    st.success("✓ Question paper processed")

        
        if rubric_file and st.button("📤 Process Rubric"):
            with st.spinner("Processing rubric..."):
                rubric_doc = process_document(rubric_file, "rubric")
                if rubric_doc:
                    rubric_text = extract_text_from_document(rubric_doc, document_type="rubric")
                    
                    if not rubric_text or len(rubric_text.strip()) < 20:
                        st.error("⚠️ Could not extract text from rubric. Please ensure the image is clear and readable.")
                    else:
                        # Show extracted text for debugging
                        with st.expander("📄 Extracted Rubric Text (click to verify)"):
                            st.text(rubric_text)
                        
                        # Extract structured rubric
                        with st.spinner("🤖 Extracting rubric structure..."):
                            structured_rubric = st.session_state.ollama_client.extract_rubric_structure(rubric_text)
                            st.session_state.current_rubric = structured_rubric
                            
                            # Save to database
                            st.session_state.database.save_rubric(
                                session_id=st.session_state.session_id,
                                rubric_data=structured_rubric,
                                question_text=st.session_state.current_question or ""
                            )
                            
                            st.success(f"✓ Rubric processed ({len(structured_rubric.get('criteria', []))} criteria found)")
        
        st.markdown("---")
        
        # Display current configuration status
        st.markdown("### 📊 Status")
        if st.session_state.current_question:
            st.success("✓ Question loaded (optional)")
        else:
            st.info("○ Question not loaded (optional)")

        if st.session_state.current_rubric:
            st.success(f"✓ Rubric loaded ({len(st.session_state.current_rubric.get('criteria', []))} criteria)")
        else:
            st.error("⚠️ Rubric required - please upload")

    
    # Main content area - Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📝 Grade Submission", "👁️ View Question & Rubric", 
                                       "📊 Results History", "ℹ️ About"])
    
    # Tab 1: Grade Submission
    with tab1:
        st.markdown("## Grade Student Submission")
        
        if not st.session_state.current_rubric:
            st.warning("⚠️ Please upload and process the grading rubric first (see sidebar)")
            st.stop()
        
        # Student information
        col1, col2 = st.columns(2)
        with col1:
            student_name = st.text_input(
                "Student Name",
                placeholder="e.g., John Doe",
                help="Enter the student's name"
            )

        with col2:
            student_id = st.text_input(
                "Student ID (Optional)",
                placeholder="e.g., 12345",
                help="Optional student identifier"
            )

        # Document type selector
        st.markdown("### 📄 Answer Sheet Type")
        answer_type = st.radio(
            "Select document type:",
            options=["Typed/Printed", "Handwritten"],
            horizontal=True,
            help="Select 'Handwritten' for better OCR accuracy on handwritten submissions"
        )

        # Answer sheet upload
        st.markdown("### 3️⃣ Upload Answer Sheet")
        answer_file = st.file_uploader(
            "Upload student answer sheet (PDF only)",
            type=['pdf'],
            key="answer_upload",
            help="Upload the student's answer sheet"
        )
        
        # Grade button
        if st.button("🎯 Grade Submission", type="primary", disabled=not (student_name and answer_file)):
            if not student_name:
                st.error("Please enter student name")
            elif not answer_file:
                st.error("Please upload answer sheet")
            else:
                # Process answer sheet
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                status_text.text("📄 Processing answer sheet...")
                progress_bar.progress(20)
                answer_doc = process_document(answer_file, "answer_sheet")
                
                if answer_doc:
                    status_text.text("🔍 Extracting student answer...")
                    progress_bar.progress(40)
                    
                    # Use document type to optimize extraction
                    force_vision = (answer_type == "Handwritten")
                    answer_text = extract_text_from_document(answer_doc, use_ocr=force_vision, document_type="answer_sheet")


                    
                    if answer_text:
                        status_text.text("🤖 Grading with AI...")
                        progress_bar.progress(60)
                        
                        # Grade submission
                        result = grade_submission(
                            student_name=student_name,
                            answer_text=answer_text,
                            question_text=st.session_state.current_question or "No specific question provided",
                            rubric=st.session_state.current_rubric
                        )
                        
                        if result:
                            status_text.text("📝 Generating feedback PDF...")
                            progress_bar.progress(80)
                            
                            # Generate feedback PDF
                            try:
                                feedback_path = st.session_state.feedback_generator.generate_feedback_pdf(
                                    grading_result=result,
                                    student_name=student_name,
                                    assignment_name=st.session_state.assignment_name
                                )
                                
                                # Save feedback document reference
                                st.session_state.database.save_feedback_document(
                                    result_id=result['result_id'],
                                    file_path=feedback_path
                                )
                                
                                result['feedback_pdf_path'] = feedback_path
                            except Exception as e:
                                st.warning(f"Could not generate feedback PDF: {str(e)}")
                            
                            progress_bar.progress(100)
                            status_text.text("✅ Grading complete!")
                            
                            # Store result
                            st.session_state.grading_results.append(result)
                            
                            # Display results
                            st.markdown("---")
                            st.markdown("## 🎓 Grading Results")
                            display_grading_results(result)
                            
                            # Download feedback PDF
                            if result.get('feedback_pdf_path'):
                                with open(result['feedback_pdf_path'], 'rb') as pdf_file:
                                    st.download_button(
                                        label="📥 Download Feedback PDF",
                                        data=pdf_file.read(),
                                        file_name=os.path.basename(result['feedback_pdf_path']),
                                        mime="application/pdf"
                                    )
                    else:
                        st.error("Failed to extract text from answer sheet")
                else:
                    st.error("Failed to process answer sheet")
    
    # Tab 2: View Question & Rubric
    with tab2:
        st.markdown("## 👁️ Current Question and Rubric")
        
        if st.session_state.current_question:
            st.markdown("### Question")
            st.info(st.session_state.current_question)
        else:
            st.warning("No question loaded yet")
        
        if st.session_state.current_rubric:
            st.markdown("### Grading Rubric")
            st.json(st.session_state.current_rubric)
            if st.session_state.current_rubric.get("rubric_type") == "banded":
                st.markdown("### 📊 Rubric Criteria")
                for criterion in st.session_state.current_rubric.get("criteria", []):
                    st.markdown(f"**{criterion['criterion_name']}** ({criterion['weight_percentage']}%)")
                    st.write(f"Max Points: {criterion['max_points']}")
        else:
            st.warning("No rubric loaded yet")
    
    # Tab 3: Results History
    with tab3:
        st.markdown("## 📊 Grading Results History")
        
        # Get all results from database
        all_results = st.session_state.database.get_grading_results(st.session_state.session_id)
        
        if all_results:
            st.markdown(f"**Total Submissions Graded:** {len(all_results)}")
            
            # Calculate statistics
            avg_score = sum(r['percentage'] for r in all_results) / len(all_results)
            st.metric("Average Score", f"{avg_score:.1f}%")
            
            # Display results table
            st.markdown("### Individual Results")
            for result in all_results:
                with st.expander(f"📄 {result['student_name']} - {result['percentage']:.1f}%"):
                    st.write(f"**Score:** {result['total_score']}/{result['max_score']}")
                    st.write(f"**Graded At:** {result['graded_at']}")
                    st.write(f"**Feedback:** {result['overall_feedback']}")
            
            # Export session data
            if st.button("📤 Export All Results (JSON)"):
                export_data = st.session_state.database.export_session(st.session_state.session_id)
                st.download_button(
                    label="Download JSON",
                    data=json.dumps(export_data, indent=2),
                    file_name=f"grading_results_{st.session_state.assignment_name}_{datetime.now().strftime('%Y%m%d')}.json",
                    mime="application/json"
                )
        else:
            st.info("No grading results yet. Grade some submissions to see history.")
    
    # Tab 4: About
    with tab4:
        st.markdown("""
        ## About AI Marker
        
        AI Marker is a privacy-first, local automated grading assistant designed for universities.
        
        ### 🎯 Key Features
        - **Local Processing**: All grading happens on your machine - no data leaves your computer
        - **PDF & Image Support**: Upload typed or handwritten answer sheets
        - **Rubric-Based Grading**: Structured, criterion-based evaluation
        - **Detailed Feedback**: Comprehensive feedback with strengths and improvements
        - **PDF Reports**: Generate professional feedback documents for students
        - **Results Tracking**: Built-in database to track all grading sessions
        
        ### 🔒 Privacy & Security
        - ✅ 100% local processing (when using Ollama)
        - ✅ No cloud API calls for student data
        - ✅ FERPA-compliant by design
        - ✅ All data stored locally in SQLite database
        
        ### 🤖 AI Models
        This system uses local LLM models via Ollama for:
        - Text extraction from documents
        - Rubric structure parsing
        - Student answer evaluation
        - Feedback generation
        
        **Recommended Models:**
        - Grading: Llama 3.1 70B or Qwen 2.5 72B
        - Vision: Llama 3.2-Vision 11B
        - OCR: PaddleOCR (printed text)
        
        ### 📚 How to Use
        1. **Setup**: Upload question paper and grading rubric (sidebar)
        2. **Grade**: Upload student answer sheet and click "Grade Submission"
        3. **Review**: View results and download feedback PDF
        4. **Track**: Check results history and export data
        
        ### ⚙️ System Requirements
        - **RAM**: 16GB minimum (32GB+ recommended for 70B models)
        - **Storage**: 50GB free space for models
        - **GPU**: Optional but recommended (NVIDIA RTX 3060+)
        - **OS**: Windows, macOS, or Linux
        
        ### 🆘 Support
        For issues or questions, please refer to the README.md and QUICKSTART.md files.
        
        ---
        **Version**: 1.0.0  
        **Last Updated**: November 2025
        """)

if __name__ == "__main__":
    main()
