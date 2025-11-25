# Feedback document generator - creates PDF reports for students

from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from typing import Dict
import os
from datetime import datetime

class FeedbackGenerator:
    """Generates PDF feedback documents for graded submissions"""
    
    def __init__(self, output_dir: str = "feedback_pdfs"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        """Create custom paragraph styles for feedback documents"""
        
        # Title style
        self.styles.add(ParagraphStyle(
            name='FeedbackTitle',
            parent=self.styles['Title'],
            fontSize=20,
            textColor=colors.HexColor('#1a5490'),
            spaceAfter=20,
            alignment=TA_CENTER
        ))
        
        # Student info style
        self.styles.add(ParagraphStyle(
            name='StudentInfo',
            parent=self.styles['Normal'],
            fontSize=11,
            leading=14,
            spaceAfter=10
        ))
        
        # Score display style
        self.styles.add(ParagraphStyle(
            name='ScoreDisplay',
            parent=self.styles['Normal'],
            fontSize=16,
            textColor=colors.HexColor('#2c5282'),
            alignment=TA_CENTER,
            spaceAfter=15,
            spaceBefore=10
        ))
        
        # Section header style
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=14,
            textColor=colors.HexColor('#1a5490'),
            spaceAfter=10,
            spaceBefore=15
        ))
        
        # Criterion header style
        self.styles.add(ParagraphStyle(
            name='CriterionHeader',
            parent=self.styles['Heading3'],
            fontSize=12,
            textColor=colors.HexColor('#2c5282'),
            spaceAfter=6,
            spaceBefore=10
        ))
        
        # Feedback text style
        self.styles.add(ParagraphStyle(
            name='FeedbackText',
            parent=self.styles['Normal'],
            fontSize=10,
            leading=14,
            spaceAfter=8
        ))
        
        # List item style
        self.styles.add(ParagraphStyle(
            name='ListItem',
            parent=self.styles['Normal'],
            fontSize=10,
            leftIndent=20,
            spaceAfter=5
        ))
    
    def generate_feedback_pdf(self, grading_result: Dict, student_name: str,
                             assignment_name: str) -> str:
        """
        Generate comprehensive feedback PDF
        
        Args:
            grading_result: Dictionary with grading results
            student_name: Name of the student
            assignment_name: Name of the assignment
        
        Returns:
            Path to generated PDF file
        """
        # Create filename
        safe_student_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' 
                                   for c in student_name)
        safe_assignment_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' 
                                      for c in assignment_name)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_student_name}_{safe_assignment_name}_{timestamp}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        
        # Create PDF document
        doc = SimpleDocTemplate(
            filepath,
            pagesize=letter,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=72
        )
        
        # Build content
        story = []
        
        # Title
        title = Paragraph("Grading Feedback Report", self.styles['FeedbackTitle'])
        story.append(title)
        story.append(Spacer(1, 0.2*inch))
        
        # Student information
        info_text = f"""
        <b>Student:</b> {student_name}<br/>
        <b>Assignment:</b> {assignment_name}<br/>
        <b>Date Graded:</b> {grading_result.get('grading_timestamp', 
                                                datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}<br/>
        <b>Model Used:</b> {grading_result.get('model_used', 'Unknown')}
        """
        story.append(Paragraph(info_text, self.styles['StudentInfo']))
        story.append(Spacer(1, 0.2*inch))
        
        # Score display with colored background
        score_data = [
            ['Total Score', 'Maximum Score', 'Percentage'],
            [
                str(grading_result['total_score']),
                str(grading_result['max_score']),
                f"{grading_result['percentage']}%"
            ]
        ]
        
        score_table = Table(score_data, colWidths=[2*inch, 2*inch, 1.5*inch])
        score_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a5490')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#e6f2ff')),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 1), (-1, -1), 14),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#1a5490')),
            ('TOPPADDING', (0, 1), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 12),
        ]))
        story.append(score_table)
        story.append(Spacer(1, 0.3*inch))
        
        # Overall feedback
        story.append(Paragraph("Overall Feedback", self.styles['SectionHeader']))
        story.append(Paragraph(
            grading_result.get('overall_feedback', 'No overall feedback provided.'),
            self.styles['FeedbackText']
        ))
        story.append(Spacer(1, 0.2*inch))
        
        # Strengths
        if grading_result.get('strengths') and len(grading_result['strengths']) > 0:
            story.append(Paragraph("✓ Strengths", self.styles['SectionHeader']))
            for strength in grading_result['strengths']:
                story.append(Paragraph(f"• {strength}", self.styles['ListItem']))
            story.append(Spacer(1, 0.2*inch))
        
        # Areas for improvement
        if grading_result.get('areas_for_improvement') and len(grading_result['areas_for_improvement']) > 0:
            story.append(Paragraph("→ Areas for Improvement", self.styles['SectionHeader']))
            for area in grading_result['areas_for_improvement']:
                story.append(Paragraph(f"• {area}", self.styles['ListItem']))
            story.append(Spacer(1, 0.2*inch))
        
        # Detailed criterion breakdown
        story.append(Paragraph("Detailed Criterion Breakdown", self.styles['SectionHeader']))
        story.append(Spacer(1, 0.1*inch))
        
        for criterion in grading_result.get('criteria_evaluation', []):
            # Criterion name and score
            criterion_title = f"{criterion['criterion_name']} " \
                            f"({criterion['awarded_points']}/{criterion['max_points']} points)"
            story.append(Paragraph(criterion_title, self.styles['CriterionHeader']))
            
            # Status indicator
            status_color = colors.green if criterion.get('satisfied', False) else colors.red
            status_text = "✓ Criterion Satisfied" if criterion.get('satisfied', False) else "✗ Criterion Not Satisfied"
            status = Paragraph(
                f"<font color='{status_color.hexval()}'><b>{status_text}</b></font>",
                self.styles['FeedbackText']
            )
            story.append(status)
            
            # Evidence
            if criterion.get('evidence'):
                story.append(Paragraph(
                    f"<b>Evidence:</b> {criterion['evidence']}",
                    self.styles['FeedbackText']
                ))
            
            # Feedback
            if criterion.get('feedback'):
                story.append(Paragraph(
                    f"<b>Feedback:</b> {criterion['feedback']}",
                    self.styles['FeedbackText']
                ))
            
            story.append(Spacer(1, 0.15*inch))
        
        # Footer note
        story.append(Spacer(1, 0.3*inch))
        footer_text = """
        <i>This feedback was generated using AI-assisted grading. 
        If you have questions or concerns about your grade, please contact your instructor.</i>
        """
        story.append(Paragraph(footer_text, self.styles['Normal']))
        
        # Build PDF
        doc.build(story)
        
        return filepath
    
    def generate_summary_report(self, grading_results: list, session_info: Dict) -> str:
        """
        Generate summary report for multiple graded submissions
        
        Args:
            grading_results: List of grading result dictionaries
            session_info: Session metadata
        
        Returns:
            Path to generated summary PDF
        """
        filename = f"Summary_Report_{session_info['assignment_name']}_{datetime.now().strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(self.output_dir, filename)
        
        doc = SimpleDocTemplate(filepath, pagesize=letter)
        story = []
        
        # Title
        title = Paragraph(f"Grading Summary Report: {session_info['assignment_name']}", 
                         self.styles['FeedbackTitle'])
        story.append(title)
        story.append(Spacer(1, 0.3*inch))
        
        # Statistics
        total_students = len(grading_results)
        avg_score = sum(r['percentage'] for r in grading_results) / total_students if total_students > 0 else 0
        highest_score = max(r['percentage'] for r in grading_results) if total_students > 0 else 0
        lowest_score = min(r['percentage'] for r in grading_results) if total_students > 0 else 0
        
        stats_text = f"""
        <b>Total Students:</b> {total_students}<br/>
        <b>Average Score:</b> {avg_score:.2f}%<br/>
        <b>Highest Score:</b> {highest_score:.2f}%<br/>
        <b>Lowest Score:</b> {lowest_score:.2f}%
        """
        story.append(Paragraph(stats_text, self.styles['Normal']))
        story.append(Spacer(1, 0.3*inch))
        
        # Results table
        story.append(Paragraph("Individual Results", self.styles['SectionHeader']))
        
        table_data = [['Student Name', 'Score', 'Max Score', 'Percentage']]
        for result in grading_results:
            table_data.append([
                result['student_name'],
                str(result['total_score']),
                str(result['max_score']),
                f"{result['percentage']:.2f}%"
            ])
        
        results_table = Table(table_data, colWidths=[2.5*inch, 1*inch, 1*inch, 1*inch])
        results_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1a5490')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        story.append(results_table)
        
        doc.build(story)
        return filepath
