import streamlit as st
import pandas as pd
from datetime import datetime
import os

# Page configuration
st.set_page_config(
    page_title="Hanni Email Backup System",
    page_icon="📧",
    layout="wide"
)

st.title("📧 Hanni Email Backup System")
st.markdown("### Secure Gmail to Dropbox Backup Platform")

# Display status
st.success("✅ System Deployed Successfully!")
st.info("🚀 The backup system is ready. Run `python backup.py` locally to start backing up emails.")

# Basic metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Status", "Ready", "✅")
with col2:
    st.metric("Version", "1.0", "📦")
with col3:
    st.metric("Environment", "Cloud", "☁️")

# Tabs
tab1, tab2, tab3 = st.tabs(["📊 Overview", "📚 Documentation", "⚙️ Configuration"])

with tab1:
    st.header("System Overview")
    st.markdown("""
    Welcome to the Hanni Email Backup System! This dashboard monitors your Gmail to Dropbox backups.
    
    **Current Configuration:**
    - 📁 Backup Location: `/Hanni Email Backups/`
    - 📧 Domain: `heyhanni.com`
    - 🔄 Mode: Incremental Backup
    - ⏰ Schedule: Daily at 2:00 AM
    """)
    
    # Sample data display
    st.subheader("📈 Sample Statistics")
    sample_data = pd.DataFrame({
        'Metric': ['Total Users', 'Emails Backed Up', 'Storage Used', 'Success Rate'],
        'Value': ['36', '0', '0 MB', '100%'],
        'Status': ['Ready', 'Waiting', 'Ready', 'Optimal']
    })
    st.dataframe(sample_data, use_container_width=True, hide_index=True)

with tab2:
    st.header("📚 How to Use")
    st.markdown("""
    ### Running a Backup
    
    1. **Local Setup Required**: The actual backup process runs locally for security
    2. **Run Command**: `python backup.py`
    3. **Monitor Progress**: Check this dashboard for statistics
    
    ### Search Emails
    ```bash
    python backup.py search
    ```
    
    ### Schedule Automation
    
    **Windows Task Scheduler:**
    - Open Task Scheduler
    - Create Basic Task
    - Set daily trigger at 2 AM
    - Action: `python C:\\EmailBackup\\backup.py`
    
    **Linux/Mac Cron:**
    ```bash
    0 2 * * * /usr/bin/python3 /path/to/backup.py
    ```
    """)

with tab3:
    st.header("⚙️ Configuration Status")
    
    # Check for environment variables
    config_items = {
        "Admin Email": os.getenv("GOOGLE_DELEGATED_ADMIN", "Not configured"),
        "Dropbox Folder": os.getenv("DROPBOX_TEAM_FOLDER", "/Hanni Email Backups"),
        "Backup Mode": os.getenv("BACKUP_MODE", "incremental"),
        "Python Version": "3.9+",
        "Dashboard Version": "1.0"
    }
    
    for key, value in config_items.items():
        if value == "Not configured":
            st.error(f"{key}: {value}")
        else:
            st.success(f"{key}: {value}")

# Footer
st.divider()
st.markdown("""
<div style='text-align: center; color: #666; padding: 20px;'>
    <p>Hanni Email Backup System v1.0 | Built with 💜 by Hanni</p>
    <p>Dashboard Status: Ready | Backup Status: Run locally with backup.py</p>
</div>
""", unsafe_allow_html=True)