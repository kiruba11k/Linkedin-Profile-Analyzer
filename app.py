import streamlit as st
import requests
import json
from datetime import datetime
import time

# ========== API FUNCTIONS (DEFINED FIRST) ==========

def extract_username_from_url(profile_url: str) -> str:
    """Extract username from LinkedIn URL."""
    if "/in/" in profile_url:
        return profile_url.split("/in/")[-1].strip("/").split("?")[0]
    return profile_url

def start_apify_run(username: str, api_key: str) -> dict:
    """
    Step 1: Start the Apify actor run asynchronously.
    Returns the run data containing runId and defaultDatasetId.
    """
    try:
        endpoint = "https://api.apify.com/v2/acts/apimaestro~linkedin-profile-detail/runs"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "username": username,
            "includeEmail": False
        }
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        
        # 201 is SUCCESS for async operations
        if response.status_code == 201:
            run_data = response.json()
            if "data" in run_data:
                return {
                    "run_id": run_data["data"]["id"],
                    "dataset_id": run_data["data"]["defaultDatasetId"],
                    "status": "STARTED"
                }
        else:
            st.error(f"Failed to start actor. Status: {response.status_code}")
            return None
            
    except Exception as e:
        st.error(f"Error starting Apify run: {str(e)}")
        return None

def check_run_status(run_id: str, api_key: str) -> dict:
    """Check the status of an Apify run."""
    try:
        endpoint = f"https://api.apify.com/v2/actor-runs/{run_id}"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        response = requests.get(endpoint, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()["data"]
        return None
        
    except Exception:
        return None

def fetch_apify_results(dataset_id: str, api_key: str) -> dict:
    """Fetch results from Apify dataset."""
    try:
        endpoint = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
        headers = {"Authorization": f"Bearer {api_key}"}
        
        response = requests.get(endpoint, headers=headers, timeout=30)
        
        if response.status_code == 200:
            items = response.json()
            if isinstance(items, list) and len(items) > 0:
                return items[0]
            elif isinstance(items, dict):
                return items
        return None
        
    except Exception:
        return None

def poll_apify_run(run_id: str, dataset_id: str, api_key: str) -> dict:
    """
    Poll the Apify run until completion and return results.
    """
    max_attempts = 36  # 6 minutes max (10 seconds per check)
    
    for attempt in range(max_attempts):
        # Update progress
        progress = min(100, int((attempt + 1) / max_attempts * 100))
        st.session_state.processing_progress = progress
        
        # Check run status
        status_data = check_run_status(run_id, api_key)
        
        if not status_data:
            time.sleep(10)
            continue
            
        status = status_data.get("status", "")
        
        if status == "SUCCEEDED":
            # Fetch the results
            results = fetch_apify_results(dataset_id, api_key)
            if results:
                return results
                
        elif status in ["FAILED", "TIMED-OUT", "ABORTED"]:
            st.error(f"Actor run failed with status: {status}")
            return None
            
        # Still running, wait and try again
        time.sleep(10)
    
    st.error("Polling timeout - actor taking too long")
    return None

def generate_research_brief(profile_data: dict, api_key: str, mode: str) -> str:
    """Generate research brief using Groq LLM."""
    try:
        prompt = f"""
        Analyze this LinkedIn profile data and create a professional research brief for sales prospecting.
        
        PROFILE DATA:
        {json.dumps(profile_data, indent=2)}
        
        ANALYSIS MODE: {mode}
        
        Create a structured brief with these sections:
        1. PROFILE SUMMARY (key facts only)
        2. CAREER TRAJECTORY & CURRENT ROLE
        3. TECHNICAL SKILLS & COMPETENCIES
        4. BUSINESS CONTEXT & INFERRED NEEDS
        5. PERSONALIZATION OPPORTUNITIES
        
        Keep it factual, concise, and focused on business insights.
        Avoid all flattery words and subjective praise.
        """
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "mixtral-8x7b-32768",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a data-driven research analyst. Provide factual analysis without flattery."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1500
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=45
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return "Error generating research brief. Please check your Groq API key."
            
    except Exception as e:
        return f"LLM connection error: {str(e)}"

def generate_first_level_message(profile_data: dict, api_key: str, style: str) -> str:
    """Generate first-level LinkedIn connection message."""
    try:
        prompt = f"""
        Create a first-level LinkedIn connection request message based on this profile.
        
        PROFILE DATA:
        {json.dumps(profile_data, indent=2)}
        
        REQUIREMENTS:
        1. Message must be UNDER 250 characters
        2. Focus on specific work, projects, or technologies from the profile
        3. Tone: {style}
        4. ABSOLUTELY FORBIDDEN: exploring, interested, learning, no easy feat, impressive, noteworthy, remarkable, fascinating, admiring, inspiring, no small feat, no easy task, stood out
        5. NO FLATTERY - only factual observations
        6. Reference something specific from the profile
        
        Example structure: "Saw your work on [specific thing]. [Factual observation]. Would connect to discuss [related topic]."
        
        Generate only the message content.
        """
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama3-70b-8192",
            "messages": [
                {
                    "role": "system",
                    "content": "Create direct, professional LinkedIn messages without forbidden words. Reference specific profile content."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 150
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            message = response.json()["choices"][0]["message"]["content"].strip()
            message = message.replace('"', '').replace('\n', ' ')
            if len(message) > 250:
                message = message[:247] + '...'
            return message
        else:
            return "Would connect based on your technical background."
            
    except Exception:
        return "Saw your profile. Would connect to discuss professional work."

# ========== STREAMLIT APPLICATION ==========

st.set_page_config(
    page_title="PROSPECT RESEARCH ASSISTANT",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Retro Terminal UI ---
retro_css = """
<style>
    .stApp {
        background: #000000;
        color: #00ff00;
        font-family: 'Courier New', monospace;
        font-size: 14px;
    }
    
    @keyframes glitch {
        0% { text-shadow: 2px 2px 0 #ff00ff, -2px -2px 0 #00ffff; }
        20% { text-shadow: -2px 2px 0 #ff00ff, 2px -2px 0 #00ffff; }
        40% { text-shadow: 2px -2px 0 #ff00ff, -2px 2px 0 #00ffff; }
        60% { text-shadow: -2px -2px 0 #ff00ff, 2px 2px 0 #00ffff; }
        80% { text-shadow: 2px 2px 0 #ff00ff, -2px -2px 0 #00ffff; }
        100% { text-shadow: -2px 2px 0 #ff00ff, 2px -2px 0 #00ffff; }
    }
    
    .glitch-header {
        color: #00ff00;
        animation: glitch 1s infinite;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 2px;
        border-bottom: 2px solid #00ff00;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }
    
    .scan-line {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 2px;
        background: linear-gradient(to right, transparent, #00ff00, transparent);
        animation: scan 8s linear infinite;
        pointer-events: none;
        z-index: 9999;
    }
    
    @keyframes scan {
        0% { transform: translateY(0); }
        100% { transform: translateY(100vh); }
    }
    
    .terminal-box {
        background: rgba(0, 20, 0, 0.3);
        border: 1px solid #00ff00;
        padding: 20px;
        margin: 15px 0;
        border-radius: 0;
        font-family: 'Courier New', monospace;
    }
    
    .stTextInput > div > div > input {
        background: #001100;
        color: #00ff00;
        border: 1px solid #00ff00;
        border-radius: 0;
        font-family: 'Courier New', monospace;
        font-size: 14px;
        padding: 10px;
    }
    
    .stButton > button {
        background: #001100;
        color: #00ff00;
        border: 1px solid #00ff00;
        border-radius: 0;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 12px 24px;
        transition: all 0.3s;
        width: 100%;
    }
    
    .stButton > button:hover {
        background: #00ff00;
        color: #000000;
        border-color: #00ff00;
        transform: translateY(-2px);
    }
    
    .progress-container {
        background: #001100;
        border: 1px solid #00ff00;
        padding: 10px;
        margin: 10px 0;
    }
    
    .progress-bar {
        height: 20px;
        background: #003300;
        border: 1px solid #008800;
        position: relative;
        overflow: hidden;
    }
    
    .progress-fill {
        height: 100%;
        background: #00ff00;
        width: 0%;
        transition: width 0.5s;
    }
    
    .message-history-item {
        background: #001100;
        border: 1px solid #008800;
        padding: 12px;
        margin: 8px 0;
        font-size: 12px;
        cursor: pointer;
        transition: all 0.3s;
    }
    
    .message-history-item:hover {
        border-color: #00ff00;
        background: #002200;
    }
    
    .message-history-item.active {
        border-left: 4px solid #00ff00;
        background: #003300;
    }
    
    .status-led {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 8px;
        background: #ff0000;
        box-shadow: 0 0 10px #ff0000;
    }
    
    .status-led.active {
        background: #00ff00;
        box-shadow: 0 0 10px #00ff00;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
</style>
<div class="scan-line"></div>
"""

st.markdown(retro_css, unsafe_allow_html=True)

# --- Initialize Session State ---
if 'profile_data' not in st.session_state:
    st.session_state.profile_data = None
if 'research_brief' not in st.session_state:
    st.session_state.research_brief = None
if 'generated_messages' not in st.session_state:
    st.session_state.generated_messages = []
if 'current_message_index' not in st.session_state:
    st.session_state.current_message_index = -1
if 'processing_status' not in st.session_state:
    st.session_state.processing_status = "READY"
if 'processing_progress' not in st.session_state:
    st.session_state.processing_progress = 0
if 'apify_run_info' not in st.session_state:
    st.session_state.apify_run_info = None

# --- Header ---
st.markdown("<h1 class='glitch-header'>PROSPECT RESEARCH ASSISTANT</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("### SYSTEM CONFIGURATION")
    
    apify_api_key = st.secrets.get("APIFY")
    
    groq_api_key = st.secrets.get("GROQ")
    
    st.markdown("---")
    
    analysis_mode = st.selectbox(
        "ANALYSIS MODE",
        ["QUICK SCAN", "DETAILED ANALYSIS", "TECHNICAL FOCUS"],
        index=1
    )
    
    message_style = st.selectbox(
        "MESSAGE STYLE",
        ["DIRECT", "PROFESSIONAL", "TECHNICAL"],
        index=1
    )
    
    st.markdown("---")
    
    # Status Display
    st.markdown("### SYSTEM STATUS")
    status_text = st.session_state.processing_status
    status_class = "active" if status_text == "READY" else ""
    
    st.markdown(f"""
    <div class="terminal-box">
        <span class="status-led {status_class}"></span>
        <strong>STATUS: {status_text}</strong><br>
        Progress: {st.session_state.processing_progress}%<br>
        Messages: {len(st.session_state.generated_messages)}<br>
        Last Update: {datetime.now().strftime('%H:%M:%S')}
    </div>
    """, unsafe_allow_html=True)

# --- Main Input Area ---
st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
col1, col2 = st.columns([3, 1])

with col1:
    linkedin_url = st.text_input(
        "LINKEDIN PROFILE URL",
        placeholder="https://linkedin.com/in/username",
        label_visibility="collapsed"
    )

with col2:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    analyze_clicked = st.button("INITIATE ANALYSIS", use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

# --- Processing Logic ---
if analyze_clicked and linkedin_url:
    if not apify_api_key or not groq_api_key:
        st.error("ERROR: BOTH API KEYS ARE REQUIRED")
    else:
        # Step 1: Start Apify run
        st.session_state.processing_status = "STARTING APIFY RUN"
        st.session_state.processing_progress = 10
        
        username = extract_username_from_url(linkedin_url)
        run_info = start_apify_run(username, apify_api_key)
        
        if run_info:
            st.session_state.apify_run_info = run_info
            st.session_state.processing_status = "POLLING APIFY RESULTS"
            st.session_state.processing_progress = 30
            
            # Create progress container
            progress_container = st.container()
            with progress_container:
                st.markdown("### PROCESSING STATUS")
                st.markdown("<div class='progress-container'>", unsafe_allow_html=True)
                st.markdown(f"<div class='progress-bar'><div class='progress-fill' style='width: {st.session_state.processing_progress}%'></div></div>", unsafe_allow_html=True)
                st.markdown(f"Fetching data for: {username}")
                st.markdown("</div>", unsafe_allow_html=True)
            
            # Step 2: Poll for results
            profile_data = poll_apify_run(
                run_info["run_id"],
                run_info["dataset_id"],
                apify_api_key
            )
            
            if profile_data:
                st.session_state.profile_data = profile_data
                st.session_state.processing_status = "GENERATING RESEARCH BRIEF"
                st.session_state.processing_progress = 70
                
                # Update progress
                with progress_container:
                    st.markdown(f"<div class='progress-bar'><div class='progress-fill' style='width: {st.session_state.processing_progress}%'></div></div>", unsafe_allow_html=True)
                    st.markdown("Data received. Generating analysis...")
                
                # Step 3: Generate research brief
                research_brief = generate_research_brief(
                    profile_data,
                    groq_api_key,
                    analysis_mode
                )
                
                st.session_state.research_brief = research_brief
                st.session_state.processing_status = "COMPLETE"
                st.session_state.processing_progress = 100
                
                # Clear progress container and show success
                progress_container.empty()
                st.success("ANALYSIS COMPLETE - PROFILE DATA READY")
            else:
                st.session_state.processing_status = "ERROR"
                st.error("FAILED TO RETRIEVE PROFILE DATA")
        else:
            st.session_state.processing_status = "ERROR"
            st.error("FAILED TO START APIFY RUN")

# --- Display Results ---
if st.session_state.profile_data and st.session_state.research_brief:
    st.markdown("---")
    
    # Create Tabs
    tab1, tab2, tab3 = st.tabs(["RESEARCH BRIEF", "MESSAGES", "RAW DATA"])
    
    with tab1:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown(f"**RESEARCH BRIEF - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
        st.markdown("---")
        st.markdown(st.session_state.research_brief)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with tab2:
        # Message Generation Controls
        col_msg1, col_msg2 = st.columns([3, 1])
        
        with col_msg2:
            st.markdown("### MESSAGE CONTROLS")
            
            if st.button("GENERATE NEW MESSAGE", use_container_width=True, key="gen_msg_btn"):
                new_message = generate_first_level_message(
                    st.session_state.profile_data,
                    groq_api_key,
                    message_style
                )
                if new_message:
                    st.session_state.generated_messages.append(new_message)
                    st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                    st.rerun()
            
            if len(st.session_state.generated_messages) > 0:
                st.markdown("---")
                col_nav1, col_nav2 = st.columns(2)
                
                with col_nav1:
                    if st.button("◄ PREVIOUS", use_container_width=True):
                        if st.session_state.current_message_index > 0:
                            st.session_state.current_message_index -= 1
                            st.rerun()
                
                with col_nav2:
                    if st.button("NEXT ►", use_container_width=True):
                        if st.session_state.current_message_index < len(st.session_state.generated_messages) - 1:
                            st.session_state.current_message_index += 1
                            st.rerun()
        
        with col_msg1:
            st.markdown("### GENERATED MESSAGES")
            
            if len(st.session_state.generated_messages) > 0:
                current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
                
                st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
                st.markdown(f"**MESSAGE {st.session_state.current_message_index + 1} OF {len(st.session_state.generated_messages)}**")
                st.markdown(f"*{len(current_msg)} characters*")
                st.markdown("---")
                st.markdown(current_msg)
                st.markdown("</div>", unsafe_allow_html=True)
                
                # Copy button
                st.code(current_msg, language=None)
                
                # Message History
                if len(st.session_state.generated_messages) > 1:
                    st.markdown("### MESSAGE HISTORY")
                    for idx, msg in enumerate(st.session_state.generated_messages):
                        is_active = idx == st.session_state.current_message_index
                        active_class = "active" if is_active else ""
                        st.markdown(f"""
                        <div class="message-history-item {active_class}">
                            <small>MESSAGE #{idx + 1} | {len(msg)} chars</small><br>
                            {msg[:100]}...
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("CLICK 'GENERATE NEW MESSAGE' TO CREATE YOUR FIRST MESSAGE")
    
    with tab3:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown("### RAW PROFILE DATA")
        with st.expander("VIEW COMPLETE JSON DATA"):
            st.json(st.session_state.profile_data)
        st.markdown("</div>", unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown("**SYSTEM**: Prospect Research v3.0")
with col_f2:
    st.markdown(f"**TIME**: {datetime.now().strftime('%H:%M:%S')}")
with col_f3:
    if st.session_state.profile_data:
        # Try to get name from different possible fields
        name = "Profile Loaded"
        if isinstance(st.session_state.profile_data, dict):
            if 'fullname' in st.session_state.profile_data:
                name = st.session_state.profile_data['fullname']
            elif 'name' in st.session_state.profile_data:
                name = st.session_state.profile_data['name']
        st.markdown(f"**CURRENT**: {name[:20]}")
    else:
        st.markdown("**CURRENT**: No Profile")

# --- Deployment Instructions ---
with st.expander("DEPLOYMENT INFORMATION"):
    st.markdown("""

    """)

# --- Error Display ---
if st.session_state.processing_status == "ERROR":
    st.markdown("<div class='terminal-box' style='border-color:#ff0000;'>", unsafe_allow_html=True)
    st.markdown("**SYSTEM ERROR DETECTED**")
    st.markdown("1. Check API keys are valid")
    st.markdown("2. Ensure LinkedIn URL is correct")
    st.markdown("3. Verify Apify account has credits")
    st.markdown("4. Try a different LinkedIn profile")
    st.markdown("</div>", unsafe_allow_html=True)
