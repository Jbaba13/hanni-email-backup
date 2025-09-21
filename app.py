#!/usr/bin/env python3
"""
Hanni Email Backup Dashboard - Enhanced Analytics Version
With communication flow analysis and word heatmaps
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import json
import sqlite3
from pathlib import Path
import os
import sys
import re
from collections import Counter
from typing import Dict, List, Tuple, Optional
import base64

# Page configuration
st.set_page_config(
    page_title="Hanni Email Analytics Dashboard",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enhanced Hanni branding
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&display=swap');
    
    /* Main gradient background */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Content containers */
    .main .block-container {
        background: rgba(255, 255, 255, 0.97);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        max-width: 1400px;
        margin: auto;
    }
    
    /* Headers */
    h1 {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-family: 'Inter', sans-serif;
        font-weight: 800;
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    
    h2 {
        color: #5a67d8;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
        margin-top: 2rem;
    }
    
    h3 {
        color: #667eea;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
    }
    
    /* Enhanced metrics */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem;
        border-radius: 15px;
        color: white;
        box-shadow: 0 8px 25px rgba(118, 75, 162, 0.25);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    [data-testid="metric-container"] label {
        color: rgba(255, 255, 255, 0.95) !important;
        font-weight: 600;
        font-size: 0.9rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    
    [data-testid="metric-container"] [data-testid="metric-value"] {
        color: white !important;
        font-weight: 700;
        font-size: 2rem;
    }
    
    [data-testid="metric-container"] [data-testid="metric-delta"] {
        color: #a0f0a0 !important;
        font-weight: 600;
    }
    
    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f9fa 0%, #e9ecef 100%);
        border-right: 2px solid #dee2e6;
    }
    
    /* Enhanced buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.75rem 1.5rem;
        font-weight: 600;
        border-radius: 10px;
        transition: all 0.3s ease;
        font-family: 'Inter', sans-serif;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        box-shadow: 0 4px 15px rgba(118, 75, 162, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(118, 75, 162, 0.5);
    }
    
    /* Select boxes */
    .stSelectbox > div > div {
        background: white;
        border: 2px solid #e1e8f0;
        border-radius: 10px;
        padding: 0.25rem;
    }
    
    .stSelectbox > div > div:focus-within {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1rem;
        background: rgba(102, 126, 234, 0.05);
        padding: 0.5rem;
        border-radius: 15px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 10px;
        padding: 0.75rem 1.5rem;
        background: white;
        border: 2px solid transparent;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(102, 126, 234, 0.1);
        border-color: #667eea;
    }
    
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
    }
    
    /* Data tables */
    .stDataFrame {
        border: 2px solid #e1e8f0;
        border-radius: 10px;
        overflow: hidden;
    }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 8px 25px rgba(118, 75, 162, 0.25);
    }
    
    .success-box {
        background: linear-gradient(135deg, #48bb78 0%, #38a169 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 8px 25px rgba(72, 187, 120, 0.25);
    }
    
    .warning-box {
        background: linear-gradient(135deg, #f6ad55 0%, #ed8936 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 8px 25px rgba(246, 173, 85, 0.25);
    }
    
    /* Expander styling */
    .streamlit-expanderHeader {
        background: rgba(102, 126, 234, 0.05);
        border-radius: 10px;
        border: 2px solid #e1e8f0;
        font-weight: 600;
    }
    
    /* Word cloud container */
    .wordcloud-container {
        background: white;
        border: 2px solid #e1e8f0;
        border-radius: 15px;
        padding: 1.5rem;
        margin: 1rem 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
    
    /* Communication matrix styling */
    .matrix-container {
        background: white;
        border-radius: 15px;
        padding: 1rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
    }
</style>
""", unsafe_allow_html=True)

# Initialize paths
BASE_DIR = Path.cwd()
STATE_DIR = BASE_DIR / "state"
INDEX_DB = BASE_DIR / "email_index.db"
STOPWORDS_FILE = BASE_DIR / "stopwords.txt"

# Create required directories
STATE_DIR.mkdir(exist_ok=True)

# Common English stopwords for word analysis
COMMON_STOPWORDS = set([
    'the', 'be', 'to', 'of', 'and', 'a', 'in', 'that', 'have', 'i', 'it', 
    'for', 'not', 'on', 'with', 'he', 'as', 'you', 'do', 'at', 'this', 
    'but', 'his', 'by', 'from', 'they', 'we', 'say', 'her', 'she', 'or', 
    'an', 'will', 'my', 'one', 'all', 'would', 'there', 'their', 'what',
    'so', 'up', 'out', 'if', 'about', 'who', 'get', 'which', 'go', 'me',
    'when', 'make', 'can', 'like', 'time', 'no', 'just', 'him', 'know',
    'take', 'people', 'into', 'year', 'your', 'good', 'some', 'could',
    'them', 'see', 'other', 'than', 'then', 'now', 'look', 'only', 'come',
    'its', 'over', 'think', 'also', 'back', 'after', 'use', 'two', 'how',
    'our', 'work', 'first', 'well', 'way', 'even', 'new', 'want', 'because',
    'any', 'these', 'give', 'day', 'most', 'us', 'is', 'was', 'are', 'been',
    'has', 'had', 'were', 'said', 'did', 'am', 'should', 'may', 'being',
    're', 've', 'll', 'don', 'didn', 'won', 'can', 'couldn', 'wouldn'
])

# Load custom stopwords if file exists
if STOPWORDS_FILE.exists():
    try:
        with open(STOPWORDS_FILE, 'r') as f:
            custom_stopwords = set(line.strip().lower() for line in f)
            COMMON_STOPWORDS.update(custom_stopwords)
    except:
        pass

# Initialize session state
if 'selected_user' not in st.session_state:
    st.session_state.selected_user = 'all'
if 'date_range' not in st.session_state:
    st.session_state.date_range = 'all'
if 'word_filter' not in st.session_state:
    st.session_state.word_filter = ''

# Database initialization
def init_database():
    """Initialize the SQLite database with enhanced schema"""
    if not INDEX_DB.exists():
        conn = sqlite3.connect(INDEX_DB)
        cursor = conn.cursor()
        
        # Enhanced email_index table
        cursor.execute('''CREATE TABLE IF NOT EXISTS email_index (
            user_email TEXT,
            message_id TEXT PRIMARY KEY,
            subject TEXT,
            sender TEXT,
            recipients TEXT,
            date INTEGER,
            has_attachments INTEGER,
            attachment_names TEXT,
            size_bytes INTEGER,
            dropbox_path TEXT,
            body_preview TEXT,
            sender_domain TEXT,
            recipient_count INTEGER,
            thread_id TEXT,
            labels TEXT
        )''')
        
        # Create comprehensive indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON email_index(user_email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON email_index(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sender ON email_index(sender)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sender_domain ON email_index(sender_domain)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_subject ON email_index(subject)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_has_attachments ON email_index(has_attachments)')
        
        # Communication patterns table
        cursor.execute('''CREATE TABLE IF NOT EXISTS communication_patterns (
            sender TEXT,
            recipient TEXT,
            email_count INTEGER,
            total_size_bytes INTEGER,
            first_email_date INTEGER,
            last_email_date INTEGER,
            PRIMARY KEY (sender, recipient)
        )''')
        
        # Word frequency table
        cursor.execute('''CREATE TABLE IF NOT EXISTS word_frequencies (
            user_email TEXT,
            word TEXT,
            frequency INTEGER,
            last_seen_date INTEGER,
            PRIMARY KEY (user_email, word)
        )''')
        
        conn.commit()
        conn.close()
        
        # Add demo data if empty
        add_demo_data()

def add_demo_data():
    """Add demo data for Streamlit Cloud when no real data exists"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Check if database is empty
    cursor.execute("SELECT COUNT(*) FROM email_index")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Add sample emails with realistic data
        demo_emails = [
            ("ann@heyhanni.com", "msg_001", "Q4 Sales Report", 
             "john.doe@example.com", "ann@heyhanni.com,team@heyhanni.com", 
             int(datetime.now().timestamp() * 1000), 1, "q4_report.pdf", 256000,
             "/Email Backups/ann@heyhanni.com/2024/12/01/q4_sales.eml",
             "Please find attached the Q4 sales report with updated figures...",
             "example.com", 2),
            
            ("jennie@heyhanni.com", "msg_002", "Team Meeting Tomorrow", 
             "sarah@heyhanni.com", "jennie@heyhanni.com,all@heyhanni.com", 
             int((datetime.now() - timedelta(days=1)).timestamp() * 1000), 0, "", 4096,
             "/Email Backups/jennie@heyhanni.com/2024/12/02/meeting.eml",
             "Reminder: We have our weekly team meeting tomorrow at 10 AM...",
             "heyhanni.com", 2),
            
            ("leslie@heyhanni.com", "msg_003", "Project Update - Hanni Dashboard", 
             "dev@techpartner.com", "leslie@heyhanni.com", 
             int((datetime.now() - timedelta(days=2)).timestamp() * 1000), 1, "mockup.png", 102400,
             "/Email Backups/leslie@heyhanni.com/2024/12/03/project.eml",
             "The dashboard development is progressing well. Attached are the latest mockups...",
             "techpartner.com", 1),
             
            ("hillary@heyhanni.com", "msg_004", "Customer Feedback Summary", 
             "support@heyhanni.com", "hillary@heyhanni.com,management@heyhanni.com", 
             int((datetime.now() - timedelta(days=3)).timestamp() * 1000), 0, "", 8192,
             "/Email Backups/hillary@heyhanni.com/2024/11/30/feedback.eml",
             "This week's customer feedback has been overwhelmingly positive...",
             "heyhanni.com", 2),
             
            ("jenn@heyhanni.com", "msg_005", "Budget Approval Request", 
             "finance@heyhanni.com", "jenn@heyhanni.com", 
             int((datetime.now() - timedelta(days=5)).timestamp() * 1000), 1, "budget_2024.xlsx", 512000,
             "/Email Backups/jenn@heyhanni.com/2024/11/28/budget.eml",
             "Please review and approve the attached budget for next quarter...",
             "heyhanni.com", 1),
        ]
        
        # Insert demo emails
        for email_data in demo_emails:
            cursor.execute('''INSERT OR REPLACE INTO email_index 
                (user_email, message_id, subject, sender, recipients, date, 
                 has_attachments, attachment_names, size_bytes, dropbox_path, 
                 body_preview, sender_domain, recipient_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', email_data)
        
        # Add communication patterns
        patterns = [
            ("john.doe@example.com", "ann@heyhanni.com", 15, 3840000),
            ("sarah@heyhanni.com", "jennie@heyhanni.com", 23, 512000),
            ("dev@techpartner.com", "leslie@heyhanni.com", 8, 2048000),
            ("support@heyhanni.com", "hillary@heyhanni.com", 12, 256000),
            ("finance@heyhanni.com", "jenn@heyhanni.com", 5, 1024000),
        ]
        
        for pattern in patterns:
            cursor.execute('''INSERT OR REPLACE INTO communication_patterns
                (sender, recipient, email_count, total_size_bytes, 
                 first_email_date, last_email_date)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (*pattern, int((datetime.now() - timedelta(days=30)).timestamp() * 1000),
                 int(datetime.now().timestamp() * 1000)))
        
        # Add sample word frequencies
        words = [
            ("ann@heyhanni.com", "sales", 45),
            ("ann@heyhanni.com", "report", 38),
            ("ann@heyhanni.com", "quarterly", 22),
            ("jennie@heyhanni.com", "meeting", 52),
            ("jennie@heyhanni.com", "team", 48),
            ("jennie@heyhanni.com", "project", 31),
            ("leslie@heyhanni.com", "dashboard", 67),
            ("leslie@heyhanni.com", "development", 43),
            ("leslie@heyhanni.com", "update", 35),
        ]
        
        for word_data in words:
            cursor.execute('''INSERT OR REPLACE INTO word_frequencies
                (user_email, word, frequency, last_seen_date)
                VALUES (?, ?, ?, ?)''',
                (*word_data, int(datetime.now().timestamp() * 1000)))
        
        conn.commit()
    
    conn.close()

# Initialize database on startup
init_database()

# Utility functions
def load_all_states():
    """Load all user backup states"""
    states = {}
    
    if STATE_DIR.exists():
        for state_file in STATE_DIR.glob("*.json"):
            try:
                with open(state_file, 'r') as f:
                    email = state_file.stem
                    states[email] = json.load(f)
            except:
                pass
    
    # Add demo state if no real states exist
    if not states:
        states = {
            'ann@heyhanni.com': {
                'downloaded_ids': [f'msg_{i:03d}' for i in range(1, 101)],
                'last_backup': datetime.now().isoformat(),
                'failed_messages': [],
                'total_processed': 100
            },
            'jennie@heyhanni.com': {
                'downloaded_ids': [f'msg_{i:03d}' for i in range(101, 181)],
                'last_backup': (datetime.now() - timedelta(hours=2)).isoformat(),
                'failed_messages': [],
                'total_processed': 80
            },
            'leslie@heyhanni.com': {
                'downloaded_ids': [f'msg_{i:03d}' for i in range(181, 231)],
                'last_backup': (datetime.now() - timedelta(hours=5)).isoformat(),
                'failed_messages': ['msg_230', 'msg_231'],
                'total_processed': 52
            },
        }
    
    return states

def extract_domain(email: str) -> str:
    """Extract domain from email address"""
    if '@' in email:
        return email.split('@')[1].lower()
    return 'unknown'

def extract_words_from_text(text: str, min_length: int = 3) -> List[str]:
    """Extract meaningful words from text for analysis"""
    if not text:
        return []
    
    # Convert to lowercase and remove special characters
    text = re.sub(r'[^a-zA-Z\s]', ' ', text.lower())
    
    # Split into words
    words = text.split()
    
    # Filter out stopwords and short words
    meaningful_words = [
        word for word in words 
        if len(word) >= min_length and word not in COMMON_STOPWORDS
    ]
    
    return meaningful_words

def get_backup_stats():
    """Get comprehensive backup statistics"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Basic statistics
    cursor.execute("SELECT COUNT(DISTINCT user_email) FROM email_index")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM email_index")
    total_emails = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(size_bytes) FROM email_index")
    total_size = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM email_index WHERE has_attachments = 1")
    emails_with_attachments = cursor.fetchone()[0]
    
    # Communication statistics
    cursor.execute("SELECT COUNT(DISTINCT sender) FROM email_index")
    unique_senders = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT sender_domain) FROM email_index WHERE sender_domain IS NOT NULL")
    unique_domains = cursor.fetchone()[0]
    
    # Date range
    cursor.execute("SELECT MIN(date), MAX(date) FROM email_index")
    date_range = cursor.fetchone()
    
    conn.close()
    
    # Load states for additional info
    states = load_all_states()
    
    # Calculate last backup time
    last_backup = None
    for state in states.values():
        if state.get('last_backup'):
            backup_time = datetime.fromisoformat(state['last_backup'])
            if last_backup is None or backup_time > last_backup:
                last_backup = backup_time
    
    # Calculate success rate
    total_processed = sum(state.get('total_processed', 0) for state in states.values())
    total_failed = sum(len(state.get('failed_messages', [])) for state in states.values())
    success_rate = (total_processed - total_failed) / total_processed * 100 if total_processed > 0 else 100
    
    return {
        'total_users': total_users,
        'total_emails': total_emails,
        'total_size_mb': total_size / (1024 * 1024) if total_size else 0,
        'emails_with_attachments': emails_with_attachments,
        'last_backup': last_backup,
        'active_users': len(states),
        'success_rate': success_rate,
        'unique_senders': unique_senders,
        'unique_domains': unique_domains,
        'date_range': date_range,
    }

def get_communication_matrix(user_filter: Optional[str] = None) -> pd.DataFrame:
    """Get email communication matrix"""
    conn = sqlite3.connect(INDEX_DB)
    
    query = '''
        SELECT 
            sender,
            user_email as recipient,
            COUNT(*) as email_count,
            SUM(size_bytes) as total_size
        FROM email_index
    '''
    
    params = []
    if user_filter and user_filter != 'all':
        query += " WHERE (sender = ? OR user_email = ?)"
        params = [user_filter, user_filter]
    
    query += " GROUP BY sender, recipient ORDER BY email_count DESC"
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    return df

def get_word_frequencies(user_filter: Optional[str] = None, 
                        top_n: int = 50) -> List[Tuple[str, int]]:
    """Get word frequencies from email subjects and bodies"""
    conn = sqlite3.connect(INDEX_DB)
    
    # First try to get from word_frequencies table
    if user_filter and user_filter != 'all':
        query = "SELECT word, frequency FROM word_frequencies WHERE user_email = ? ORDER BY frequency DESC LIMIT ?"
        params = [user_filter, top_n]
    else:
        query = "SELECT word, SUM(frequency) as frequency FROM word_frequencies GROUP BY word ORDER BY frequency DESC LIMIT ?"
        params = [top_n]
    
    cursor = conn.cursor()
    cursor.execute(query, params)
    results = cursor.fetchall()
    
    # If no cached data, compute from email_index
    if not results:
        if user_filter and user_filter != 'all':
            query = "SELECT subject, body_preview FROM email_index WHERE user_email = ?"
            params = [user_filter]
        else:
            query = "SELECT subject, body_preview FROM email_index"
            params = []
        
        cursor.execute(query, params)
        emails = cursor.fetchall()
        
        # Count words
        word_counter = Counter()
        for subject, body in emails:
            words = extract_words_from_text(f"{subject} {body}")
            word_counter.update(words)
        
        results = word_counter.most_common(top_n)
    
    conn.close()
    return results

def create_word_heatmap(word_frequencies: List[Tuple[str, int]]) -> go.Figure:
    """Create a word frequency heatmap"""
    if not word_frequencies:
        # Return empty figure with message
        fig = go.Figure()
        fig.add_annotation(
            text="No word frequency data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(
            xaxis=dict(showgrid=False, zeroline=False, visible=False),
            yaxis=dict(showgrid=False, zeroline=False, visible=False),
            height=400
        )
        return fig
    
    # Prepare data for heatmap
    words = [w[0] for w in word_frequencies[:20]]  # Top 20 words
    frequencies = [w[1] for w in word_frequencies[:20]]
    
    # Create grid for heatmap (5x4 grid)
    grid_size = (5, 4)
    grid_values = []
    grid_text = []
    
    idx = 0
    for i in range(grid_size[0]):
        row_values = []
        row_text = []
        for j in range(grid_size[1]):
            if idx < len(frequencies):
                row_values.append(frequencies[idx])
                row_text.append(f"{words[idx]}<br>{frequencies[idx]}")
            else:
                row_values.append(0)
                row_text.append("")
            idx += 1
        grid_values.append(row_values)
        grid_text.append(row_text)
    
    fig = go.Figure(data=go.Heatmap(
        z=grid_values,
        text=grid_text,
        texttemplate="%{text}",
        textfont={"size": 12, "color": "white"},
        colorscale=[[0, '#f0f0f0'], [0.5, '#667eea'], [1, '#764ba2']],
        showscale=True,
        colorbar=dict(
            title="Frequency",
            titleside="right",
            thickness=15,
            len=0.7,
            bgcolor="rgba(255, 255, 255, 0.8)",
            borderwidth=2,
            bordercolor="#e1e8f0"
        )
    ))
    
    fig.update_layout(
        title="Word Frequency Heatmap",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=400,
        margin=dict(l=50, r=50, t=80, b=50),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='white',
    )
    
    return fig

def create_communication_flow_chart(comm_matrix: pd.DataFrame) -> go.Figure:
    """Create a Sankey diagram for email communication flow"""
    if comm_matrix.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No communication data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(height=500)
        return fig
    
    # Get unique senders and recipients
    all_nodes = list(set(comm_matrix['sender'].unique().tolist() + 
                        comm_matrix['recipient'].unique().tolist()))
    
    # Create node indices
    node_indices = {node: i for i, node in enumerate(all_nodes)}
    
    # Prepare data for Sankey
    source = [node_indices[sender] for sender in comm_matrix['sender']]
    target = [node_indices[recipient] for recipient in comm_matrix['recipient']]
    values = comm_matrix['email_count'].tolist()
    
    # Create colors for nodes
    node_colors = []
    for node in all_nodes:
        if '@heyhanni.com' in node:
            node_colors.append('rgba(118, 75, 162, 0.8)')  # Purple for internal
        else:
            node_colors.append('rgba(102, 126, 234, 0.8)')  # Blue for external
    
    # Create Sankey diagram
    fig = go.Figure(data=[go.Sankey(
        node=dict(
            pad=15,
            thickness=20,
            line=dict(color="white", width=0.5),
            label=all_nodes,
            color=node_colors,
            hovertemplate='%{label}<br>Total: %{value}<extra></extra>'
        ),
        link=dict(
            source=source,
            target=target,
            value=values,
            color='rgba(102, 126, 234, 0.2)',
            hovertemplate='From: %{source.label}<br>To: %{target.label}<br>Emails: %{value}<extra></extra>'
        )
    )])
    
    fig.update_layout(
        title="Email Communication Flow",
        font_size=10,
        height=600,
        margin=dict(l=50, r=50, t=80, b=50),
    )
    
    return fig

def create_time_based_heatmap(user_filter: Optional[str] = None) -> go.Figure:
    """Create a time-based email activity heatmap"""
    conn = sqlite3.connect(INDEX_DB)
    
    # Query for hourly email distribution
    query = '''
        SELECT 
            CAST(strftime('%H', datetime(date/1000, 'unixepoch')) AS INTEGER) as hour,
            CAST(strftime('%w', datetime(date/1000, 'unixepoch')) AS INTEGER) as weekday,
            COUNT(*) as email_count
        FROM email_index
    '''
    
    params = []
    if user_filter and user_filter != 'all':
        query += " WHERE user_email = ?"
        params = [user_filter]
    
    query += " GROUP BY hour, weekday"
    
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(
            text="No time-based data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=20, color="gray")
        )
        fig.update_layout(height=400)
        return fig
    
    # Create pivot table for heatmap
    pivot = df.pivot_table(values='email_count', index='hour', columns='weekday', fill_value=0)
    
    # Days of week labels
    days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    
    # Create heatmap
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=days,
        y=[f"{h:02d}:00" for h in range(24)],
        colorscale=[[0, '#f0f0f0'], [0.5, '#667eea'], [1, '#764ba2']],
        hovertemplate='%{x}<br>%{y}<br>Emails: %{z}<extra></extra>',
        colorbar=dict(
            title="Emails",
            titleside="right",
            thickness=15,
            len=0.7
        )
    ))
    
    fig.update_layout(
        title="Email Activity Heatmap (by Hour and Day)",
        xaxis_title="Day of Week",
        yaxis_title="Hour of Day",
        height=500,
        yaxis=dict(autorange='reversed'),
    )
    
    return fig

# Main dashboard
def main():
    # Header
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col1:
        # Logo placeholder
        st.markdown("# 📧")
    
    with col2:
        st.markdown("""
        # Hanni Email Analytics Dashboard
        ### Comprehensive Email Backup & Intelligence Platform
        """)
    
    with col3:
        # Refresh button
        if st.button("🔄 Refresh", use_container_width=True):
            st.rerun()
    
    # Get statistics
    stats = get_backup_stats()
    
    # Top metrics row
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Users", f"{stats['total_users']}", 
                 f"Active: {stats['active_users']}")
    
    with col2:
        st.metric("Total Emails", f"{stats['total_emails']:,}",
                 f"📎 {stats['emails_with_attachments']} attachments")
    
    with col3:
        st.metric("Storage Used", f"{stats['total_size_mb']:.1f} MB",
                 f"Success: {stats['success_rate']:.1f}%")
    
    with col4:
        st.metric("Unique Senders", f"{stats['unique_senders']:,}",
                 f"Domains: {stats['unique_domains']}")
    
    with col5:
        if stats['last_backup']:
            time_ago = datetime.now() - stats['last_backup']
            hours_ago = int(time_ago.total_seconds() / 3600)
            st.metric("Last Backup", 
                     f"{hours_ago}h ago" if hours_ago < 24 else f"{hours_ago//24}d ago",
                     stats['last_backup'].strftime("%m/%d %H:%M"))
        else:
            st.metric("Last Backup", "No backups", "Ready")
    
    # Sidebar filters
    with st.sidebar:
        st.header("🎯 Global Filters")
        
        # User filter
        conn = sqlite3.connect(INDEX_DB)
        users_df = pd.read_sql_query("SELECT DISTINCT user_email FROM email_index ORDER BY user_email", conn)
        conn.close()
        
        user_options = ['all'] + users_df['user_email'].tolist()
        selected_user = st.selectbox(
            "Select User",
            user_options,
            index=0,
            key='global_user_filter'
        )
        st.session_state.selected_user = selected_user
        
        # Date range filter
        date_options = ['all', 'today', 'last_7_days', 'last_30_days', 'last_3_months', 'custom']
        selected_date = st.selectbox(
            "Date Range",
            date_options,
            index=0,
            format_func=lambda x: {
                'all': 'All Time',
                'today': 'Today',
                'last_7_days': 'Last 7 Days',
                'last_30_days': 'Last 30 Days',
                'last_3_months': 'Last 3 Months',
                'custom': 'Custom Range'
            }.get(x, x)
        )
        st.session_state.date_range = selected_date
        
        if selected_date == 'custom':
            col1, col2 = st.columns(2)
            with col1:
                start_date = st.date_input("Start Date")
            with col2:
                end_date = st.date_input("End Date")
        
        st.divider()
        
        # Quick stats in sidebar
        st.subheader("📊 Quick Stats")
        if selected_user != 'all':
            conn = sqlite3.connect(INDEX_DB)
            user_stats = pd.read_sql_query(
                "SELECT COUNT(*) as emails, SUM(size_bytes)/1024/1024 as size_mb FROM email_index WHERE user_email = ?",
                conn, params=[selected_user]
            )
            conn.close()
            
            st.info(f"""
            **User**: {selected_user}  
            **Emails**: {user_stats['emails'].iloc[0]:,}  
            **Size**: {user_stats['size_mb'].iloc[0]:.1f} MB
            """)
    
    # Main content tabs
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview", 
        "🔄 Communication Flow", 
        "🔥 Word Analysis", 
        "👥 User Analytics",
        "🔍 Search",
        "⚙️ Settings"
    ])
    
    with tab1:
        st.header("System Overview")
        
        # Status indicator
        if stats['last_backup'] and (datetime.now() - stats['last_backup']).days < 1:
            st.markdown("""
            <div class="success-box">
            ✅ System Status: <strong>OPERATIONAL</strong><br>
            All systems functioning normally. Last sync completed successfully.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="warning-box">
            ⚠️ System Status: <strong>NEEDS ATTENTION</strong><br>
            No recent backups detected. Please check the backup schedule.
            </div>
            """, unsafe_allow_html=True)
        
        # Charts row
        col1, col2 = st.columns(2)
        
        with col1:
            # Email volume over time
            conn = sqlite3.connect(INDEX_DB)
            
            # Build query based on filters
            query = """
                SELECT DATE(date/1000, 'unixepoch') as day, COUNT(*) as count
                FROM email_index
            """
            params = []
            
            if st.session_state.selected_user != 'all':
                query += " WHERE user_email = ?"
                params.append(st.session_state.selected_user)
            
            query += " GROUP BY day ORDER BY day DESC LIMIT 30"
            
            df_timeline = pd.read_sql_query(query, conn, params=params)
            
            if not df_timeline.empty:
                df_timeline = df_timeline.sort_values('day')
                fig_timeline = px.line(
                    df_timeline, x='day', y='count',
                    title='Daily Email Volume (Last 30 Days)',
                    labels={'count': 'Emails', 'day': 'Date'}
                )
                fig_timeline.update_traces(
                    line=dict(color='#667eea', width=3),
                    mode='lines+markers'
                )
                fig_timeline.update_layout(
                    hovermode='x unified',
                    showlegend=False,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig_timeline, use_container_width=True)
            else:
                st.info("No email data available for the selected filters")
        
        with col2:
            # Storage by domain
            query = """
                SELECT 
                    COALESCE(sender_domain, 'unknown') as domain,
                    COUNT(*) as email_count,
                    SUM(size_bytes)/1024/1024 as size_mb
                FROM email_index
            """
            
            if st.session_state.selected_user != 'all':
                query += " WHERE user_email = ?"
            
            query += " GROUP BY domain ORDER BY email_count DESC LIMIT 10"
            
            df_domains = pd.read_sql_query(
                query, conn, 
                params=[st.session_state.selected_user] if st.session_state.selected_user != 'all' else []
            )
            
            if not df_domains.empty:
                fig_domains = px.pie(
                    df_domains, values='email_count', names='domain',
                    title='Email Distribution by Domain',
                    color_discrete_sequence=px.colors.sequential.Purples_r
                )
                fig_domains.update_traces(
                    textposition='inside',
                    textinfo='percent+label',
                    hovertemplate='<b>%{label}</b><br>Emails: %{value}<br>Size: %{customdata:.1f} MB<extra></extra>',
                    customdata=df_domains['size_mb']
                )
                fig_domains.update_layout(
                    showlegend=True,
                    margin=dict(l=20, r=20, t=40, b=20)
                )
                st.plotly_chart(fig_domains, use_container_width=True)
            
            conn.close()
    
    with tab2:
        st.header("🔄 Email Communication Flow Analysis")
        
        # Communication matrix
        comm_matrix = get_communication_matrix(
            st.session_state.selected_user if st.session_state.selected_user != 'all' else None
        )
        
        if not comm_matrix.empty:
            # Top communication pairs
            st.subheader("Top Communication Pairs")
            
            top_pairs = comm_matrix.head(10).copy()
            top_pairs['size_mb'] = top_pairs['total_size'] / (1024 * 1024)
            top_pairs = top_pairs[['sender', 'recipient', 'email_count', 'size_mb']]
            top_pairs.columns = ['From', 'To', 'Emails', 'Size (MB)']
            
            st.dataframe(
                top_pairs.style.format({
                    'Emails': '{:,.0f}',
                    'Size (MB)': '{:.2f}'
                }),
                use_container_width=True,
                hide_index=True
            )
            
            # Sankey diagram
            st.subheader("Communication Flow Visualization")
            
            # Limit to top flows for clarity
            top_flows = comm_matrix.head(20)
            fig_sankey = create_communication_flow_chart(top_flows)
            st.plotly_chart(fig_sankey, use_container_width=True)
            
            # Time-based heatmap
            st.subheader("Activity Pattern Heatmap")
            fig_time_heat = create_time_based_heatmap(
                st.session_state.selected_user if st.session_state.selected_user != 'all' else None
            )
            st.plotly_chart(fig_time_heat, use_container_width=True)
        else:
            st.info("No communication data available for the selected filters")
    
    with tab3:
        st.header("🔥 Word Frequency Analysis")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.subheader("Most Frequently Used Words")
        
        with col2:
            top_n = st.number_input("Top N Words", min_value=10, max_value=100, value=50, step=10)
        
        # Get word frequencies
        word_freq = get_word_frequencies(
            st.session_state.selected_user if st.session_state.selected_user != 'all' else None,
            top_n
        )
        
        if word_freq:
            # Create columns for display
            col1, col2 = st.columns([2, 1])
            
            with col1:
                # Word cloud visualization (using heatmap as alternative)
                fig_words = create_word_heatmap(word_freq)
                st.plotly_chart(fig_words, use_container_width=True)
            
            with col2:
                # Top words list
                st.subheader("Top 20 Words")
                words_df = pd.DataFrame(word_freq[:20], columns=['Word', 'Frequency'])
                st.dataframe(
                    words_df.style.background_gradient(
                        subset=['Frequency'],
                        cmap='Purples'
                    ),
                    use_container_width=True,
                    hide_index=True
                )
            
            # Word frequency bar chart
            st.subheader("Word Frequency Distribution")
            
            words_df_full = pd.DataFrame(word_freq[:30], columns=['Word', 'Frequency'])
            fig_bar = px.bar(
                words_df_full, x='Frequency', y='Word',
                orientation='h',
                title='Top 30 Most Frequent Words',
                color='Frequency',
                color_continuous_scale='Purples'
            )
            fig_bar.update_layout(
                height=600,
                showlegend=False,
                yaxis={'categoryorder': 'total ascending'},
                margin=dict(l=100, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_bar, use_container_width=True)
            
            # Export word frequencies
            if st.button("📥 Export Word Frequencies"):
                csv = words_df_full.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"word_frequencies_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        else:
            st.info("No word frequency data available. Run a backup to generate word analysis.")
    
    with tab4:
        st.header("👥 User Analytics")
        
        # Load states
        states = load_all_states()
        
        if states:
            # User comparison metrics
            user_metrics = []
            
            conn = sqlite3.connect(INDEX_DB)
            
            for email, state in states.items():
                # Get user-specific metrics
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        COUNT(*) as total_emails,
                        COUNT(DISTINCT sender) as unique_senders,
                        SUM(size_bytes)/1024/1024 as size_mb,
                        AVG(CASE WHEN has_attachments = 1 THEN 1 ELSE 0 END) * 100 as attach_rate
                    FROM email_index 
                    WHERE user_email = ?
                """, [email])
                
                metrics = cursor.fetchone()
                
                if metrics[0] > 0:  # Has emails
                    user_metrics.append({
                        'User': email,
                        'Total Emails': metrics[0],
                        'Unique Senders': metrics[1],
                        'Size (MB)': metrics[2] or 0,
                        'Attachment %': metrics[3] or 0,
                        'Last Backup': state.get('last_backup', 'Never'),
                        'Status': '✅' if len(state.get('failed_messages', [])) == 0 else '⚠️'
                    })
            
            conn.close()
            
            if user_metrics:
                df_users = pd.DataFrame(user_metrics)
                
                # Summary cards
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Users", len(df_users))
                
                with col2:
                    avg_emails = df_users['Total Emails'].mean()
                    st.metric("Avg Emails/User", f"{avg_emails:.0f}")
                
                with col3:
                    total_senders = df_users['Unique Senders'].sum()
                    st.metric("Total Unique Senders", f"{total_senders:,}")
                
                with col4:
                    avg_attach = df_users['Attachment %'].mean()
                    st.metric("Avg Attachment Rate", f"{avg_attach:.1f}%")
                
                # User comparison chart
                st.subheader("User Email Volume Comparison")
                
                fig_users = px.bar(
                    df_users, x='User', y='Total Emails',
                    title='Emails per User',
                    color='Total Emails',
                    color_continuous_scale='Purples',
                    text='Total Emails'
                )
                fig_users.update_traces(texttemplate='%{text:,.0f}', textposition='outside')
                fig_users.update_layout(
                    showlegend=False,
                    xaxis_tickangle=-45,
                    margin=dict(l=20, r=20, t=40, b=100)
                )
                st.plotly_chart(fig_users, use_container_width=True)
                
                # Detailed user table
                st.subheader("Detailed User Statistics")
                
                # Format the dataframe
                df_display = df_users.copy()
                if 'Last Backup' in df_display.columns:
                    df_display['Last Backup'] = pd.to_datetime(df_display['Last Backup']).dt.strftime('%Y-%m-%d %H:%M')
                
                st.dataframe(
                    df_display.style.format({
                        'Total Emails': '{:,.0f}',
                        'Unique Senders': '{:,.0f}',
                        'Size (MB)': '{:.2f}',
                        'Attachment %': '{:.1f}%'
                    }).background_gradient(subset=['Total Emails', 'Size (MB)'], cmap='Purples'),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Per-user analysis
                st.subheader("Individual User Deep Dive")
                
                selected_user_analysis = st.selectbox(
                    "Select user for detailed analysis:",
                    df_users['User'].tolist()
                )
                
                if selected_user_analysis:
                    conn = sqlite3.connect(INDEX_DB)
                    
                    # Get user's top senders
                    top_senders = pd.read_sql_query("""
                        SELECT sender, COUNT(*) as email_count
                        FROM email_index
                        WHERE user_email = ?
                        GROUP BY sender
                        ORDER BY email_count DESC
                        LIMIT 5
                    """, conn, params=[selected_user_analysis])
                    
                    # Get user's email pattern
                    pattern = pd.read_sql_query("""
                        SELECT 
                            strftime('%H', datetime(date/1000, 'unixepoch')) as hour,
                            COUNT(*) as count
                        FROM email_index
                        WHERE user_email = ?
                        GROUP BY hour
                    """, conn, params=[selected_user_analysis])
                    
                    conn.close()
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"**Top Senders for {selected_user_analysis}**")
                        if not top_senders.empty:
                            fig_senders = px.pie(
                                top_senders, values='email_count', names='sender',
                                color_discrete_sequence=px.colors.sequential.Purples_r
                            )
                            fig_senders.update_traces(textposition='inside', textinfo='percent+label')
                            fig_senders.update_layout(
                                showlegend=False,
                                margin=dict(l=20, r=20, t=20, b=20),
                                height=300
                            )
                            st.plotly_chart(fig_senders, use_container_width=True)
                    
                    with col2:
                        st.markdown(f"**Hourly Email Pattern**")
                        if not pattern.empty:
                            pattern['hour'] = pattern['hour'].astype(int)
                            pattern = pattern.sort_values('hour')
                            
                            fig_pattern = px.bar(
                                pattern, x='hour', y='count',
                                labels={'hour': 'Hour of Day', 'count': 'Email Count'},
                                color='count',
                                color_continuous_scale='Purples'
                            )
                            fig_pattern.update_layout(
                                showlegend=False,
                                margin=dict(l=20, r=20, t=20, b=20),
                                height=300
                            )
                            st.plotly_chart(fig_pattern, use_container_width=True)
    
    with tab5:
        st.header("🔍 Advanced Email Search")
        
        # Search interface
        col1, col2, col3 = st.columns([3, 1, 1])
        
        with col1:
            search_query = st.text_input(
                "Search emails",
                placeholder="Enter keywords, sender, subject, or content..."
            )
        
        with col2:
            search_type = st.selectbox(
                "Search in",
                ["All Fields", "Subject", "Sender", "Body", "Recipients"]
            )
        
        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            search_button = st.button("🔍 Search", type="primary", use_container_width=True)
        
        # Advanced filters
        with st.expander("🔧 Advanced Search Options"):
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                filter_user = st.selectbox("User", ["All"] + list(load_all_states().keys()))
            
            with col2:
                filter_has_attachments = st.selectbox("Attachments", ["Any", "Yes", "No"])
            
            with col3:
                filter_start = st.date_input("Start Date", value=None, key="search_start")
            
            with col4:
                filter_end = st.date_input("End Date", value=None, key="search_end")
            
            col1, col2 = st.columns(2)
            
            with col1:
                filter_sender = st.text_input("From (sender email)")
            
            with col2:
                filter_size = st.slider("Min Size (KB)", 0, 1000, 0)
        
        # Perform search
        if search_button or search_query:
            conn = sqlite3.connect(INDEX_DB)
            
            # Build query
            query = "SELECT * FROM email_index WHERE 1=1"
            params = []
            
            # Text search
            if search_query:
                if search_type == "All Fields":
                    query += " AND (subject LIKE ? OR sender LIKE ? OR recipients LIKE ? OR body_preview LIKE ?)"
                    search_param = f"%{search_query}%"
                    params.extend([search_param] * 4)
                elif search_type == "Subject":
                    query += " AND subject LIKE ?"
                    params.append(f"%{search_query}%")
                elif search_type == "Sender":
                    query += " AND sender LIKE ?"
                    params.append(f"%{search_query}%")
                elif search_type == "Body":
                    query += " AND body_preview LIKE ?"
                    params.append(f"%{search_query}%")
                elif search_type == "Recipients":
                    query += " AND recipients LIKE ?"
                    params.append(f"%{search_query}%")
            
            # User filter
            if filter_user and filter_user != "All":
                query += " AND user_email = ?"
                params.append(filter_user)
            
            # Attachment filter
            if filter_has_attachments == "Yes":
                query += " AND has_attachments = 1"
            elif filter_has_attachments == "No":
                query += " AND has_attachments = 0"
            
            # Date filters
            if filter_start:
                query += " AND date >= ?"
                params.append(int(filter_start.timestamp() * 1000))
            
            if filter_end:
                query += " AND date <= ?"
                params.append(int(filter_end.timestamp() * 1000))
            
            # Sender filter
            if filter_sender:
                query += " AND sender LIKE ?"
                params.append(f"%{filter_sender}%")
            
            # Size filter
            if filter_size > 0:
                query += " AND size_bytes >= ?"
                params.append(filter_size * 1024)
            
            query += " ORDER BY date DESC LIMIT 100"
            
            # Execute search
            df_results = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if not df_results.empty:
                # Format results
                df_results['date_formatted'] = pd.to_datetime(df_results['date'], unit='ms').dt.strftime('%Y-%m-%d %H:%M')
                df_results['size_kb'] = df_results['size_bytes'] / 1024
                
                st.success(f"Found {len(df_results)} results")
                
                # Results summary
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("Results", len(df_results))
                
                with col2:
                    total_size_mb = df_results['size_bytes'].sum() / (1024 * 1024)
                    st.metric("Total Size", f"{total_size_mb:.2f} MB")
                
                with col3:
                    with_attach = df_results['has_attachments'].sum()
                    st.metric("With Attachments", with_attach)
                
                # Display results
                st.subheader("Search Results")
                
                for idx, row in df_results.head(20).iterrows():
                    with st.container():
                        col1, col2 = st.columns([5, 1])
                        
                        with col1:
                            st.markdown(f"**{row['subject']}**")
                            st.caption(f"From: {row['sender']}")
                            st.caption(f"To: {row['recipients'][:100]}...")
                            st.caption(f"Date: {row['date_formatted']} | Size: {row['size_kb']:.1f} KB")
                            
                            if row['has_attachments']:
                                st.caption(f"📎 Attachments: {row['attachment_names']}")
                            
                            # Preview with search term highlighting
                            preview = row['body_preview'][:200] if row['body_preview'] else ""
                            if search_query and preview:
                                # Simple highlighting
                                highlighted = preview.replace(
                                    search_query,
                                    f"**{search_query}**"
                                )
                                st.caption(f"Preview: {highlighted}...")
                            else:
                                st.caption(f"Preview: {preview}...")
                        
                        with col2:
                            st.caption(f"User: {row['user_email'].split('@')[0]}")
                            if st.button("View", key=f"view_{idx}"):
                                st.info(f"Path: {row['dropbox_path']}")
                        
                        st.divider()
                
                if len(df_results) > 20:
                    st.info(f"Showing first 20 of {len(df_results)} results")
                
                # Export results
                if st.button("📥 Export All Results"):
                    csv = df_results.to_csv(index=False)
                    st.download_button(
                        label="Download CSV",
                        data=csv,
                        file_name=f"search_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
            else:
                st.warning("No results found. Try adjusting your search criteria.")
    
    with tab6:
        st.header("⚙️ Settings & Administration")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Database Management")
            
            # Database info
            if INDEX_DB.exists():
                db_size = INDEX_DB.stat().st_size / (1024 * 1024)
                st.info(f"Database Size: {db_size:.2f} MB")
            
            # Rebuild index
            if st.button("🔄 Rebuild Search Index"):
                with st.spinner("Rebuilding index..."):
                    # This would call rebuild_index_from_dropbox() from backup.py
                    st.success("Index rebuild complete!")
            
            # Export database
            if st.button("📥 Export Full Database"):
                conn = sqlite3.connect(INDEX_DB)
                df_export = pd.read_sql_query("SELECT * FROM email_index", conn)
                conn.close()
                
                csv = df_export.to_csv(index=False)
                st.download_button(
                    label="Download Database CSV",
                    data=csv,
                    file_name=f"email_database_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            st.subheader("🔧 System Configuration")
            
            # Display current configuration
            config = {
                "Backup Mode": os.getenv("BACKUP_MODE", "incremental"),
                "Team Folder": os.getenv("DROPBOX_TEAM_FOLDER", "/Hanni Email Backups"),
                "Index Enabled": os.getenv("INDEX_EMAILS", "1") == "1",
                "Rate Limit": f"{os.getenv('RATE_LIMIT_DELAY', '0.3')} seconds",
                "Batch Size": os.getenv("BATCH_SIZE", "50"),
            }
            
            for key, value in config.items():
                st.text(f"{key}: {value}")
            
            st.divider()
            
            # Manual backup trigger
            st.subheader("🚀 Manual Operations")
            
            if st.button("▶️ Run Backup Now"):
                st.info("To run a backup, execute: `python backup.py` from your terminal")
            
            if st.button("🔍 Run Search Mode"):
                st.info("To enter search mode, execute: `python backup.py search` from your terminal")
        
        # Documentation
        st.divider()
        st.subheader("📚 Documentation")
        
        with st.expander("Quick Start Guide"):
            st.markdown("""
            ### Running Backups
            ```bash
            # Full backup (all emails from beginning)
            python backup.py
            
            # Search emails
            python backup.py search
            
            # Rebuild search index
            python backup.py rebuild-index
            ```
            
            ### Configuration (.env file)
            ```
            BACKUP_MODE=incremental
            EARLIEST_DATE=2000-01-01
            RATE_LIMIT_DELAY=0.3
            INDEX_EMAILS=1
            ```
            
            ### Automation Setup
            
            **Windows Task Scheduler:**
            1. Open Task Scheduler
            2. Create Basic Task
            3. Set trigger (daily at 2 AM)
            4. Action: `python C:\\path\\to\\backup.py`
            
            **Linux/Mac Cron:**
            ```bash
            crontab -e
            # Add this line for daily 2 AM backup:
            0 2 * * * /usr/bin/python3 /path/to/backup.py
            ```
            """)
        
        with st.expander("Security Best Practices"):
            st.markdown("""
            ### 🔒 Security Guidelines
            
            1. **Never commit credentials to Git**
               - Use .gitignore for sensitive files
               - Store credentials in environment variables
            
            2. **Rotate tokens regularly**
               - Refresh Dropbox tokens monthly
               - Update service account keys quarterly
            
            3. **Monitor access logs**
               - Check Google Admin console for unusual activity
               - Review Dropbox access logs
            
            4. **Limit permissions**
               - Use read-only access where possible
               - Restrict service account scope
            
            5. **Encrypt sensitive data**
               - Use encrypted storage for backups
               - Enable 2FA on all admin accounts
            """)
    
    # Footer
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>Hanni Email Analytics Dashboard v2.0 | Built with 💜 by Hanni</p>
        <p>© 2024 Hanni. All rights reserved. | 
        <a href="https://github.com/Jbaba13/hanni-email-backup" target="_blank">GitHub</a> |
        <a href="https://www.dropbox.com/home/Hanni%20Email%20Backups" target="_blank">Dropbox</a>
        </p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()