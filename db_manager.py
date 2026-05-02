import sqlite3
import json
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Ensure DB_PATH is always absolute relative to the script's directory
# This prevents the DB from "moving" when the agent navigates to other folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "history.db")

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deepseek_url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                messages TEXT
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database Error: {e}")

def create_session() -> int:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO sessions (messages) VALUES (?)", ("[]",))
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return session_id
    except:
        init_db() # Try to re-init if insert fails
        return 1 # Fallback to 1

def save_session(session_id: int, url: Optional[str], messages: List[Dict]):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE sessions 
            SET deepseek_url = ?, messages = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (url, json.dumps(messages), session_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error saving session: {e}")

def load_session(session_id: int):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT deepseek_url, messages FROM sessions WHERE id = ?", (session_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return row[0], json.loads(row[1])
    except:
        pass
    return None, []

def get_recent_sessions(limit: int = 10):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, deepseek_url, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        sessions = []
        for r in rows:
            sessions.append({
                "id": r[0],
                "url": r[1],
                "created_at": r[2],
                "updated_at": r[3]
            })
        return sessions
    except:
        return []

# Always ensure DB is ready on import
init_db()
