# Database handler for grading session persistence

import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Dict, Optional

class Database:
    """Handles SQLite database operations for grading storage"""
    
    def __init__(self, db_path: str = "ai_marker.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Grading sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grading_sessions (
                session_id TEXT PRIMARY KEY,
                teacher_id TEXT NOT NULL,
                assignment_name TEXT NOT NULL,
                course_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT
            )
        """)
        
        # Submissions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                submission_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                answer_sheet_path TEXT,
                extracted_answer TEXT,
                submission_date TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES grading_sessions(session_id)
            )
        """)
        
        # Grading results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS grading_results (
                result_id TEXT PRIMARY KEY,
                submission_id TEXT NOT NULL,
                total_score REAL NOT NULL,
                max_score REAL NOT NULL,
                percentage REAL NOT NULL,
                criteria_evaluation TEXT,
                overall_feedback TEXT,
                strengths TEXT,
                improvements TEXT,
                graded_at TEXT NOT NULL,
                model_used TEXT,
                FOREIGN KEY (submission_id) REFERENCES submissions(submission_id)
            )
        """)
        
        # Rubrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rubrics (
                rubric_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                rubric_data TEXT NOT NULL,
                question_text TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES grading_sessions(session_id)
            )
        """)
        
        # Feedback documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedback_documents (
                document_id TEXT PRIMARY KEY,
                result_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                FOREIGN KEY (result_id) REFERENCES grading_results(result_id)
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_grading_session(self, session_id: str, teacher_id: str = "default_teacher",
                               assignment_name: str = "Untitled Assignment",
                               course_id: Optional[str] = None) -> str:
        """Create a new grading session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO grading_sessions (session_id, teacher_id, assignment_name, 
                                         course_id, created_at, updated_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (session_id, teacher_id, assignment_name, course_id, now, now, json.dumps({})))
        
        conn.commit()
        conn.close()
        return session_id
    
    def add_submission(self, session_id: str, student_name: str, 
                      answer_sheet_path: str = None, extracted_answer: str = None) -> str:
        """Add a student submission"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        submission_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        # Ensure session exists
        cursor.execute("SELECT session_id FROM grading_sessions WHERE session_id = ?",
                      (session_id,))
        if not cursor.fetchone():
            self.create_grading_session(session_id)
        
        cursor.execute("""
            INSERT INTO submissions (submission_id, session_id, student_name, 
                                    answer_sheet_path, extracted_answer, submission_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (submission_id, session_id, student_name, answer_sheet_path, 
              extracted_answer, timestamp))
        
        # Update session timestamp
        cursor.execute("""
            UPDATE grading_sessions
            SET updated_at = ?
            WHERE session_id = ?
        """, (timestamp, session_id))
        
        conn.commit()
        conn.close()
        return submission_id
    
    def save_grading_result(self, submission_id: str, grading_data: Dict,
                           model_used: str = "unknown") -> str:
        """Save grading results"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        result_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO grading_results (result_id, submission_id, total_score, 
                                        max_score, percentage, criteria_evaluation,
                                        overall_feedback, strengths, improvements,
                                        graded_at, model_used)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result_id,
            submission_id,
            grading_data.get("total_score", 0),
            grading_data.get("max_score", 0),
            grading_data.get("percentage", 0),
            json.dumps(grading_data.get("criteria_evaluation", [])),
            grading_data.get("overall_feedback", ""),
            json.dumps(grading_data.get("strengths", [])),
            json.dumps(grading_data.get("areas_for_improvement", [])),
            timestamp,
            model_used
        ))
        
        conn.commit()
        conn.close()
        return result_id
    
    def save_rubric(self, session_id: str, rubric_data: Dict, 
                   question_text: str = "") -> str:
        """Save rubric for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        rubric_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO rubrics (rubric_id, session_id, rubric_data, 
                               question_text, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (rubric_id, session_id, json.dumps(rubric_data), 
              question_text, timestamp))
        
        conn.commit()
        conn.close()
        return rubric_id
    
    def get_rubric(self, session_id: str) -> Optional[Dict]:
        """Retrieve rubric for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT rubric_data, question_text
            FROM rubrics
            WHERE session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
        """, (session_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "rubric_data": json.loads(row[0]),
                "question_text": row[1]
            }
        return None
    
    def get_grading_results(self, session_id: str) -> List[Dict]:
        """Retrieve all grading results for a session"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT s.student_name, r.total_score, r.max_score, r.percentage,
                   r.overall_feedback, r.graded_at, r.result_id
            FROM grading_results r
            JOIN submissions s ON r.submission_id = s.submission_id
            WHERE s.session_id = ?
            ORDER BY r.graded_at DESC
        """, (session_id,))
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "student_name": row[0],
                "total_score": row[1],
                "max_score": row[2],
                "percentage": row[3],
                "overall_feedback": row[4],
                "graded_at": row[5],
                "result_id": row[6]
            })
        
        conn.close()
        return results
    
    def save_feedback_document(self, result_id: str, file_path: str) -> str:
        """Record generated feedback document"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        document_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        
        cursor.execute("""
            INSERT INTO feedback_documents (document_id, result_id, file_path, generated_at)
            VALUES (?, ?, ?, ?)
        """, (document_id, result_id, file_path, timestamp))
        
        conn.commit()
        conn.close()
        return document_id
    
    def export_session(self, session_id: str) -> Dict:
        """Export entire session data for download"""
        results = self.get_grading_results(session_id)
        rubric = self.get_rubric(session_id)
        
        return {
            "session_id": session_id,
            "exported_at": datetime.now().isoformat(),
            "rubric": rubric,
            "grading_results": results
        }
