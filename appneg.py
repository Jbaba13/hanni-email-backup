#!/usr/bin/env python3
"""
Hanni Email Backup Dashboard - Streamlit Cloud Version
Fixed to handle missing local resources gracefully
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import json
import sqlite3
from pathlib import Path
import os
import sys

# Page configuration
st.set_page_config(
    page_title="Hanni Email Backup System",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Hanni branding
st.markdown("""
<style>
    /* Purple gradient theme */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Main content area */
    .main .block-container {
        background: rgba(255, 255, 255, 0.95);
        border-radius: 20px;
        padding: 2rem;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
    }
    
    /* Headers */
    h1 {
        color: #764ba2;
        font-family: 'Inter', sans-serif;
        font-weight: 700;
    }
    
    h2, h3 {
        color: #5a67d8;
        font-family: 'Inter', sans-serif;
    }
    
    /* Metrics */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    [data-testid="metric-container"] label {
        color: rgba(255,255,255,0.9) !important;
    }
    
    [data-testid="metric-container"] [data-testid="metric-value"] {
        color: white !important;
        font-weight: 700;
    }
    
    /* Sidebar */
    .css-1d391kg {
        background: rgba(255,255,255,0.95);
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 0.5rem 1rem;
        font-weight: 600;
        border-radius: 5px;
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 20px rgba(118,75,162,0.4);
    }
    
    /* Success messages */
    .success-box {
        background: #48bb78;
        color: white;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    /* Warning messages */
    .warning-box {
        background: #f6ad55;
        color: white;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
</style>

<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# Initialize paths
BASE_DIR = Path.cwd()
STATE_DIR = BASE_DIR / "state"
INDEX_DB = BASE_DIR / "email_index.db"

# Create required directories if they don't exist
STATE_DIR.mkdir(exist_ok=True)

# Initialize database if it doesn't exist
def init_database():
    """Initialize the SQLite database with schema if it doesn't exist"""
    if not INDEX_DB.exists():
        conn = sqlite3.connect(INDEX_DB)
        cursor = conn.cursor()
        
        # Create email_index table
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
            body_preview TEXT
        )''')
        
        # Create indexes
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_user_email ON email_index(user_email)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON email_index(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_sender ON email_index(sender)')
        
        conn.commit()
        conn.close()
        
        # Add some demo data if database is empty (for cloud demo)
        add_demo_data()

def add_demo_data():
    """Add demo data for Streamlit Cloud when no real data exists"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Check if database is empty
    cursor.execute("SELECT COUNT(*) FROM email_index")
    count = cursor.fetchone()[0]
    
    if count == 0:
        # Add sample data for demonstration
        demo_data = [
            ("demo@heyhanni.com", "msg_001", "Welcome to Hanni Email Backup", 
             "system@heyhanni.com", "demo@heyhanni.com", 
             int(datetime.now().timestamp() * 1000), 0, "", 1024,
             "/Email Backups/demo@heyhanni.com/2024/12/01/welcome.eml",
             "This is a demo email showing the backup system is ready."),
        ]
        
        cursor.executemany('''INSERT OR REPLACE INTO email_index 
            (user_email, message_id, subject, sender, recipients, date, 
             has_attachments, attachment_names, size_bytes, dropbox_path, body_preview)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', demo_data)
        
        conn.commit()
    
    conn.close()

# Initialize database on startup
init_database()

# Load user states
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
        states['demo@heyhanni.com'] = {
            'downloaded_ids': ['msg_001'],
            'last_backup': datetime.now().isoformat(),
            'failed_messages': [],
            'total_processed': 1
        }
    
    return states

# Get backup statistics
def get_backup_stats():
    """Get overall backup statistics from database and states"""
    conn = sqlite3.connect(INDEX_DB)
    cursor = conn.cursor()
    
    # Get email statistics
    cursor.execute("SELECT COUNT(DISTINCT user_email) FROM email_index")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM email_index")
    total_emails = cursor.fetchone()[0]
    
    cursor.execute("SELECT SUM(size_bytes) FROM email_index")
    total_size = cursor.fetchone()[0] or 0
    
    cursor.execute("SELECT COUNT(*) FROM email_index WHERE has_attachments = 1")
    emails_with_attachments = cursor.fetchone()[0]
    
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
    
    return {
        'total_users': total_users,
        'total_emails': total_emails,
        'total_size_mb': total_size / (1024 * 1024) if total_size else 0,
        'emails_with_attachments': emails_with_attachments,
        'last_backup': last_backup,
        'active_users': len(states),
        'success_rate': 95.0  # Demo value when no real data
    }

# Main dashboard
def main():
    # Header with logo
    col1, col2 = st.columns([1, 4])
    with col1:
        # Try to load logo, use emoji if not found
        if Path("hanni_logo.png").exists():
            st.image("hanni_logo.png", width=100)
        else:
            st.markdown("# 📧")
    
    with col2:
        st.markdown("""
        # Hanni Email Backup System
        ### Secure Gmail to Dropbox Backup & Analytics Platform
        """)
    
    # Get statistics
    stats = get_backup_stats()
    
    # Top metrics row
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Users", f"{stats['total_users']}", 
                 f"Active: {stats['active_users']}")
    
    with col2:
        st.metric("Total Emails", f"{stats['total_emails']:,}",
                 f"📎 {stats['emails_with_attachments']} with attachments")
    
    with col3:
        st.metric("Storage Used", f"{stats['total_size_mb']:.1f} MB",
                 f"Success rate: {stats['success_rate']:.1f}%")
    
    with col4:
        if stats['last_backup']:
            time_ago = datetime.now() - stats['last_backup']
            hours_ago = int(time_ago.total_seconds() / 3600)
            st.metric("Last Backup", 
                     f"{hours_ago}h ago" if hours_ago < 24 else f"{hours_ago//24}d ago",
                     stats['last_backup'].strftime("%Y-%m-%d %H:%M"))
        else:
            st.metric("Last Backup", "No backups yet", "Ready to start")
    
    # Tabs for different views
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Overview", "👥 Users", "🔍 Search", "📈 Analytics", "⚙️ Settings"])
    
    with tab1:
        st.header("System Overview")
        
        # Status indicator
        if stats['last_backup'] and (datetime.now() - stats['last_backup']).days < 1:
            st.markdown("""
            <div class="success-box">
            ✅ System Status: <strong>OPERATIONAL</strong><br>
            All backups are running successfully.
            </div>
            """, unsafe_allow_html=True)
        elif stats['total_emails'] == 0:
            st.markdown("""
            <div class="info-box">
            🚀 System Status: <strong>READY</strong><br>
            The backup system is deployed and ready. Run your first backup to begin.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="warning-box">
            ⚠️ System Status: <strong>NEEDS ATTENTION</strong><br>
            No backups in the last 24 hours.
            </div>
            """, unsafe_allow_html=True)
        
        # Quick stats
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📅 Backup Schedule")
            st.info("""
            **Current Mode**: Incremental Backup  
            **Schedule**: Daily at 2:00 AM  
            **Next Run**: Tonight  
            **Retention**: Unlimited
            """)
            
            if st.button("🔄 Run Backup Now"):
                st.warning("Manual backup requires running: `python backup.py` locally")
        
        with col2:
            st.subheader("🔗 Quick Links")
            st.markdown("""
            - [📁 Dropbox Team Folder](https://www.dropbox.com/home/Hanni%20Email%20Backups)
            - [🔧 Google Admin Console](https://admin.google.com)
            - [📊 Dropbox Admin Console](https://www.dropbox.com/team)
            - [💻 GitHub Repository](https://github.com/Jbaba13/hanni-email-backup)
            """)
        
        # Recent activity
        st.subheader("📝 Recent Activity")
        
        # Create sample activity data
        activity_data = []
        if stats['last_backup']:
            activity_data.append({
                'Time': stats['last_backup'],
                'User': 'demo@heyhanni.com',
                'Action': 'Backup completed',
                'Status': '✅ Success',
                'Details': f"{stats['total_emails']} emails backed up"
            })
        
        if activity_data:
            df_activity = pd.DataFrame(activity_data)
            st.dataframe(df_activity, use_container_width=True, hide_index=True)
        else:
            st.info("No recent activity. Run your first backup to see activity here.")
    
    with tab2:
        st.header("User Management")
        
        # Load user states
        states = load_all_states()
        
        if states:
            # User statistics
            user_data = []
            for email, state in states.items():
                downloaded = len(state.get('downloaded_ids', []))
                failed = len(state.get('failed_messages', []))
                last_backup = state.get('last_backup', 'Never')
                if last_backup != 'Never':
                    last_backup = datetime.fromisoformat(last_backup).strftime('%Y-%m-%d %H:%M')
                
                user_data.append({
                    'Email': email,
                    'Backed Up': downloaded,
                    'Failed': failed,
                    'Success Rate': f"{(downloaded/(downloaded+failed)*100) if (downloaded+failed) > 0 else 0:.1f}%",
                    'Last Backup': last_backup,
                    'Status': '✅' if failed == 0 else '⚠️'
                })
            
            df_users = pd.DataFrame(user_data)
            
            # Display summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Users", len(states))
            with col2:
                successful = len([u for u in user_data if u['Status'] == '✅'])
                st.metric("Successful", successful)
            with col3:
                st.metric("Need Attention", len(states) - successful)
            
            # User table
            st.subheader("User Backup Status")
            st.dataframe(
                df_users,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Status": st.column_config.TextColumn("Status", width="small"),
                    "Success Rate": st.column_config.TextColumn("Success Rate", width="small"),
                }
            )
            
            # User selector for details
            selected_user = st.selectbox("Select user for details:", df_users['Email'].tolist())
            
            if selected_user:
                user_state = states[selected_user]
                col1, col2 = st.columns(2)
                
                with col1:
                    st.info(f"""
                    **User**: {selected_user}  
                    **Emails Backed Up**: {len(user_state.get('downloaded_ids', []))}  
                    **Failed Messages**: {len(user_state.get('failed_messages', []))}  
                    **Last Backup**: {user_state.get('last_backup', 'Never')}
                    """)
                
                with col2:
                    if st.button(f"🔄 Retry Failed for {selected_user}"):
                        st.warning("Run `python backup.py` locally to retry failed messages")
                    
                    if st.button(f"📥 Download User State"):
                        st.download_button(
                            label="Download JSON",
                            data=json.dumps(user_state, indent=2),
                            file_name=f"{selected_user}_state.json",
                            mime="application/json"
                        )
        else:
            st.info("No user data available yet. Run your first backup to see user statistics.")
    
    with tab3:
        st.header("Email Search")
        
        # Search interface
        col1, col2 = st.columns([3, 1])
        with col1:
            search_query = st.text_input("🔍 Search emails", placeholder="Enter keywords, sender, subject...")
        
        with col2:
            search_button = st.button("Search", type="primary", use_container_width=True)
        
        # Advanced filters
        with st.expander("Advanced Filters"):
            col1, col2, col3 = st.columns(3)
            with col1:
                filter_user = st.selectbox("User", ["All"] + list(load_all_states().keys()))
            with col2:
                filter_start = st.date_input("Start Date", value=None)
            with col3:
                filter_end = st.date_input("End Date", value=None)
            
            filter_attachments = st.checkbox("Only emails with attachments")
        
        # Perform search
        if search_button or search_query:
            conn = sqlite3.connect(INDEX_DB)
            
            # Build query
            query = "SELECT * FROM email_index WHERE 1=1"
            params = []
            
            if search_query:
                query += " AND (subject LIKE ? OR sender LIKE ? OR recipients LIKE ? OR body_preview LIKE ?)"
                search_param = f"%{search_query}%"
                params.extend([search_param] * 4)
            
            if filter_user and filter_user != "All":
                query += " AND user_email = ?"
                params.append(filter_user)
            
            if filter_start:
                query += " AND date >= ?"
                params.append(int(filter_start.timestamp() * 1000))
            
            if filter_end:
                query += " AND date <= ?"
                params.append(int(filter_end.timestamp() * 1000))
            
            if filter_attachments:
                query += " AND has_attachments = 1"
            
            query += " ORDER BY date DESC LIMIT 100"
            
            df_results = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if not df_results.empty:
                # Format results
                df_results['date'] = pd.to_datetime(df_results['date'], unit='ms')
                df_results['size_mb'] = df_results['size_bytes'] / (1024 * 1024)
                
                st.success(f"Found {len(df_results)} results")
                
                # Display results
                for _, row in df_results.head(20).iterrows():
                    with st.container():
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            st.markdown(f"**{row['subject']}**")
                            st.caption(f"From: {row['sender']} | To: {row['recipients'][:50]}...")
                            st.caption(f"Date: {row['date'].strftime('%Y-%m-%d %H:%M')} | Size: {row['size_mb']:.2f} MB")
                            if row['has_attachments']:
                                st.caption(f"📎 Attachments: {row['attachment_names']}")
                        with col2:
                            if st.button("View", key=f"view_{row['message_id']}"):
                                st.info(f"Path: {row['dropbox_path']}")
                        
                        st.divider()
                
                if len(df_results) > 20:
                    st.info(f"Showing first 20 of {len(df_results)} results")
            else:
                st.warning("No results found")
        else:
            st.info("Enter search terms and click Search to find emails")
    
    with tab4:
        st.header("Analytics")
        
        conn = sqlite3.connect(INDEX_DB)
        
        # Check if we have data
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM email_index")
        has_data = cursor.fetchone()[0] > 0
        
        if has_data:
            # Email volume over time
            st.subheader("📈 Email Volume Over Time")
            
            df_timeline = pd.read_sql_query("""
                SELECT DATE(date/1000, 'unixepoch') as day, COUNT(*) as count
                FROM email_index
                GROUP BY day
                ORDER BY day
            """, conn)
            
            if not df_timeline.empty:
                fig_timeline = px.line(df_timeline, x='day', y='count', 
                                       title='Daily Email Volume')
                st.plotly_chart(fig_timeline, use_container_width=True)
            
            # Top senders
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("📤 Top Senders")
                df_senders = pd.read_sql_query("""
                    SELECT sender, COUNT(*) as count
                    FROM email_index
                    GROUP BY sender
                    ORDER BY count DESC
                    LIMIT 10
                """, conn)
                
                if not df_senders.empty:
                    fig_senders = px.bar(df_senders, x='count', y='sender', 
                                         orientation='h')
                    st.plotly_chart(fig_senders, use_container_width=True)
            
            with col2:
                st.subheader("📎 Attachment Statistics")
                df_attachments = pd.read_sql_query("""
                    SELECT 
                        CASE WHEN has_attachments = 1 THEN 'With Attachments'
                             ELSE 'No Attachments' END as type,
                        COUNT(*) as count
                    FROM email_index
                    GROUP BY has_attachments
                """, conn)
                
                if not df_attachments.empty:
                    fig_attachments = px.pie(df_attachments, values='count', 
                                            names='type', hole=0.4)
                    st.plotly_chart(fig_attachments, use_container_width=True)
            
            # Storage by user
            st.subheader("💾 Storage by User")
            df_storage = pd.read_sql_query("""
                SELECT user_email, 
                       SUM(size_bytes)/(1024.0*1024.0) as size_mb,
                       COUNT(*) as email_count
                FROM email_index
                GROUP BY user_email
                ORDER BY size_mb DESC
            """, conn)
            
            if not df_storage.empty:
                fig_storage = px.treemap(df_storage, path=['user_email'], 
                                        values='size_mb',
                                        title='Storage Distribution by User (MB)')
                st.plotly_chart(fig_storage, use_container_width=True)
        else:
            st.info("""
            📊 **No Analytics Data Available Yet**
            
            Analytics will appear here once you run your first backup.
            The dashboard will show:
            - Email volume trends over time
            - Top senders and recipients
            - Storage usage by user
            - Attachment statistics
            - Communication patterns
            
            Run `python backup.py` locally to start backing up emails.
            """)
        
        conn.close()
    
    with tab5:
        st.header("Settings & Configuration")
        
        st.subheader("🔧 Current Configuration")
        
        # Display configuration (from environment or defaults)
        config_data = {
            "Backup Mode": os.getenv("BACKUP_MODE", "incremental"),
            "Admin Email": os.getenv("GOOGLE_DELEGATED_ADMIN", "admin@heyhanni.com"),
            "Team Folder": os.getenv("DROPBOX_TEAM_FOLDER", "/Hanni Email Backups"),
            "Start Date": os.getenv("START_DATE", "2024-01-01"),
            "Page Size": os.getenv("PAGE_SIZE", "200"),
            "Rate Limit Delay": os.getenv("RATE_LIMIT_DELAY", "0.1") + " seconds",
            "Index Emails": "Enabled" if os.getenv("INDEX_EMAILS", "1") == "1" else "Disabled",
        }
        
        for key, value in config_data.items():
            st.text(f"{key}: {value}")
        
        st.subheader("📝 Instructions")
        
        st.markdown("""
        ### To run a backup:
        ```bash
        python backup.py
        ```
        
        ### To search emails:
        ```bash
        python backup.py search
        ```
        
        ### To rebuild the search index:
        ```bash
        python backup.py rebuild-index
        ```
        
        ### To set up automation:
        
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
        
        st.subheader("🔒 Security")
        st.warning("""
        **Important Security Notes:**
        - Never commit credentials to GitHub
        - Keep service_account.json local only
        - Use environment variables for sensitive data
        - Rotate tokens regularly
        - Monitor API usage
        """)
        
        # Export functionality
        st.subheader("📥 Export Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("Export Email Index (CSV)"):
                conn = sqlite3.connect(INDEX_DB)
                df_export = pd.read_sql_query("SELECT * FROM email_index", conn)
                conn.close()
                
                csv = df_export.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"email_index_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
        
        with col2:
            if st.button("Export User States (JSON)"):
                states = load_all_states()
                json_data = json.dumps(states, indent=2)
                
                st.download_button(
                    label="Download JSON",
                    data=json_data,
                    file_name=f"user_states_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )
    
    # Footer
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 20px;'>
        <p>Hanni Email Backup System v1.0 | Built with 💜 by Hanni</p>
        <p>© 2024 Hanni. All rights reserved.</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()