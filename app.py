import streamlit as st
import requests
import json
from datetime import datetime
import os
from typing import Dict, List, Optional
import time

# --- Page Configuration with Retro Theme ---
st.set_page_config(
    page_title="PROSPECT RESEARCH // AUTO",
    page_icon="",
    layout="wide"
)

# --- Custom CSS for Retro UI ---
retro_css = """
<style>
    .stApp {
        background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
        color: #00ff9d;
        font-family: 'Courier New', monospace;
    }
    
    /* Terminal Glitch Effect */
    @keyframes terminal-flicker {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.95; }
    }
    
    .terminal-box {
        background: rgba(10, 15, 20, 0.9);
        border: 1px solid #00ff9d;
        padding: 1.5rem;
        border-radius: 0;
        margin: 1rem 0;
        animation: terminal-flicker 5s infinite;
    }
    
    .scan-line {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 1px;
        background: linear-gradient(90deg, transparent, #00ff9d, transparent);
        animation: scan 8s linear infinite;
        pointer-events: none;
        z-index: 999;
    }
    
    @keyframes scan {
        0% { transform: translateY(0); }
        100% { transform: translateY(100vh); }
    }
    
    /* Button Styles */
    .stButton > button {
        background: #000;
        color: #00ff9d;
        border: 1px solid #00ff9d;
        border-radius: 0;
        font-family: 'Courier New', monospace;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        background: #00ff9d;
        color: #000;
        transform: translateY(-2px);
    }
    
    .msg-button {
        background: #002200 !important;
        border-color: #00cc00 !important;
    }
    
    /* Input Styling */
    .stTextInput > div > div > input {
        background: #000;
        color: #00ff9d;
        border: 1px solid #00ff9d;
        border-radius: 0;
    }
    
    /* Tab Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 2rem;
        background-color: #000;
    }
    
    .stTabs [data-baseweb="tab"] {
        background-color: #000;
        color: #00ff9d;
        border: 1px solid #00ff9d;
        border-radius: 0;
        padding: 0.5rem 1rem;
    }
    
    /* Message History Box */
    .msg-history {
        background: #001100;
        border: 1px solid #008800;
        padding: 1rem;
        margin: 0.5rem 0;
        font-size: 0.9rem;
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
if 'messages' not in st.session_state:
    st.session_state.messages = []
if 'current_msg_index' not in st.session_state:
    st.session_state.current_msg_index = -1
if 'apify_task_id' not in st.session_state:
    st.session_state.apify_task_id = None

# --- Header ---
st.markdown("<h1 style='color:#00ff9d; text-align:center;'>PROSPECT RESEARCH ASSISTANT</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align:center; color:#888;'>Automated LinkedIn Analysis Pipeline</p>", unsafe_allow_html=True)

# --- Sidebar for Configuration ---
with st.sidebar:
    st.markdown("### CONFIGURATION")
    
    # API Keys
    apify_token = st.text_input(
        "APIFY API TOKEN",
        type="password",
        help="Get from https://console.apify.com/account#/integrations"
    )
    
    groq_api_key = st.text_input(
        "GROQ API KEY",
        type="password",
        help="Get from https://console.groq.com"
    )
    
    st.markdown("---")
    
    # Analysis Settings
    analysis_mode = st.selectbox(
        "ANALYSIS DEPTH",
        ["Quick Scan", "Standard", "Deep Analysis"],
        index=1
    )
    
    message_style = st.selectbox(
        "MESSAGE TONE",
        ["Direct & Professional", "Technical Focus", "Project Reference"]
    )
    
    st.markdown("---")
    st.markdown("### STATUS")
    
    if st.session_state.profile_data:
        st.success(" Profile Loaded")
    else:
        st.info("Ready for URL")

# --- Main Input Area ---
st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
col1, col2 = st.columns([3, 1])

with col1:
    linkedin_url = st.text_input(
        "ENTER LINKEDIN PROFILE URL",
        placeholder="https://linkedin.com/in/username",
        label_visibility="collapsed"
    )

with col2:
    st.markdown("<br>", unsafe_allow_html=True)
    analyze_clicked = st.button(" FETCH & ANALYZE", use_container_width=True)

st.markdown("</div>", unsafe_allow_html=True)

# --- APIFY API Integration Functions ---
def fetch_linkedin_data_apify(profile_url: str, apify_token: str) -> Optional[Dict]:
    """
    Fetch LinkedIn data using Apify API
    Using Apify's LinkedIn Profile Scraper actor
    """
    try:
        # Apify API endpoint for LinkedIn Profile Scraper
        APIFY_ACTOR_ID = "apify/linkedin-profile-scraper"
        APIFY_BASE_URL = "https://api.apify.com/v2"
        
        headers = {
            "Authorization": f"Bearer {apify_token}",
            "Content-Type": "application/json"
        }
        
        # Prepare the run input
        run_input = {
            "startUrls": [{"url": profile_url}],
            "maxProfiles": 1,
            "extendOutputFunction": """async ({ data, item, page, request, customData, Apify }) => {
                return item;
            }""",
            "proxyConfiguration": {"useApifyProxy": True}
        }
        
        # Start the actor run
        run_response = requests.post(
            f"{APIFY_BASE_URL}/acts/{APIFY_ACTOR_ID}/runs",
            headers=headers,
            json={"startUrls": [profile_url]}
        )
        
        if run_response.status_code == 201:
            run_data = run_response.json()
            task_id = run_data["data"]["id"]
            st.session_state.apify_task_id = task_id
            
            # Poll for completion (simplified - in production use webhooks)
            with st.spinner("Fetching profile data from Apify..."):
                for _ in range(30):  # Wait up to 30 seconds
                    time.sleep(2)
                    status_response = requests.get(
                        f"{APIFY_BASE_URL}/acts/{APIFY_ACTOR_ID}/runs/{task_id}",
                        headers=headers
                    )
                    
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        if status_data["data"]["status"] == "SUCCEEDED":
                            # Get the dataset items
                            dataset_id = status_data["data"]["defaultDatasetId"]
                            items_response = requests.get(
                                f"{APIFY_BASE_URL}/datasets/{dataset_id}/items",
                                headers=headers
                            )
                            
                            if items_response.status_code == 200:
                                items = items_response.json()
                                if items:
                                    return items[0]  # Return first profile
                            break
                        elif status_data["data"]["status"] in ["FAILED", "TIMED-OUT"]:
                            st.error(f"Apify run failed: {status_data['data']['status']}")
                            return None
                
                st.warning("Apify run taking longer than expected. Using mock data for demo.")
                return create_mock_data(profile_url)
        
        return None
        
    except Exception as e:
        st.error(f"Apify API Error: {str(e)}")
        # Fallback to mock data for demo
        return create_mock_data(profile_url)

def create_mock_data(profile_url: str) -> Dict:
    """Create mock data for demo/testing"""
    return {
        "basic_info": {
            "fullname": "Demo User",
            "headline": "Software Engineer | AI/ML",
            "profile_url": profile_url,
            "about": "Passionate about building scalable AI solutions.",
            "location": {"full": "San Francisco, CA"}
        },
        "experience": [
            {
                "title": "Senior AI Engineer",
                "company": "Tech Corp",
                "description": "Leading AI initiatives.",
                "duration": "2022 - Present",
                "is_current": True
            }
        ],
        "education": [],
        "projects": [],
        "certifications": []
    }

# --- GROQ LLM Functions ---
def generate_research_brief(profile_data: Dict, groq_api_key: str) -> str:
    """Generate research brief using Groq LLM"""
    prompt = f"""
    Analyze this LinkedIn profile and create a concise research brief for sales prospecting.
    
    PROFILE DATA:
    {json.dumps(profile_data, indent=2)}
    
    Create a brief with these sections:
    1. PROFILE SUMMARY (3-4 bullet points)
    2. CAREER TRAJECTORY (key moves and progression)
    3. TECHNICAL FOCUS AREAS (based on experience and skills)
    4. POTENTIAL PAIN POINTS (inferred from role/industry)
    5. PERSONALIZATION INSIGHTS (specific hooks from profile content)
    
    Keep it factual, concise, and actionable.
    """
    
    try:
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "mixtral-8x7b-32768",
            "messages": [
                {
                    "role": "system", 
                    "content": "You are a data-driven research assistant. Provide factual analysis without flattery."
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
            return "Error generating brief with LLM."
            
    except Exception as e:
        return f"LLM Error: {str(e)}"

def generate_first_level_message(profile_data: Dict, groq_api_key: str, style: str) -> str:
    """Generate first-level message based on profile content"""
    
    # Extract recent experience and projects
    current_exp = next((exp for exp in profile_data.get('experience', []) if exp.get('is_current', False)), {})
    recent_projects = profile_data.get('projects', [])[:2]
    
    prompt = f"""
    Create a first-level LinkedIn connection request message based on this profile.
    
    PROFILE INFO:
    - Name: {profile_data.get('basic_info', {}).get('fullname', 'User')}
    - Current Role: {current_exp.get('title', '')} at {current_exp.get('company', '')}
    - Recent Projects: {[p.get('name', '') for p in recent_projects]}
    - Profile Summary: {profile_data.get('basic_info', {}).get('about', '')[:200]}
    
    REQUIREMENTS:
    1. Message must be UNDER 250 characters
    2. Focus on their recent work, projects, or specific technical content
    3. Be direct and professional
    4. DO NOT use these words: exploring, interested, learning, no easy feat, impressive, noteworthy, remarkable, fascinating, admiring, inspiring, no small feat, no easy task, stood out
    5. DO NOT use flattery
    6. Tone: {style}
    
    Example structure: "Saw your work on [specific project/technology]. [Brief, relevant observation]. Would appreciate connecting."
    
    Generate only the message content, no explanations.
    """
    
    try:
        headers = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama3-70b-8192",  # Using Llama for more consistent output
            "messages": [
                {
                    "role": "system", 
                    "content": "You generate concise, professional LinkedIn messages without flattery or forbidden words."
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
            timeout=30
        )
        
        if response.status_code == 200:
            message = response.json()["choices"][0]["message"]["content"].strip()
            # Clean up and ensure length
            message = message.replace('"', '')
            if len(message) > 250:
                message = message[:247] + "..."
            return message
        else:
            return "Hi, came across your profile. Would appreciate connecting."
            
    except Exception as e:
        return "Would like to connect based on your technical background."

# --- Main Processing Logic ---
if analyze_clicked and linkedin_url:
    if not apify_token or not groq_api_key:
        st.error("Please enter both Apify and Groq API keys in the sidebar")
    else:
        with st.spinner("Fetching LinkedIn data via Apify API..."):
            # Fetch data from Apify
            profile_data = fetch_linkedin_data_apify(linkedin_url, apify_token)
            
            if profile_data:
                st.session_state.profile_data = profile_data
                
                # Generate research brief
                with st.spinner("Generating research brief..."):
                    research_brief = generate_research_brief(profile_data, groq_api_key)
                    st.session_state.research_brief = research_brief
                
                st.success(" Analysis Complete!")

# --- Display Results if Data Exists ---
if st.session_state.profile_data and st.session_state.research_brief:
    profile = st.session_state.profile_data
    brief = st.session_state.research_brief
    
    # Create tabs for different outputs
    tab1, tab2, tab3 = st.tabs(["RESEARCH BRIEF", "FIRST-LEVEL MESSAGES", "PROFILE DATA"])
    
    with tab1:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown(f"### RESEARCH BRIEF: {profile.get('basic_info', {}).get('fullname', 'User')}")
        st.markdown("---")
        st.markdown(brief)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with tab2:
        col_msg1, col_msg2 = st.columns([3, 1])
        
        with col_msg2:
            st.markdown("### MESSAGE CONTROLS")
            
            # Button to generate new message
            if st.button(" GENERATE NEW MESSAGE", key="gen_new_msg", use_container_width=True):
                new_message = generate_first_level_message(
                    profile, 
                    groq_api_key, 
                    message_style
                )
                st.session_state.messages.append(new_message)
                st.session_state.current_msg_index = len(st.session_state.messages) - 1
                st.rerun()
            
            # Navigation buttons
            if len(st.session_state.messages) > 0:
                st.markdown("---")
                col_nav1, col_nav2 = st.columns(2)
                
                with col_nav1:
                    if st.button("◀ PREVIOUS", use_container_width=True):
                        if st.session_state.current_msg_index > 0:
                            st.session_state.current_msg_index -= 1
                            st.rerun()
                
                with col_nav2:
                    if st.button("NEXT ▶", use_container_width=True):
                        if st.session_state.current_msg_index < len(st.session_state.messages) - 1:
                            st.session_state.current_msg_index += 1
                            st.rerun()
        
        with col_msg1:
            st.markdown("### GENERATED MESSAGES")
            st.markdown(f"*Total generated: {len(st.session_state.messages)}*")
            
            if len(st.session_state.messages) > 0:
                # Display current message
                current_msg = st.session_state.messages[st.session_state.current_msg_index]
                
                st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
                st.markdown(f"**Message #{st.session_state.current_msg_index + 1}**")
                st.markdown(f"*{len(current_msg)} characters*")
                st.markdown("---")
                st.markdown(current_msg)
                st.markdown("</div>", unsafe_allow_html=True)
                
                # Copy button
                st.code(current_msg, language=None)
                
                # Message history
                if len(st.session_state.messages) > 1:
                    st.markdown("### MESSAGE HISTORY")
                    for idx, msg in enumerate(st.session_state.messages):
                        bg_color = "#003300" if idx == st.session_state.current_msg_index else "#001100"
                        st.markdown(
                            f"""<div class='msg-history' style='background: {bg_color};'>
                            <small>Message #{idx + 1} ({len(msg)} chars)</small><br>
                            {msg[:100]}...
                            </div>""", 
                            unsafe_allow_html=True
                        )
            else:
                st.info("Click 'GENERATE NEW MESSAGE' to create your first message")
    
    with tab3:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown("### RAW PROFILE DATA")
        with st.expander("View JSON Data"):
            st.json(profile)
        st.markdown("</div>", unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown("**System**: Prospect Research v2.0")
with col_f2:
    if st.session_state.profile_data:
        name = st.session_state.profile_data.get('basic_info', {}).get('fullname', 'None')
        st.markdown(f"**Profile**: {name}")
    else:
        st.markdown("**Profile**: None loaded")
with col_f3:
    st.markdown(f"**Time**: {datetime.now().strftime('%H:%M:%S')}")

# --- Instructions ---
with st.expander(""):
    st.markdown("""

    """)
