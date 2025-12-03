import streamlit as st
import requests
import json
from datetime import datetime
import time

# --- Page Configuration ---
st.set_page_config(
    page_title="PROSPECT RESEARCH ASSISTANT",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Retro Terminal UI ---
retro_css = """
<style>
    /* Base Terminal Style */
    .stApp {
        background: #000000;
        color: #00ff00;
        font-family: 'Courier New', monospace;
        font-size: 14px;
    }
    
    /* Glitch Header Effect */
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
    }
    
    /* Scan Line Effect */
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
    
    /* Terminal Box */
    .terminal-box {
        background: rgba(0, 20, 0, 0.3);
        border: 1px solid #00ff00;
        padding: 15px;
        margin: 10px 0;
        border-radius: 0;
        font-family: 'Courier New', monospace;
    }
    
    /* Input Styling */
    .stTextInput > div > div > input {
        background: #001100;
        color: #00ff00;
        border: 1px solid #00ff00;
        border-radius: 0;
        font-family: 'Courier New', monospace;
        font-size: 14px;
    }
    
    .stTextInput > div > div > input:focus {
        outline: none;
        box-shadow: 0 0 10px #00ff00;
        background: #002200;
    }
    
    /* Button Styling */
    .stButton > button {
        background: #001100;
        color: #00ff00;
        border: 1px solid #00ff00;
        border-radius: 0;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        background: #00ff00;
        color: #000000;
        border-color: #00ff00;
        transform: translateY(-1px);
    }
    
    /* Selectbox Styling */
    .stSelectbox > div > div {
        background: #001100;
        color: #00ff00;
        border: 1px solid #00ff00;
        border-radius: 0;
    }
    
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        background: #000000;
        border-bottom: 1px solid #00ff00;
        gap: 20px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: #000000;
        color: #00ff00;
        border: 1px solid #00ff00;
        border-bottom: none;
        border-radius: 0;
        padding: 8px 16px;
        font-family: 'Courier New', monospace;
    }
    
    .stTabs [aria-selected="true"] {
        background: #00ff00;
        color: #000000;
        font-weight: bold;
    }
    
    /* Message History Items */
    .message-item {
        background: #001100;
        border: 1px solid #008800;
        padding: 10px;
        margin: 5px 0;
        font-size: 12px;
        font-family: 'Courier New', monospace;
    }
    
    .message-item.active {
        background: #003300;
        border-color: #00ff00;
        border-left: 4px solid #00ff00;
    }
    
    /* Status Indicators */
    .status-indicator {
        display: inline-block;
        width: 10px;
        height: 10px;
        margin-right: 8px;
        background: #ff0000;
    }
    
    .status-indicator.active {
        background: #00ff00;
        box-shadow: 0 0 10px #00ff00;
        animation: pulse 1s infinite;
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
    st.session_state.processing_status = "IDLE"

# --- Header Section ---
st.markdown("<h1 class='glitch-header'>PROSPECT RESEARCH ASSISTANT v2.0</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("<h3>SYSTEM CONFIGURATION</h3>", unsafe_allow_html=True)
    
    # API Configuration
    apify_api_key = st.secrets.get("APIFY")
    
    groq_api_key = st.secrets.get("GROQ")
    
    st.markdown("---")
    
    # Analysis Settings
    analysis_mode = st.selectbox(
        "ANALYSIS MODE",
        ["BASIC ANALYSIS", "DETAILED ANALYSIS", "TECHNICAL FOCUS"],
        index=0
    )
    
    message_tone = st.selectbox(
        "MESSAGE TONE",
        ["DIRECT", "PROFESSIONAL", "TECHNICAL"],
        index=1
    )
    
    st.markdown("---")
    
    # System Status
    st.markdown("<h4>SYSTEM STATUS</h4>", unsafe_allow_html=True)
    status_text = "READY" if st.session_state.processing_status == "IDLE" else st.session_state.processing_status
    status_class = "active" if st.session_state.processing_status == "IDLE" else ""
    
    st.markdown(f"""
    <div class="terminal-box">
        <span class="status-indicator {status_class}"></span>
        STATUS: {status_text}<br>
        PROFILES LOADED: {1 if st.session_state.profile_data else 0}<br>
        MESSAGES GENERATED: {len(st.session_state.generated_messages)}
    </div>
    """, unsafe_allow_html=True)

# --- Main Content Area ---
col_left, col_right = st.columns([2, 1])

with col_left:
    st.markdown("<h3>PROFILE INPUT</h3>", unsafe_allow_html=True)
    
    linkedin_url = st.text_input(
        "LINKEDIN PROFILE URL",
        placeholder="https://linkedin.com/in/username",
        label_visibility="collapsed"
    )
    
    # Process Button
    if st.button("INITIATE PROFILE ANALYSIS", use_container_width=True):
        if not linkedin_url:
            st.error("ERROR: NO PROFILE URL PROVIDED")
        elif not apify_api_key or not groq_api_key:
            st.error("ERROR: API KEYS REQUIRED")
        else:
            st.session_state.processing_status = "FETCHING_DATA"
            
            # Fetch data from Apify
            with st.spinner("CONNECTING TO APIFY API..."):
                profile_data = fetch_apify_data(linkedin_url, apify_api_key)
                
                if profile_data:
                    st.session_state.profile_data = profile_data
                    st.session_state.processing_status = "ANALYZING_DATA"
                    
                    # Generate research brief
                    with st.spinner("GENERATING RESEARCH BRIEF..."):
                        research_brief = generate_research_brief(profile_data, groq_api_key, analysis_mode)
                        st.session_state.research_brief = research_brief
                        st.session_state.processing_status = "COMPLETE"
                        st.success("ANALYSIS COMPLETE")
                else:
                    st.error("ERROR: FAILED TO RETRIEVE PROFILE DATA")
                    st.session_state.processing_status = "ERROR"

with col_right:
    st.markdown("<h3>CONTROLS</h3>", unsafe_allow_html=True)
    
    # Message Generation Controls (only show if profile loaded)
    if st.session_state.profile_data and st.session_state.research_brief:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        
        if st.button("GENERATE FIRST-LEVEL MESSAGE", use_container_width=True):
            new_message = generate_first_level_message(
                st.session_state.profile_data,
                groq_api_key,
                message_tone
            )
            
            if new_message:
                st.session_state.generated_messages.append(new_message)
                st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                st.rerun()
        
        st.markdown("</div>")
        
        # Navigation Controls
        if len(st.session_state.generated_messages) > 0:
            col_nav1, col_nav2 = st.columns(2)
            
            with col_nav1:
                if st.button("PREVIOUS MESSAGE", use_container_width=True):
                    if st.session_state.current_message_index > 0:
                        st.session_state.current_message_index -= 1
                        st.rerun()
            
            with col_nav2:
                if st.button("NEXT MESSAGE", use_container_width=True):
                    if st.session_state.current_message_index < len(st.session_state.generated_messages) - 1:
                        st.session_state.current_message_index += 1
                        st.rerun()

# --- Display Results ---
if st.session_state.profile_data and st.session_state.research_brief:
    st.markdown("---")
    
    # Create Tabs
    tab1, tab2, tab3 = st.tabs(["RESEARCH BRIEF", "MESSAGES", "PROFILE DATA"])
    
    with tab1:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown(f"**RESEARCH BRIEF GENERATED: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
        st.markdown("---")
        st.markdown(st.session_state.research_brief)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with tab2:
        if len(st.session_state.generated_messages) > 0:
            # Current Message Display
            current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
            
            st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
            st.markdown(f"**MESSAGE {st.session_state.current_message_index + 1} OF {len(st.session_state.generated_messages)}**")
            st.markdown(f"**LENGTH:** {len(current_msg)} characters")
            st.markdown("---")
            st.markdown(current_msg)
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Copy to clipboard
            st.code(current_msg, language=None)
            
            # Message History
            st.markdown("**MESSAGE HISTORY**")
            for idx, msg in enumerate(st.session_state.generated_messages):
                active_class = "active" if idx == st.session_state.current_message_index else ""
                st.markdown(f"""
                <div class="message-item {active_class}">
                    <small>MESSAGE {idx + 1} | {len(msg)} chars</small><br>
                    {msg[:80]}...
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("NO MESSAGES GENERATED YET. CLICK 'GENERATE FIRST-LEVEL MESSAGE' TO CREATE ONE.")
    
    with tab3:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown("**RAW PROFILE DATA**")
        with st.expander("VIEW JSON STRUCTURE"):
            st.json(st.session_state.profile_data)
        st.markdown("</div>", unsafe_allow_html=True)

# --- API Functions ---
def fetch_apify_data(profile_url: str, api_key: str) -> dict:
    """
    Fetch LinkedIn profile data using Apify API
    """
    try:
        # For Apify LinkedIn Profile Scraper actor
        actor_id = "apify/linkedin-profile-scraper"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Prepare the run input
        payload = {
            "startUrls": [{"url": profile_url}],
            "maxProfiles": 1,
            "proxyConfiguration": {"useApifyProxy": True}
        }
        
        # Start the actor run
        run_response = requests.post(
            f"https://api.apify.com/v2/acts/{actor_id}/runs",
            headers=headers,
            json=payload
        )
        
        if run_response.status_code == 201:
            run_data = run_response.json()
            run_id = run_data["data"]["id"]
            
            # Wait for completion (simplified polling)
            for i in range(30):  # Max 30 seconds
                time.sleep(1)
                
                status_response = requests.get(
                    f"https://api.apify.com/v2/acts/{actor_id}/runs/{run_id}",
                    headers=headers
                )
                
                if status_response.status_code == 200:
                    status_data = status_response.json()
                    
                    if status_data["data"]["status"] == "SUCCEEDED":
                        # Get dataset items
                        dataset_id = status_data["data"]["defaultDatasetId"]
                        items_response = requests.get(
                            f"https://api.apify.com/v2/datasets/{dataset_id}/items",
                            headers=headers
                        )
                        
                        if items_response.status_code == 200:
                            items = items_response.json()
                            if items and len(items) > 0:
                                return items[0]
                    
                    elif status_data["data"]["status"] in ["FAILED", "TIMED-OUT"]:
                        st.error(f"APIFY ERROR: {status_data['data']['status']}")
                        return None
            
            st.warning("APIFY TIMEOUT: USING MOCK DATA FOR DEMONSTRATION")
            return create_mock_data(profile_url)
        
        return None
        
    except Exception as e:
        st.error(f"API CONNECTION ERROR: {str(e)}")
        return create_mock_data(profile_url)

def create_mock_data(profile_url: str) -> dict:
    """
    Create mock profile data for demonstration
    """
    return {
        "basic_info": {
            "fullname": "Demo User",
            "headline": "Software Engineer | AI/ML Specialist",
            "profile_url": profile_url,
            "about": "Focused on building scalable AI solutions and machine learning pipelines.",
            "location": {"full": "San Francisco Bay Area"}
        },
        "experience": [
            {
                "title": "Senior AI Engineer",
                "company": "Tech Innovations Inc.",
                "description": "Leading AI model development and deployment.",
                "duration": "2022 - Present",
                "is_current": True
            }
        ],
        "education": [],
        "projects": [],
        "certifications": []
    }

def generate_research_brief(profile_data: dict, api_key: str, mode: str) -> str:
    """
    Generate research brief using Groq LLM
    """
    prompt = f"""
    Analyze this LinkedIn profile and create a concise research brief for sales prospecting.
    
    PROFILE DATA:
    {json.dumps(profile_data, indent=2)}
    
    ANALYSIS MODE: {mode}
    
    Create a brief with these sections:
    1. PROFILE SUMMARY (3-4 key points)
    2. CAREER TRAJECTORY AND PROGRESSION
    3. TECHNICAL COMPETENCIES AND SKILLS
    4. INFERRED BUSINESS NEEDS AND PAIN POINTS
    5. PERSONALIZATION OPPORTUNITIES
    
    Keep the analysis factual, concise, and focused on business insights.
    Avoid flattery and subjective praise.
    """
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "mixtral-8x7b-32768",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a research analyst creating factual prospect briefs. Focus on data and insights, not opinions."
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
            timeout=30
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"LLM API ERROR: {response.status_code}"
            
    except Exception as e:
        return f"LLM CONNECTION ERROR: {str(e)}"

def generate_first_level_message(profile_data: dict, api_key: str, tone: str) -> str:
    """
    Generate first-level LinkedIn message using Groq LLM
    """
    # Extract relevant data for message generation
    current_role = next(
        (exp for exp in profile_data.get('experience', []) if exp.get('is_current', False)),
        {}
    )
    
    recent_projects = profile_data.get('projects', [])[:2]
    profile_summary = profile_data.get('basic_info', {}).get('about', '')[:300]
    
    prompt = f"""
    Create a first-level LinkedIn connection request message based on this profile.
    
    PROFILE CONTEXT:
    - Current Role: {current_role.get('title', '')} at {current_role.get('company', '')}
    - Recent Work: {[p.get('name', '') for p in recent_projects]}
    - Profile Summary: {profile_summary}
    
    REQUIREMENTS:
    1. Message must be UNDER 250 characters total
    2. Focus on specific work, projects, or technical content from their profile
    3. Tone should be: {tone}
    4. ABSOLUTELY DO NOT USE these words: exploring, interested, learning, no easy feat, impressive, noteworthy, remarkable, fascinating, admiring, inspiring, no small feat, no easy task, stood out
    5. No flattery or praise - focus on factual observations
    6. Do not include explanations or meta-commentary
    
    Example format: "Noticed your work on [specific project/technology]. [Brief relevant observation]. Would connect to discuss [related topic]."
    
    Generate only the message content.
    """
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama3-70b-8192",
            "messages": [
                {
                    "role": "system",
                    "content": "You generate direct, professional LinkedIn messages without flattery or forbidden words. Focus on specific profile content."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 100
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=20
        )
        
        if response.status_code == 200:
            message = response.json()["choices"][0]["message"]["content"].strip()
            
            # Clean and validate message
            message = message.replace('"', '').replace('\n', ' ')
            if len(message) > 250:
                message = message[:247] + '...'
            
            return message
        else:
            return "Would connect based on your technical background."
            
    except Exception as e:
        return "Saw your profile. Would connect to discuss technical work."

# --- Footer Section ---
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("**SYSTEM**: Prospect Research v2.0")
with col2:
    st.markdown(f"**TIME**: {datetime.now().strftime('%H:%M:%S')}")
with col3:
    if st.session_state.profile_data:
        name = st.session_state.profile_data.get('basic_info', {}).get('fullname', 'No Profile')
        st.markdown(f"**CURRENT**: {name[:20]}")

# --- Deployment Instructions ---
with st.expander("DEPLOYMENT INSTRUCTIONS"):
    st.markdown("""
   
    """)

# --- Error Handling Display ---
if st.session_state.processing_status == "ERROR":
    st.markdown("<div class='terminal-box' style='border-color:#ff0000;'>", unsafe_allow_html=True)
    st.markdown("**SYSTEM ERROR**")
    st.markdown("Check API keys and internet connection.")
    st.markdown("</div>", unsafe_allow_html=True)
