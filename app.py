#!/usr/bin/env python3
"""
Streamlit Web Interface for Gmail -> Dropbox Backup System
Complete fresh version with working Hanni branding
"""

import streamlit as st
import pandas as pd
import sqlite3
import os
import json
import time
import datetime as dt
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter, defaultdict
import re
from dotenv import load_dotenv
from PIL import Image

from PIL import Image

# Page configuration
try:
    logo = Image.open("hanni_logo.png")  # Or your logo filename
    st.set_page_config(
        page_title="Hanni - Email Backup System",
        page_icon=logo,
        layout="wide",
        initial_sidebar_state="expanded"
    )
except:
    # Fallback to emoji if logo file not found
    st.set_page_config(
        page_title="Hanni - Email Backup System",
        page_icon="💜",
        layout="wide",
        initial_sidebar_state="expanded"
    )

# Load environment variables
load_dotenv()

# Constants
BASE_DIR = Path(__file__).resolve().parent
STATE_DIR = BASE_DIR / "state"
INDEX_DB = BASE_DIR / "email_index.db"
DROPBOX_FOLDER = os.getenv("DROPBOX_TEAM_FOLDER", "/Hanni Email Backups")

# Custom CSS
st.markdown("""
<style>
    .stMetric {
        background: white;
        padding: 1.2rem;
        border-radius: 15px;
        box-shadow: 0 2px 15px rgba(118, 75, 162, 0.08);
        border: 1px solid rgba(118, 75, 162, 0.1);
    }
    
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 10px;
        padding: 0.6rem 2rem;
        font-weight: 600;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(118, 75, 162, 0.3);
    }
    
    .stTabs [data-baseweb="tab"] {
        background: white;
        border-radius: 10px;
        padding: 0.5rem 1rem;
        border: 2px solid #f0f2f6;
        font-weight: 500;
    }
    
    .stTabs [data-baseweb="tab"][aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: 2px solid transparent;
    }
</style>
""", unsafe_allow_html=True)

# Helper Functions
@st.cache_data(ttl=60)
def get_database_stats():
    """Get statistics from the email index database"""
    try:
        if not INDEX_DB.exists():
            return {
                'total_emails': 0,
                'total_users': 0,
                'total_storage_mb': 0,
                'recent_emails': 0
            }
            
        conn = sqlite3.connect(INDEX_DB)
        
        # Total emails
        total_emails = pd.read_sql_query("SELECT COUNT(*) as count FROM email_index", conn).iloc[0]['count']
        
        # Total users
        total_users = pd.read_sql_query("SELECT COUNT(DISTINCT user_email) as count FROM email_index", conn).iloc[0]['count']
        
        # Total storage
        total_bytes = pd.read_sql_query("SELECT SUM(size_bytes) as total FROM email_index", conn).iloc[0]['total'] or 0
        
        # Recent emails (last 30 days)
        thirty_days_ago = int((dt.datetime.now() - dt.timedelta(days=30)).timestamp() * 1000)
        recent_emails = pd.read_sql_query(
            f"SELECT COUNT(*) as count FROM email_index WHERE date > {thirty_days_ago}", 
            conn
        ).iloc[0]['count']
        
        conn.close()
        
        return {
            'total_emails': total_emails,
            'total_users': total_users,
            'total_storage_mb': total_bytes / (1024 * 1024),
            'recent_emails': recent_emails
        }
    except Exception as e:
        st.error(f"Database error: {e}")
        return {
            'total_emails': 0,
            'total_users': 0,
            'total_storage_mb': 0,
            'recent_emails': 0
        }

@st.cache_data(ttl=60)
def get_user_backup_status():
    """Get backup status for all users"""
    users_data = []
    
    try:
        if not STATE_DIR.exists():
            return pd.DataFrame()
            
        state_files = list(STATE_DIR.glob("*.json"))
        
        for state_file in state_files:
            try:
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                user_email = state_file.stem.replace('_', '@').replace('@com', '.com')
                
                if state.get('backup_in_progress'):
                    status = "🔄 In Progress"
                    progress = state.get('messages_processed', 0) / max(state.get('total_messages', 1), 1) * 100
                elif state.get('backup_completed'):
                    status = "✅ Complete"
                    progress = 100
                else:
                    status = "⏸️ Paused"
                    progress = state.get('messages_processed', 0) / max(state.get('total_messages', 1), 1) * 100
                
                users_data.append({
                    'User': user_email,
                    'Status': status,
                    'Progress': f"{progress:.1f}%",
                    'Messages': f"{state.get('messages_downloaded', 0):,}",
                    'Last Update': state.get('backup_completed', state.get('backup_started', 'N/A'))[:19] if state.get('backup_completed') or state.get('backup_started') else 'N/A'
                })
            except Exception as e:
                continue
    except Exception as e:
        st.error(f"Error reading state files: {e}")
    
    return pd.DataFrame(users_data) if users_data else pd.DataFrame()

@st.cache_data(ttl=300)
def get_sender_receiver_analytics():
    """Get detailed sender and receiver analytics"""
    try:
        if not INDEX_DB.exists():
            return None
            
        conn = sqlite3.connect(INDEX_DB)
        
        query = """
        SELECT user_email, sender, recipients, date, size_bytes
        FROM email_index
        ORDER BY date DESC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            return None
        
        # Parse senders
        def extract_email(text):
            if not text:
                return ''
            match = re.search(r'[\w\.-]+@[\w\.-]+', text)
            return match.group(0).lower() if match else text.lower()
        
        df['sender_clean'] = df['sender'].apply(extract_email)
        
        # Parse recipients
        def extract_all_emails(text):
            if not text:
                return []
            emails = re.findall(r'[\w\.-]+@[\w\.-]+', text)
            return [e.lower() for e in emails]
        
        df['recipients_list'] = df['recipients'].apply(extract_all_emails)
        
        # Convert date to datetime
        df['datetime'] = pd.to_datetime(df['date'], unit='ms')
        
        return df
        
    except Exception as e:
        st.error(f"Error loading analytics data: {e}")
        return None

def format_bytes(bytes):
    """Format bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024.0
    return f"{bytes:.2f} PB"

# Main App
def main():
    # Clean Hanni header
    st.markdown('''
    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 50px 20px; border-radius: 0 0 30px 30px; text-align: center; margin: -50px -50px 30px -50px;">
        <h1 style="color: #d1547e; font-size: 60px; font-weight: bold; margin: 0;">hanni</h1>
        <h2 style="color: white; font-size: 28px; font-weight: 300; margin: 10px 0;">Email Backup System</h2>
        <p style="color: rgba(255, 255, 255, 0.9); font-size: 16px; margin: 10px 0;">Secure Gmail to Dropbox Backup & Analytics Platform</p>
    </div>
    ''', unsafe_allow_html=True)
    
    # Main tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 Dashboard", "🔍 Search", "📈 Analytics", "👥 Sender/Receiver Analysis", "⚙️ Settings"])
    
    # Tab 1: Dashboard
    with tab1:
        st.header("Backup Status Dashboard")
        
        # Metrics
        stats = get_database_stats()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Emails", f"{stats['total_emails']:,}", 
                     delta=f"+{stats['recent_emails']} (30 days)")
        with col2:
            st.metric("Active Users", stats['total_users'])
        with col3:
            st.metric("Storage Used", f"{stats['total_storage_mb']:.2f} MB")
        with col4:
            try:
                state_files = list(STATE_DIR.glob("*.json"))
                if state_files:
                    latest_time = max([f.stat().st_mtime for f in state_files])
                    last_run = dt.datetime.fromtimestamp(latest_time).strftime('%Y-%m-%d %H:%M')
                else:
                    last_run = "Never"
            except:
                last_run = "Unknown"
            st.metric("Last Backup", last_run)
        
        # User backup status table
        st.subheader("User Backup Status")
        user_df = get_user_backup_status()
        
        if not user_df.empty:
            def highlight_status(row):
                if '✅' in row['Status']:
                    return ['background-color: #d4edda'] * len(row)
                elif '🔄' in row['Status']:
                    return ['background-color: #fff3cd'] * len(row)
                else:
                    return ['background-color: #f8d7da'] * len(row)
            
            styled_df = user_df.style.apply(highlight_status, axis=1)
            st.dataframe(styled_df, width='stretch', hide_index=True)
        else:
            st.info("No backup data available yet. Run the backup script to start backing up emails.")
        
        # Quick actions
        st.subheader("Quick Actions")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("🚀 Start Backup", key="start_backup", help="Run backup.py"):
                st.info("Run `python backup.py` in your terminal to start backup")
        with col2:
            if st.button("🔄 Refresh Stats", key="refresh_stats"):
                st.cache_data.clear()
                st.rerun()
        with col3:
            if st.button("📥 Export Report", key="export_report"):
                report = {
                    'Generated': dt.datetime.now().isoformat(),
                    'Statistics': stats,
                    'Users': user_df.to_dict() if not user_df.empty else {}
                }
                st.download_button(
                    "Download JSON Report",
                    json.dumps(report, indent=2),
                    "backup_report.json",
                    "application/json"
                )
    
    # Tab 2: Search
    with tab2:
        st.header("Email Search")
        
        col1, col2 = st.columns(2)
        with col1:
            search_query = st.text_input("Search term", placeholder="Search in all fields...")
            sender_filter = st.text_input("Sender", placeholder="sender@example.com")
            subject_filter = st.text_input("Subject", placeholder="Meeting notes...")
        
        with col2:
            user_filter = st.selectbox(
                "User", 
                ["All"] + (user_df['User'].tolist() if not user_df.empty else [])
            )
            date_range = st.date_input(
                "Date range",
                value=(dt.date.today() - dt.timedelta(days=30), dt.date.today()),
                format="YYYY-MM-DD"
            )
            has_attachments = st.checkbox("Only emails with attachments")
        
        if st.button("🔍 Search", key="search_button"):
            try:
                conn = sqlite3.connect(INDEX_DB)
                
                conditions = []
                params = []
                
                if search_query:
                    conditions.append("""
                        (subject LIKE ? OR sender LIKE ? OR recipients LIKE ? OR body_preview LIKE ?)
                    """)
                    query_param = f"%{search_query}%"
                    params.extend([query_param] * 4)
                
                if user_filter != "All":
                    conditions.append("user_email = ?")
                    params.append(user_filter)
                
                if sender_filter:
                    conditions.append("sender LIKE ?")
                    params.append(f"%{sender_filter}%")
                
                if subject_filter:
                    conditions.append("subject LIKE ?")
                    params.append(f"%{subject_filter}%")
                
                if date_range and len(date_range) == 2:
                    start_ts = int(dt.datetime.combine(date_range[0], dt.time.min).timestamp() * 1000)
                    end_ts = int(dt.datetime.combine(date_range[1], dt.time.max).timestamp() * 1000)
                    conditions.append("date BETWEEN ? AND ?")
                    params.extend([start_ts, end_ts])
                
                if has_attachments:
                    conditions.append("has_attachments = 1")
                
                where_clause = " AND ".join(conditions) if conditions else "1=1"
                query = f"""
                    SELECT 
                        substr(date_str, 1, 19) as Date,
                        user_email as User,
                        subject as Subject,
                        sender as From,
                        CASE WHEN has_attachments THEN '📎 Yes' ELSE 'No' END as Attachments,
                        printf('%.2f KB', size_bytes / 1024.0) as Size
                    FROM email_index 
                    WHERE {where_clause}
                    ORDER BY date DESC
                    LIMIT 100
                """
                
                results_df = pd.read_sql_query(query, conn, params=params)
                conn.close()
                
                if not results_df.empty:
                    st.success(f"Found {len(results_df)} emails")
                    st.dataframe(results_df, width='stretch', hide_index=True)
                    
                    csv = results_df.to_csv(index=False)
                    st.download_button(
                        "📥 Download Results (CSV)",
                        csv,
                        "search_results.csv",
                        "text/csv"
                    )
                else:
                    st.info("No emails found matching your criteria")
                    
            except Exception as e:
                st.error(f"Search error: {e}")
    
    # Tab 3: Analytics
    with tab3:
        st.header("Email Analytics")
        
        try:
            if not INDEX_DB.exists():
                st.info("No email database found. Run the backup script first to index emails.")
            else:
                conn = sqlite3.connect(INDEX_DB)
                
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='email_index'")
                if not cursor.fetchone():
                    st.info("Email index table not found. Run the backup script to create the index.")
                    conn.close()
                else:
                    # Time series
                    st.subheader("Email Volume Over Time")
                    
                    time_query = """
                    SELECT 
                        DATE(date/1000, 'unixepoch') as day,
                        COUNT(*) as count
                    FROM email_index
                    GROUP BY day
                    ORDER BY day DESC
                    LIMIT 90
                    """
                    
                    time_df = pd.read_sql_query(time_query, conn)
                    
                    if not time_df.empty:
                        fig = px.line(time_df, x='day', y='count', 
                                     title='Daily Email Count (Last 90 Days)',
                                     labels={'day': 'Date', 'count': 'Emails'})
                        fig.update_traces(line_color='#764ba2')
                        st.plotly_chart(fig, use_container_width=True)
                    
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.subheader("Emails by User")
                        user_query = """
                        SELECT 
                            user_email,
                            COUNT(*) as email_count
                        FROM email_index
                        GROUP BY user_email
                        ORDER BY email_count DESC
                        LIMIT 10
                        """
                        
                        user_stats = pd.read_sql_query(user_query, conn)
                        
                        if not user_stats.empty:
                            fig = px.pie(user_stats, values='email_count', names='user_email',
                                        title='Email Distribution by User')
                            fig.update_traces(marker=dict(colors=px.colors.sequential.Purples_r))
                            st.plotly_chart(fig, use_container_width=True)
                    
                    with col2:
                        st.subheader("Attachment Statistics")
                        attach_query = """
                        SELECT 
                            CASE WHEN has_attachments THEN 'With Attachments' ELSE 'No Attachments' END as type,
                            COUNT(*) as count
                        FROM email_index
                        GROUP BY has_attachments
                        """
                        
                        attach_stats = pd.read_sql_query(attach_query, conn)
                        
                        if not attach_stats.empty:
                            fig = px.bar(attach_stats, x='type', y='count',
                                        title='Emails with Attachments',
                                        color='type',
                                        color_discrete_map={'With Attachments': '#764ba2', 
                                                           'No Attachments': '#667eea'})
                            st.plotly_chart(fig, use_container_width=True)
                    
                    conn.close()
                
        except Exception as e:
            st.error(f"Error loading analytics: {e}")
    
    # Tab 4: Sender/Receiver Analysis
    with tab4:
        st.header("👥 Sender/Receiver Analysis")
        
        df_analytics = get_sender_receiver_analytics()
        
        if df_analytics is not None and not df_analytics.empty:
            
            col1, col2 = st.columns(2)
            with col1:
                analysis_type = st.selectbox(
                    "Analysis Type",
                    ["Team Overview", "Individual User", "Domain Analysis", "Communication Patterns"]
                )
            
            with col2:
                if analysis_type == "Individual User":
                    selected_user = st.selectbox(
                        "Select User",
                        sorted(df_analytics['user_email'].unique())
                    )
                    df_filtered = df_analytics[df_analytics['user_email'] == selected_user]
                else:
                    df_filtered = df_analytics
                    selected_user = None
            
            date_filter = st.date_input(
                "Date Range for Analysis",
                value=(dt.date.today() - dt.timedelta(days=90), dt.date.today()),
                format="YYYY-MM-DD",
                key="sender_date_range"
            )
            
            if date_filter and len(date_filter) == 2:
                mask = (df_filtered['datetime'].dt.date >= date_filter[0]) & (df_filtered['datetime'].dt.date <= date_filter[1])
                df_filtered = df_filtered.loc[mask]
            
            if analysis_type == "Team Overview":
                st.subheader("📊 Team-Wide Email Statistics")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Top External Senders to Team")
                    external_senders = df_filtered[~df_filtered['sender_clean'].str.contains('@heyhanni.com', na=False)]
                    sender_counts = external_senders['sender_clean'].value_counts().head(15)
                    
                    if not sender_counts.empty:
                        fig = px.bar(
                            x=sender_counts.values, 
                            y=sender_counts.index,
                            orientation='h',
                            labels={'x': 'Email Count', 'y': 'Sender'},
                            title=f"Top 15 External Email Senders",
                            color=sender_counts.values,
                            color_continuous_scale='Purples'
                        )
                        fig.update_layout(height=500, showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("### Most Contacted Recipients")
                    all_recipients = []
                    for recipients in df_filtered['recipients_list']:
                        all_recipients.extend(recipients)
                    
                    external_recipients = [r for r in all_recipients if '@heyhanni.com' not in r]
                    recipient_counts = pd.Series(external_recipients).value_counts().head(15)
                    
                    if not recipient_counts.empty:
                        fig = px.bar(
                            x=recipient_counts.values,
                            y=recipient_counts.index,
                            orientation='h',
                            labels={'x': 'Times Contacted', 'y': 'Recipient'},
                            title=f"Top 15 External Recipients",
                            color=recipient_counts.values,
                            color_continuous_scale='Viridis'
                        )
                        fig.update_layout(height=500, showlegend=False)
                        st.plotly_chart(fig, use_container_width=True)
            
            elif analysis_type == "Individual User":
                st.subheader(f"📧 Email Analysis for {selected_user}")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Total Emails", len(df_filtered))
                with col2:
                    unique_senders = df_filtered['sender_clean'].nunique()
                    st.metric("Unique Senders", unique_senders)
                with col3:
                    all_user_recipients = []
                    for recipients in df_filtered['recipients_list']:
                        all_user_recipients.extend(recipients)
                    unique_recipients = len(set(all_user_recipients))
                    st.metric("Unique Recipients", unique_recipients)
                with col4:
                    avg_daily = len(df_filtered) / max((df_filtered['datetime'].max() - df_filtered['datetime'].min()).days, 1)
                    st.metric("Avg Emails/Day", f"{avg_daily:.1f}")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Top Senders to This User")
                    user_senders = df_filtered['sender_clean'].value_counts().head(10)
                    
                    fig = go.Figure(data=[
                        go.Bar(
                            x=user_senders.values,
                            y=user_senders.index,
                            orientation='h',
                            marker_color='#764ba2',
                            text=user_senders.values,
                            textposition='auto',
                        )
                    ])
                    fig.update_layout(
                        title=f"Top 10 Senders to {selected_user}",
                        xaxis_title="Email Count",
                        yaxis_title="Sender",
                        height=400,
                        showlegend=False
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("### This User Sends To")
                    user_sent = df_analytics[df_analytics['sender_clean'] == selected_user.lower()]
                    
                    if not user_sent.empty:
                        user_recipients = []
                        for recipients in user_sent['recipients_list']:
                            user_recipients.extend(recipients)
                        
                        recipient_counts = pd.Series(user_recipients).value_counts().head(10)
                        
                        fig = go.Figure(data=[
                            go.Bar(
                                x=recipient_counts.values,
                                y=recipient_counts.index,
                                orientation='h',
                                marker_color='#667eea',
                                text=recipient_counts.values,
                                textposition='auto',
                            )
                        ])
                        fig.update_layout(
                            title=f"Top 10 Recipients from {selected_user}",
                            xaxis_title="Email Count",
                            yaxis_title="Recipient",
                            height=400,
                            showlegend=False
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No sent emails found for this user")
            
            elif analysis_type == "Domain Analysis":
                st.subheader("🌐 Email Domain Analysis")
                
                df_filtered['sender_domain'] = df_filtered['sender_clean'].apply(
                    lambda x: x.split('@')[1] if '@' in x else 'unknown'
                )
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Top Sending Domains")
                    domain_counts = df_filtered['sender_domain'].value_counts().head(15)
                    
                    fig = px.pie(
                        values=domain_counts.values,
                        names=domain_counts.index,
                        title="Email Distribution by Domain",
                        color_discrete_sequence=px.colors.sequential.Purples_r
                    )
                    fig.update_traces(textposition='inside', textinfo='percent+label')
                    fig.update_layout(height=500)
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("### Domain Statistics")
                    
                    total_domains = df_filtered['sender_domain'].nunique()
                    internal_emails = len(df_filtered[df_filtered['sender_domain'] == 'heyhanni.com'])
                    external_emails = len(df_filtered) - internal_emails
                    
                    st.metric("Total Unique Domains", total_domains)
                    st.metric("Internal Emails", f"{internal_emails:,} ({internal_emails/len(df_filtered)*100:.1f}%)")
                    st.metric("External Emails", f"{external_emails:,} ({external_emails/len(df_filtered)*100:.1f}%)")
            
            else:  # Communication Patterns
                st.subheader("🔄 Communication Patterns")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.markdown("### Email Activity by Hour")
                    df_filtered['hour'] = df_filtered['datetime'].dt.hour
                    hourly_counts = df_filtered['hour'].value_counts().sort_index()
                    
                    fig = go.Figure(data=[
                        go.Bar(
                            x=hourly_counts.index,
                            y=hourly_counts.values,
                            marker_color=['#764ba2' if 9 <= h <= 17 else '#667eea' for h in hourly_counts.index],
                            text=hourly_counts.values,
                            textposition='auto',
                        )
                    ])
                    fig.update_layout(
                        title="Email Distribution by Hour of Day",
                        xaxis_title="Hour (24h format)",
                        yaxis_title="Email Count",
                        xaxis=dict(tickmode='linear', tick0=0, dtick=1),
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
                
                with col2:
                    st.markdown("### Email Activity by Day of Week")
                    df_filtered['weekday'] = df_filtered['datetime'].dt.day_name()
                    weekday_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
                    weekday_counts = df_filtered['weekday'].value_counts().reindex(weekday_order, fill_value=0)
                    
                    fig = go.Figure(data=[
                        go.Bar(
                            x=weekday_counts.index,
                            y=weekday_counts.values,
                            marker_color=['#764ba2' if d not in ['Saturday', 'Sunday'] else '#667eea' for d in weekday_counts.index],
                            text=weekday_counts.values,
                            textposition='auto',
                        )
                    ])
                    fig.update_layout(
                        title="Email Distribution by Day of Week",
                        xaxis_title="Day",
                        yaxis_title="Email Count",
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
        
        else:
            st.info("No email data available for analysis. Run the backup script to index emails first.")
    
    # Tab 5: Settings
    with tab5:
        st.header("Settings & Configuration")
        
        st.subheader("Current Configuration")
        
        config_data = {
            "Dropbox Folder": DROPBOX_FOLDER,
            "Database Location": str(INDEX_DB),
            "State Directory": str(STATE_DIR),
            "Admin Email": os.getenv("GOOGLE_DELEGATED_ADMIN", "Not configured"),
            "Backup Mode": os.getenv("BACKUP_MODE", "incremental"),
            "Rate Limit": f"{os.getenv('RATE_LIMIT_DELAY', '0.1')} seconds",
            "Batch Size": os.getenv("BATCH_SIZE", "100"),
            "Index Enabled": "Yes" if os.getenv("INDEX_EMAILS", "1") == "1" else "No"
        }
        
        for key, value in config_data.items():
            col1, col2 = st.columns([1, 2])
            with col1:
                st.text(key)
            with col2:
                st.code(value)
        
        st.subheader("Quick Start Guide")
        
        st.markdown("""
        <div style='background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%); border-left: 4px solid #764ba2; padding: 1rem 1.5rem; border-radius: 10px; margin: 1rem 0;'>
        <h4>To start backing up emails:</h4>
        <ol>
        <li>Ensure your <code>.env</code> file is configured with proper tokens</li>
        <li>Run <code>python backup.py</code> in your terminal</li>
        <li>For search functionality: <code>python backup.py search</code></li>
        <li>To rebuild index: <code>python backup.py rebuild-index</code></li>
        </ol>
        </div>
        """, unsafe_allow_html=True)
        
        st.subheader("System Status")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if INDEX_DB.exists():
                st.success("✅ Database Connected")
            else:
                st.error("❌ Database Not Found")
        
        with col2:
            if STATE_DIR.exists():
                state_count = len(list(STATE_DIR.glob("*.json")))
                st.success(f"✅ {state_count} User States")
            else:
                st.warning("⚠️ No State Files")
        
        with col3:
            if os.getenv("DROPBOX_TEAM_TOKEN"):
                st.success("✅ Dropbox Configured")
            else:
                st.error("❌ Dropbox Not Configured")
        
        with st.expander("Advanced Options"):
            st.markdown("""
            ### Environment Variables
            
            You can configure these in your `.env` file:
            
            - `BACKUP_MODE`: 'full' or 'incremental'
            - `RATE_LIMIT_DELAY`: Seconds between API calls
            - `BATCH_SIZE`: Number of emails per batch
            - `MAX_MESSAGES_PER_USER`: Limit emails per user (0 = unlimited)
            - `BUSINESS_HOURS_SLOWDOWN`: Enable slower processing during work hours
            - `INDEX_EMAILS`: Enable search indexing (1 = yes, 0 = no)
            """)
            
            if st.button("🔄 Clear Cache", key="clear_cache"):
                st.cache_data.clear()
                st.success("Cache cleared successfully!")

if __name__ == "__main__":
    main()