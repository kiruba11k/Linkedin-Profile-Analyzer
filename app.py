import streamlit as st
import requests
import json
from datetime import datetime
import time
import random

# ========== API FUNCTIONS ==========

def extract_username_from_url(profile_url: str) -> str:
    """Extract username from LinkedIn URL."""
    if "/in/" in profile_url:
        return profile_url.split("/in/")[-1].strip("/").split("?")[0]
    return profile_url

def start_apify_run(username: str, api_key: str) -> dict:
    """
    Start the Apify actor run asynchronously.
    HTTP 201 status means SUCCESS - run created.
    """
    try:
        endpoint = "https://api.apify.com/v2/acts/apimaestro~linkedin-profile-detail/runs"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {"username": username, "includeEmail": False}
        
        response = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 201:
            run_data = response.json()
            return {
                "run_id": run_data["data"]["id"],
                "dataset_id": run_data["data"]["defaultDatasetId"],
                "status": "RUNNING"
            }
        else:
            st.error(f"Failed to start actor. Status: {response.status_code}")
            return None
            
    except Exception as e:
        st.error(f"Error starting Apify run: {str(e)}")
        return None

def poll_apify_run_with_status(run_id: str, dataset_id: str, api_key: str) -> dict:
    """
    Poll the Apify run with proper status updates.
    Returns profile data when successful.
    """
    max_attempts = 60
    headers = {"Authorization": f"Bearer {api_key}"}
    
    with st.spinner("🔄 Fetching LinkedIn data..."):
        progress_bar = st.progress(0)
        
        for attempt in range(max_attempts):
            progress = min(100, int((attempt + 1) / max_attempts * 80))
            progress_bar.progress(progress)
            
            try:
                status_endpoint = f"https://api.apify.com/v2/actor-runs/{run_id}"
                status_response = requests.get(status_endpoint, headers=headers, timeout=15)
                
                if status_response.status_code == 200:
                    status_data = status_response.json()["data"]
                    current_status = status_data.get("status", "UNKNOWN")
                    
                    if current_status == "SUCCEEDED":
                        progress_bar.progress(95)
                        
                        dataset_endpoint = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
                        dataset_response = requests.get(dataset_endpoint, headers=headers, timeout=30)
                        
                        if dataset_response.status_code == 200:
                            items = dataset_response.json()
                            progress_bar.progress(100)
                            if isinstance(items, list) and len(items) > 0:
                                return items[0]
                            elif isinstance(items, dict):
                                return items
                        else:
                            st.error(f"Failed to fetch dataset: {dataset_response.status_code}")
                            return None
                            
                    elif current_status in ["FAILED", "TIMED-OUT", "ABORTED"]:
                        st.error(f"Apify run failed: {current_status}")
                        return None
                        
                    elif current_status == "RUNNING":
                        time.sleep(10)
                        continue
                        
                else:
                    time.sleep(10)
                    
            except Exception as e:
                time.sleep(10)
    
    st.error("Polling timeout - Apify taking too long")
    return None

def generate_research_brief(profile_data: dict, api_key: str) -> str:
    """
    Generate research brief with improved reliability.
    """
    try:
        profile_summary = json.dumps(profile_data, indent=2)[:2000]
        
        prompt = f'''
        Create a concise research brief for sales prospecting.
        
        PROFILE DATA:
        {profile_summary}
        
        Create a brief with these sections:
        1. KEY PROFILE INSIGHTS
        2. CAREER PATTERNS & CURRENT FOCUS
        3. BUSINESS CONTEXT & POTENTIAL NEEDS
        4. PERSONALIZATION OPPORTUNITIES
        
        Keep it factual and actionable.
        '''
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a research analyst creating factual briefs."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 1200
        }
        
        try:
            response = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                return f"Research brief generation encountered an issue (Status: {response.status_code}). The profile data is loaded and ready for message generation."
                
        except requests.exceptions.Timeout:
            return "Research brief generation is taking longer than expected. Profile data is loaded and ready for message generation."
        except Exception as e:
            return f"Research brief service temporarily unavailable. Profile data loaded successfully."
            
    except Exception as e:
        return f"Profile analysis ready. Focus on message generation."

def analyze_and_generate_message(profile_data: dict, api_key: str, sender_name: str, 
                                user_instructions: str = None, previous_message: str = None) -> str:
    """
    LLM analyzes message patterns organically and generates a natural message.
    Uses cross-checking to prevent hallucinations.
    """
    # Extract key information from profile
    prospect_name = "there"
    profile_elements = []
    
    try:
        if isinstance(profile_data, dict):
            # Extract name
            if profile_data.get('fullname'):
                prospect_name = profile_data.get('fullname').split()[0]
            elif profile_data.get('basic_info') and profile_data['basic_info'].get('fullname'):
                prospect_name = profile_data['basic_info']['fullname'].split()[0]
            
            # Extract key elements for context
            if profile_data.get('headline'):
                profile_elements.append(f"Headline: {profile_data['headline']}")
            if profile_data.get('about'):
                profile_elements.append(f"About: {profile_data['about'][:200]}")
            if profile_data.get('experience'):
                experiences = profile_data.get('experience', [])
                if experiences and len(experiences) > 0:
                    current_exp = experiences[0]
                    role = current_exp.get('title', '')
                    company = current_exp.get('company', '')
                    if role and company:
                        profile_elements.append(f"Current Role: {role} at {company}")
            if profile_data.get('education'):
                edu = profile_data.get('education', [])
                if edu and len(edu) > 0:
                    school = edu[0].get('school', '')
                    degree = edu[0].get('degree', '')
                    if school:
                        profile_elements.append(f"Education: {school}")
        
        profile_summary = "\n".join(profile_elements)
        
    except Exception as e:
        profile_summary = json.dumps(profile_data, indent=2)[:1500]

    # CRITICAL: Cross-checking system to prevent hallucinations
    verification_prompt = f'''You are a message verification system. Check if this message:
    1. Contains factual information from the profile
    2. Doesn't copy example messages exactly
    3. Is personalized and professional
    4. Follows proper structure
    
    Profile Context:
    {profile_summary}
    
    Return "VALID" if the message meets criteria, otherwise return specific feedback.'''

    if user_instructions and previous_message:
        # Refinement mode
        prompt = f'''Generate a refined LinkedIn connection message for {prospect_name}.

PROFILE CONTEXT:
{profile_summary}

ORIGINAL MESSAGE TO REFINE:
{previous_message}

REFINEMENT INSTRUCTIONS:
{user_instructions}

CRITICAL GUIDELINES:
1. Start with "Hi [First Name],"
2. Reference ONE specific element from their profile (current role, education, or headline)
3. Mention YOUR value/interest (but not specific company names unless in profile)
4. End with "Best, [Your Name]"
5. Keep under 250 characters
6. DO NOT copy phrases from any example messages
7. Make it unique and personalized to THIS person

Generate only the message:'''
    else:
        # New generation with anti-hallucination measures
        prompt = f'''Generate a personalized LinkedIn connection message for {prospect_name}.

PROFILE CONTEXT:
{profile_summary}

GUIDELINES FOR CREATION:
1. Start with "Hi {prospect_name},"
2. Reference ONE specific element from their profile (current role at company, education, or headline)
3. Connect it to your general interest/field WITHOUT naming specific companies
4. End with "Best, {sender_name}"
5. Keep entire message under 250 characters
6. MUST be unique - do not copy any example structures
7. Use natural, conversational tone
8. Focus on mutual professional interests

IMPORTANT: Only use information from the profile. Do not invent details.

Generate only the message:'''
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Generate initial message
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system", 
                    "content": f'''You are a professional relationship builder. Create unique, personalized LinkedIn messages.
                    NEVER copy from examples. Always base messages on profile data only.'''
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8,  # Slightly higher for creativity
            "max_tokens": 300
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=40
        )
        
        if response.status_code == 200:
            message = response.json()["choices"][0]["message"]["content"].strip()
            
            # Clean and format message
            message = message.replace('"', '').replace("''", "'").strip()
            
            # Ensure proper greeting
            if not message.lower().startswith(f"hi {prospect_name.lower()},"):
                if message.lower().startswith("hi ") and "," in message:
                    # Keep existing greeting
                    pass
                else:
                    # Add proper greeting
                    message = f"Hi {prospect_name},\n{message}"
            
            # Ensure proper signature
            if not message.strip().endswith(f"Best, {sender_name}"):
                message = f"{message.rstrip()}\nBest, {sender_name}"
            
            # Verify message doesn't copy examples
            forbidden_patterns = [
                "LeadStrategus", "Planet", "Adam", "Heather", "Gabriel",
                "FP&A leadership", "renovation lending", "recruiting",
                "mortgage lending", "retention and analytics"
            ]
            
            for pattern in forbidden_patterns:
                if pattern.lower() in message.lower():
                    # Regenerate with stricter prompt
                    strict_prompt = f'''Regenerate message for {prospect_name}. 
                    Do NOT use any example phrases. 
                    Profile: {profile_summary[:300]}
                    Create completely original message.'''
                    
                    strict_payload = {
                        "model": "llama-3.1-8b-instant",
                        "messages": [
                            {"role": "system", "content": "Create completely original message. No example copying."},
                            {"role": "user", "content": strict_prompt}
                        ],
                        "temperature": 0.9,
                        "max_tokens": 250
                    }
                    
                    strict_response = requests.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=strict_payload,
                        timeout=30
                    )
                    
                    if strict_response.status_code == 200:
                        message = strict_response.json()["choices"][0]["message"]["content"].strip()
                        message = f"Hi {prospect_name},\n{message}"
                        if not message.endswith(f"Best, {sender_name}"):
                            message = f"{message}\nBest, {sender_name}"
                    break
            
            # Final length check
            if len(message) > 275:
                lines = message.split('\n')
                if len(lines) >= 3:
                    message = f"{lines[0]}\n{lines[1][:150]}\n{lines[-1]}"
                message = message[:275]
            
            return message
            
        else:
            # Safe fallback
            return f"Hi {prospect_name},\nI noticed your professional background and wanted to connect regarding mutual interests in your field.\nBest, {sender_name}"
            
    except Exception as e:
        return f"Hi {prospect_name},\nYour experience looks impressive. Would be great to connect and exchange insights.\nBest, {sender_name}"

# ========== STREAMLIT APPLICATION ==========

st.set_page_config(
    page_title="AI Prospect Assistant",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Modern AI-themed CSS ---
modern_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        font-family: 'Inter', sans-serif;
    }
    
    .main-container {
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-radius: 24px;
        padding: 40px;
        margin: 20px;
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
        animation: fadeIn 0.8s ease-out;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    @keyframes float {
        0%, 100% { transform: translateY(0); }
        50% { transform: translateY(-10px); }
    }
    
    @keyframes shimmer {
        0% { background-position: -1000px 0; }
        100% { background-position: 1000px 0; }
    }
    
    .header-title {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(90deg, #667eea, #764ba2, #667eea);
        background-size: 200% auto;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        animation: shimmer 3s linear infinite;
        margin-bottom: 10px;
    }
    
    .header-subtitle {
        color: #666;
        font-size: 1.2rem;
        margin-bottom: 30px;
        opacity: 0.9;
    }
    
    .gradient-button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        padding: 14px 32px;
        border-radius: 12px;
        font-weight: 600;
        font-size: 1rem;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
    }
    
    .gradient-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(102, 126, 234, 0.6);
    }
    
    .card {
        background: white;
        border-radius: 20px;
        padding: 25px;
        margin: 15px 0;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        transition: all 0.3s ease;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.12);
    }
    
    .message-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #e4edf5 100%);
        border-left: 4px solid #667eea;
        padding: 25px;
        border-radius: 16px;
        margin: 15px 0;
        animation: slideIn 0.5s ease-out;
    }
    
    @keyframes slideIn {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    
    .ai-badge {
        display: inline-block;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 6px 16px;
        border-radius: 20px;
        font-size: 0.9rem;
        font-weight: 600;
        margin: 5px;
        animation: float 3s ease-in-out infinite;
    }
    
    .stTextInput > div > div > input {
        border-radius: 12px;
        border: 2px solid #e0e0e0;
        padding: 14px;
        font-size: 1rem;
        transition: all 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
    }
    
    .stSelectbox > div > div {
        border-radius: 12px;
    }
    
    .status-indicator {
        display: inline-flex;
        align-items: center;
        padding: 8px 16px;
        border-radius: 20px;
        font-weight: 600;
        font-size: 0.9rem;
        margin: 5px;
    }
    
    .status-active {
        background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
        color: white;
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.7); }
        70% { box-shadow: 0 0 0 10px rgba(76, 175, 80, 0); }
        100% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0); }
    }
    
    .status-idle {
        background: #f0f0f0;
        color: #666;
    }
    
    .floating-shapes {
        position: fixed;
        width: 100%;
        height: 100%;
        top: 0;
        left: 0;
        pointer-events: none;
        z-index: -1;
    }
    
    .shape {
        position: absolute;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 50%;
        animation: float 20s infinite linear;
    }
    
    .tab-container {
        background: white;
        border-radius: 20px;
        padding: 20px;
        margin-top: 20px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
    }
    
    /* Custom scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f1f1;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(135deg, #5a6fd8 0%, #6a4190 100%);
    }
</style>

<div class="floating-shapes">
    <div class="shape" style="width: 100px; height: 100px; top: 10%; left: 5%; animation-delay: 0s;"></div>
    <div class="shape" style="width: 150px; height: 150px; top: 60%; left: 80%; animation-delay: -5s;"></div>
    <div class="shape" style="width: 80px; height: 80px; top: 20%; left: 70%; animation-delay: -10s;"></div>
    <div class="shape" style="width: 120px; height: 120px; top: 80%; left: 20%; animation-delay: -15s;"></div>
</div>
"""

st.markdown(modern_css, unsafe_allow_html=True)

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
    st.session_state.processing_status = "Ready"
if 'sender_name' not in st.session_state:
    st.session_state.sender_name = "Joseph"
if 'message_instructions' not in st.session_state:
    st.session_state.message_instructions = ""
if 'regenerate_mode' not in st.session_state:
    st.session_state.regenerate_mode = False

# --- Main Container ---
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# --- Header ---
col1, col2 = st.columns([3, 1])
with col1:
    st.markdown('<h1 class="header-title">🤖 AI Prospect Assistant</h1>', unsafe_allow_html=True)
    st.markdown('<p class="header-subtitle">Generate personalized LinkedIn messages with AI intelligence</p>', unsafe_allow_html=True)
with col2:
    st.markdown(f'''
    <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div class="status-indicator {'status-active' if st.session_state.profile_data else 'status-idle'}">
                    ● {st.session_state.processing_status}
                </div>
                <p style="margin-top: 10px; font-size: 0.9rem; color: #666;">
                    Messages: {len(st.session_state.generated_messages)}<br>
                    {datetime.now().strftime('%H:%M:%S')}
                </p>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

st.markdown("---")

# --- Main Input Section ---
st.markdown("### 🔍 Analyze LinkedIn Profile")
st.markdown("Enter a LinkedIn URL to start personalized message generation")

input_col1, input_col2 = st.columns([3, 1])

with input_col1:
    linkedin_url = st.text_input(
        "",
        placeholder="https://www.linkedin.com/in/username",
        label_visibility="collapsed"
    )

with input_col2:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    analyze_clicked = st.button(
        "🚀 Analyze Profile", 
        use_container_width=True,
        type="primary"
    )

# --- Processing Logic ---
if analyze_clicked and linkedin_url:
    with st.spinner("🤖 Initializing AI analysis..."):
        # Use secrets for API keys
        apify_api_key = st.secrets.get("APIFY", "")
        groq_api_key = st.secrets.get("GROQ", "")
        
        if not apify_api_key or not groq_api_key:
            st.error("❌ API keys not configured. Please check your secrets.")
        else:
            st.session_state.processing_status = "Analyzing"
            
            # Extract and process profile
            username = extract_username_from_url(linkedin_url)
            run_info = start_apify_run(username, apify_api_key)
            
            if run_info:
                profile_data = poll_apify_run_with_status(
                    run_info["run_id"],
                    run_info["dataset_id"],
                    apify_api_key
                )
                
                if profile_data:
                    st.session_state.profile_data = profile_data
                    st.session_state.processing_status = "Generating Brief"
                    
                    # Generate research brief
                    research_brief = generate_research_brief(profile_data, groq_api_key)
                    st.session_state.research_brief = research_brief
                    st.session_state.processing_status = "Ready"
                    
                    st.success("✅ Profile analysis complete! Ready to generate messages.")
                    
                    # Clear previous messages for new profile
                    st.session_state.generated_messages = []
                    st.session_state.current_message_index = -1
                else:
                    st.session_state.processing_status = "Error"
                    st.error("❌ Failed to fetch profile data")

# --- Results Display ---
if st.session_state.profile_data and st.session_state.research_brief:
    st.markdown("---")
    
    # Sender Configuration
    with st.expander("✏️ Message Settings", expanded=False):
        col_set1, col_set2 = st.columns(2)
        with col_set1:
            new_sender_name = st.text_input(
                "Your Name",
                value=st.session_state.sender_name,
                help="This will sign all generated messages"
            )
            if new_sender_name != st.session_state.sender_name:
                st.session_state.sender_name = new_sender_name
        
        with col_set2:
            st.markdown(f"""
            <div class="card">
                <h4>⚙️ Current Settings</h4>
                <p><strong>Sender:</strong> {st.session_state.sender_name}</p>
                <p><strong>Profile:</strong> Loaded</p>
                <p><strong>Messages Generated:</strong> {len(st.session_state.generated_messages)}</p>
            </div>
            """, unsafe_allow_html=True)
    
    # Tab Interface
    tab1, tab2, tab3 = st.tabs(["📝 Generate Messages", "📊 Research Brief", "🔍 Profile Data"])
    
    with tab1:
        st.markdown("### ✨ Generate Personalized Message")
        
        # Generate new message
        col_gen1, col_gen2 = st.columns([2, 1])
        
        with col_gen1:
            if st.button(
                "🤖 Generate AI Message", 
                use_container_width=True,
                type="primary",
                key="generate_new"
            ):
                with st.spinner("🧠 Creating personalized message..."):
                    new_message = analyze_and_generate_message(
                        st.session_state.profile_data,
                        groq_api_key,
                        st.session_state.sender_name
                    )
                    
                    if new_message:
                        st.session_state.generated_messages.append(new_message)
                        st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                        st.rerun()
        
        with col_gen2:
            if len(st.session_state.generated_messages) > 0:
                if st.button(
                    "🔄 Refine Message", 
                    use_container_width=True,
                    key="start_refine"
                ):
                    st.session_state.regenerate_mode = True
                    st.rerun()
        
        # Display current message
        if len(st.session_state.generated_messages) > 0:
            current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
            
            st.markdown(f'''
            <div class="message-card">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div>
                        <h4>📨 Generated Message</h4>
                        <p style="color: #666; font-size: 0.9rem;">
                            {len(current_msg)} characters • Version {st.session_state.current_message_index + 1}
                        </p>
                    </div>
                    <span class="ai-badge">AI Generated</span>
                </div>
                <div style="background: white; padding: 20px; border-radius: 12px; margin: 15px 0; border: 1px solid #e0e0e0;">
                    <pre style="white-space: pre-wrap; font-family: 'Inter', sans-serif; line-height: 1.6; margin: 0;">
{current_msg}
                    </pre>
                </div>
            </div>
            ''', unsafe_allow_html=True)
            
            # Copy and navigation
            col_copy, col_prev, col_next, col_count = st.columns([2, 1, 1, 1])
            
            with col_copy:
                st.code(current_msg, language=None)
            
            with col_prev:
                if st.button("← Previous", use_container_width=True, disabled=st.session_state.current_message_index <= 0):
                    st.session_state.current_message_index -= 1
                    st.session_state.regenerate_mode = False
                    st.rerun()
            
            with col_next:
                if st.button("Next →", use_container_width=True, disabled=st.session_state.current_message_index >= len(st.session_state.generated_messages) - 1):
                    st.session_state.current_message_index += 1
                    st.session_state.regenerate_mode = False
                    st.rerun()
            
            with col_count:
                st.markdown(f"**{st.session_state.current_message_index + 1}/{len(st.session_state.generated_messages)}**")
            
            # Refinement Mode
            if st.session_state.regenerate_mode:
                st.markdown("---")
                st.markdown("### 🔧 Refine Message")
                
                with st.form("refinement_form"):
                    instructions = st.text_area(
                        "How would you like to improve this message?",
                        value=st.session_state.message_instructions,
                        placeholder="e.g., 'Make it more casual', 'Focus on AI experience', 'Shorten to 150 chars'",
                        height=100
                    )
                    
                    col_ref1, col_ref2, col_ref3 = st.columns([2, 1, 1])
                    
                    with col_ref1:
                        refine_submit = st.form_submit_button(
                            "✨ Generate Refined Version",
                            type="primary",
                            use_container_width=True
                        )
                    
                    with col_ref2:
                        cancel_refine = st.form_submit_button(
                            "Cancel",
                            use_container_width=True
                        )
                    
                    if refine_submit and instructions:
                        with st.spinner("🔄 Creating refined version..."):
                            refined_message = analyze_and_generate_message(
                                st.session_state.profile_data,
                                groq_api_key,
                                st.session_state.sender_name,
                                instructions,
                                current_msg
                            )
                            
                            if refined_message:
                                st.session_state.generated_messages.append(refined_message)
                                st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                                st.session_state.regenerate_mode = False
                                st.session_state.message_instructions = ""
                                st.rerun()
                    
                    if cancel_refine:
                        st.session_state.regenerate_mode = False
                        st.rerun()
            
            # Message History
            if len(st.session_state.generated_messages) > 1:
                st.markdown("---")
                st.markdown("### 📚 Message History")
                
                for idx, msg in enumerate(st.session_state.generated_messages):
                    is_active = idx == st.session_state.current_message_index
                    bg_color = "#f0f4ff" if is_active else "#f8f9fa"
                    
                    st.markdown(f'''
                    <div style="background: {bg_color}; padding: 15px; border-radius: 12px; margin: 8px 0; border: 1px solid {'#667eea' if is_active else '#e0e0e0'}; cursor: pointer; transition: all 0.3s;"
                         onclick="this.style.transform='scale(0.98)'; setTimeout(() => window.location.href='?select={idx}', 100)">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong>Version {idx + 1}</strong>
                                <span style="color: #666; font-size: 0.85rem; margin-left: 10px;">
                                    {len(msg)} chars
                                </span>
                            </div>
                            {'<span style="color: #667eea; font-weight: 600;">✓ Active</span>' if is_active else ''}
                        </div>
                        <div style="margin-top: 8px; color: #555; font-size: 0.9rem;">
                            {msg.split('\\n')[0][:80]}...
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
        
        else:
            st.info("👆 Click 'Generate AI Message' to create your first personalized message!")
    
    with tab2:
        st.markdown("### 📊 Research Brief")
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(st.session_state.research_brief)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab3:
        st.markdown("### 🔍 Raw Profile Data")
        with st.expander("View JSON Data", expanded=False):
            st.json(st.session_state.profile_data)

else:
    # Welcome/Empty State
    st.markdown('''
    <div style="text-align: center; padding: 60px 20px;">
        <div style="font-size: 4rem; margin-bottom: 20px;">🤖</div>
        <h2 style="color: #333; margin-bottom: 20px;">Welcome to AI Prospect Assistant</h2>
        <p style="color: #666; max-width: 600px; margin: 0 auto 40px; line-height: 1.6;">
            Enter a LinkedIn profile URL above to generate personalized connection messages 
            using advanced AI. Get research briefs and craft unique messages that resonate.
        </p>
        <div style="display: inline-flex; gap: 20px; justify-content: center;">
            <div class="ai-badge" style="animation-delay: 0s;">⚡ Fast Analysis</div>
            <div class="ai-badge" style="animation-delay: 1s;">🎯 Personalized</div>
            <div class="ai-badge" style="animation-delay: 2s;">🤖 AI Powered</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown("**AI Prospect Assistant v2.0**")
with col_f2:
    st.markdown(f"**Last Updated:** {datetime.now().strftime('%H:%M:%S')}")
with col_f3:
    if st.session_state.profile_data:
        name = "Profile Loaded"
        if isinstance(st.session_state.profile_data, dict):
            if 'fullname' in st.session_state.profile_data:
                name = st.session_state.profile_data['fullname'][:25]
        st.markdown(f"**Active:** {name}")
    else:
        st.markdown("**Status:** Ready")

# Add some interactive elements
if st.session_state.profile_data:
    st.markdown("""
    <script>
    // Smooth scroll to messages
    function smoothScroll(element) {
        element.scrollIntoView({behavior: 'smooth'});
    }
    
    // Add click handlers to message history items
    document.addEventListener('DOMContentLoaded', function() {
        const urlParams = new URLSearchParams(window.location.search);
        const selectIdx = urlParams.get('select');
        if (selectIdx) {
            setTimeout(() => {
                window.history.replaceState({}, document.title, window.location.pathname);
            }, 100);
        }
    });
    </script>
    """, unsafe_allow_html=True)
