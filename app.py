import streamlit as st
import requests
import json
from datetime import datetime
import time

# ========== API FUNCTIONS ==========
apify_api_key = st.secrets.get("APIFY", "")
groq_api_key = st.secrets.get("GROQ", "")

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
    
    with st.spinner(""):
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

def analyze_and_generate_message(profile_data: dict, api_key: str, sender_info: dict, 
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

    # Build sender context for the AI
    sender_context = ""
    if sender_info.get('company'):
        sender_context += f"I work at {sender_info['company']}. "
    if sender_info.get('role'):
        sender_context += f"My role is {sender_info['role']}. "
    if sender_info.get('expertise'):
        sender_context += f"I focus on {sender_info['expertise']}. "

    if user_instructions and previous_message:
        # Refinement mode
        prompt = f'''Generate a refined LinkedIn connection message for {prospect_name}.

PROFILE CONTEXT:
{profile_summary}

SENDER CONTEXT:
{sender_context}

ORIGINAL MESSAGE TO REFINE:
{previous_message}

REFINEMENT INSTRUCTIONS:
{user_instructions}

CRITICAL GUIDELINES:
1. Start with "Hi [First Name],"
2. Reference ONE specific element from their profile (current role, education, or headline)
3. Mention YOUR value/interest based on sender context
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

YOUR INFORMATION (SENDER):
{sender_context}

GUIDELINES FOR CREATION:
1. Start with "Hi {prospect_name},"
2. Reference ONE specific element from their profile (current role at company, education, or headline)
3. Connect it to your background/field mentioned above
4. End with "Best, {sender_info['name']}"
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
            "temperature": 0.8,
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
                    pass
                else:
                    message = f"Hi {prospect_name},\n{message}"
            
            # Ensure proper signature
            if not message.strip().endswith(f"Best, {sender_info['name']}"):
                message = f"{message.rstrip()}\nBest, {sender_info['name']}"
            
            # Verify message doesn't copy examples
            forbidden_patterns = [
                "LeadStrategus", "Planet", "Adam", "Heather", "Gabriel",
                "FP&A leadership", "renovation lending", "recruiting",
                "mortgage lending", "retention and analytics"
            ]
            
            for pattern in forbidden_patterns:
                if pattern.lower() in message.lower():
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
                        if not message.endswith(f"Best, {sender_info['name']}"):
                            message = f"{message}\nBest, {sender_info['name']}"
                    break
            
            # Final length check
            if len(message) > 275:
                lines = message.split('\n')
                if len(lines) >= 3:
                    message = f"{lines[0]}\n{lines[1][:150]}\n{lines[-1]}"
                message = message[:275]
            
            return message
            
        else:
            return f"Hi {prospect_name},\nI noticed your professional background and wanted to connect regarding mutual interests in your field.\nBest, {sender_info['name']}"
            
    except Exception as e:
        return f"Hi {prospect_name},\nYour experience looks impressive. Would be great to connect and exchange insights.\nBest, {sender_info['name']}"

# ========== STREAMLIT APPLICATION ==========

st.set_page_config(
    page_title="Linzy | AI Prospect Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Modern 3D Color Theory CSS with Enhanced Input Effects ---
modern_3d_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0a192f 0%, #1a1a2e 50%, #16213e 100%);
        font-family: 'Space Grotesk', sans-serif;
        min-height: 100vh;
    }
    
    /* 3D Perspective Container */
    .perspective-container {
        perspective: 1000px;
        transform-style: preserve-3d;
    }
    
    /* Main 3D Card */
    .main-3d-card {
        background: linear-gradient(145deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
        backdrop-filter: blur(20px);
        border-radius: 32px;
        padding: 50px;
        margin: 30px;
        border: 1px solid rgba(0, 180, 216, 0.1);
        box-shadow: 
            0 50px 100px rgba(0, 180, 216, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.1),
            0 0 100px rgba(0, 180, 216, 0.05);
        transform: rotateY(-2deg) rotateX(1deg);
        animation: float3d 6s ease-in-out infinite;
        position: relative;
        overflow: hidden;
    }
    
    @keyframes float3d {
        0%, 100% { transform: rotateY(-2deg) rotateX(1deg) translateY(0); }
        50% { transform: rotateY(-2deg) rotateX(1deg) translateY(-10px); }
    }
    
    .main-3d-card::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(0, 180, 216, 0.1), transparent);
        transition: 0.5s;
    }
    
    .main-3d-card:hover::before {
        left: 100%;
    }
    
    /* Neural Network Background */
    .neural-network {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: -1;
        opacity: 0.3;
    }
    
    /* Gradient Text Effects */
    .gradient-text-primary {
        background: linear-gradient(135deg, #00b4d8 0%, #00ffd0 50%, #0077b6 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        background-size: 200% auto;
        animation: textShimmer 3s ease-in-out infinite alternate;
    }
    
    @keyframes textShimmer {
        0% { background-position: 0% 50%; }
        100% { background-position: 100% 50%; }
    }
    
    /* Enhanced 3D Input Fields with Animations */
    .enhanced-input-3d {
        background: linear-gradient(145deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.01));
        border: 2px solid rgba(0, 180, 216, 0.15);
        border-radius: 16px;
        padding: 20px 24px;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1rem;
        color: #e6f7ff;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        backdrop-filter: blur(15px);
        transform-style: preserve-3d;
        position: relative;
        box-shadow: 
            inset 0 2px 4px rgba(0, 0, 0, 0.1),
            0 8px 32px rgba(0, 180, 216, 0.1);
    }
    
    .enhanced-input-3d:focus {
        background: linear-gradient(145deg, rgba(0, 180, 216, 0.05), rgba(0, 255, 208, 0.03));
        border-color: #00b4d8;
        box-shadow: 
            0 0 0 4px rgba(0, 180, 216, 0.15),
            inset 0 2px 8px rgba(0, 180, 216, 0.1),
            0 12px 40px rgba(0, 180, 216, 0.2);
        transform: translateY(-3px) scale(1.02);
        outline: none;
    }
    
    .enhanced-input-3d::placeholder {
        color: rgba(136, 146, 176, 0.7);
        font-weight: 400;
    }
    
    /* Input glow animation on focus */
    @keyframes inputGlow {
        0%, 100% { box-shadow: 0 0 0 4px rgba(0, 180, 216, 0.15); }
        50% { box-shadow: 0 0 0 6px rgba(0, 180, 216, 0.25); }
    }
    
    .enhanced-input-3d:focus {
        animation: inputGlow 2s ease-in-out infinite;
    }
    
    /* 3D Cards for Configuration */
    .config-card-3d {
        background: linear-gradient(145deg, rgba(255, 255, 255, 0.03), rgba(255, 255, 255, 0.01));
        border-radius: 20px;
        padding: 25px;
        margin: 15px 0;
        border: 1px solid rgba(0, 180, 216, 0.1);
        transform-style: preserve-3d;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        backdrop-filter: blur(15px);
        box-shadow: 
            0 20px 60px rgba(0, 0, 0, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 0.05);
    }
    
    .config-card-3d:hover {
        transform: translateY(-5px) rotateX(2deg);
        border-color: rgba(0, 180, 216, 0.3);
        box-shadow: 
            0 30px 80px rgba(0, 180, 216, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
    
    /* Status Indicators */
    .status-orb {
        display: inline-block;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        margin-right: 12px;
        background: #ff6b6b;
        box-shadow: 0 0 20px #ff6b6b;
        animation: pulse 2s infinite;
    }
    
    .status-orb.active {
        background: #00ffd0;
        box-shadow: 0 0 20px #00ffd0;
    }
    
    @keyframes pulse {
        0%, 100% { 
            opacity: 1;
            box-shadow: 0 0 20px currentColor;
        }
        50% { 
            opacity: 0.7;
            box-shadow: 0 0 40px currentColor;
        }
    }
    
    /* Message Display */
    .message-display-3d {
        background: linear-gradient(135deg, rgba(0, 180, 216, 0.05), rgba(0, 255, 208, 0.05));
        border-left: 4px solid #00b4d8;
        padding: 30px;
        border-radius: 20px;
        margin: 20px 0;
        font-family: 'Inter', sans-serif;
        line-height: 1.8;
        color: #e6f7ff;
        animation: slideIn3d 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        transform-style: preserve-3d;
        transform: rotateX(0.5deg);
    }
    
    @keyframes slideIn3d {
        from {
            opacity: 0;
            transform: rotateX(10deg) translateY(20px);
        }
        to {
            opacity: 1;
            transform: rotateX(0.5deg) translateY(0);
        }
    }
    
    /* Save Button Animation */
    .save-button {
        background: linear-gradient(135deg, #00b4d8 0%, #0077b6 100%);
        color: white;
        border: none;
        padding: 14px 28px;
        border-radius: 14px;
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 600;
        font-size: 0.95rem;
        cursor: pointer;
        transform-style: preserve-3d;
        transition: all 0.3s ease;
        box-shadow: 
            0 8px 25px rgba(0, 180, 216, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.2);
        position: relative;
        overflow: hidden;
    }
    
    .save-button:hover {
        transform: translateY(-2px) scale(1.03);
        box-shadow: 
            0 12px 35px rgba(0, 180, 216, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .save-button:active {
        transform: translateY(0);
        box-shadow: 
            0 5px 20px rgba(0, 180, 216, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
    
    /* Success Animation */
    @keyframes successPulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.05); }
        100% { transform: scale(1); }
    }
    
    .success-animation {
        animation: successPulse 0.5s ease-in-out;
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 10px;
    }
    
    ::-webkit-scrollbar-track {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: linear-gradient(135deg, #00b4d8, #0077b6);
        border-radius: 10px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: linear-gradient(135deg, #00ffd0, #00b4d8);
    }
</style>

<!-- Font Awesome Icons -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
"""

st.markdown(modern_3d_css, unsafe_allow_html=True)

# --- Initialize Session State with Sender Info ---
if 'profile_data' not in st.session_state:
    st.session_state.profile_data = None
if 'research_brief' not in st.session_state:
    st.session_state.research_brief = None
if 'generated_messages' not in st.session_state:
    st.session_state.generated_messages = []
if 'current_message_index' not in st.session_state:
    st.session_state.current_message_index = -1
if 'processing_status' not in st.session_state:
    st.session_state.processing_status = "System Ready"
if 'sender_info' not in st.session_state:
    st.session_state.sender_info = {
        'name': '',
        'company': '',
        'role': '',
        'expertise': '',
        'configured': False
    }
if 'message_instructions' not in st.session_state:
    st.session_state.message_instructions = ""
if 'regenerate_mode' not in st.session_state:
    st.session_state.regenerate_mode = False
if 'show_success_animation' not in st.session_state:
    st.session_state.show_success_animation = False

# --- Main 3D Container ---
st.markdown('<div class="perspective-container">', unsafe_allow_html=True)
st.markdown('<div class="main-3d-card">', unsafe_allow_html=True)

# --- Header Section ---
col1, col2 = st.columns([4, 1])
with col1:
    st.markdown('<h1 class="gradient-text-primary" style="font-size: 3.5rem; margin-bottom: 10px;">LINZY</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color: #8892b0; font-size: 1.2rem; margin-bottom: 40px;">Advanced AI-Powered Prospect Intelligence Platform</p>', unsafe_allow_html=True)
with col2:
    st.markdown(f'''
    <div class="config-card-3d" style="text-align: center; padding: 20px;">
        <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
            <span class="status-orb {'active' if st.session_state.profile_data else ''}"></span>
            <span style="color: #e6f7ff; font-weight: 600;">{st.session_state.processing_status}</span>
        </div>
        <div style="color: #8892b0; font-size: 0.9rem;">
            <div><i class="fas fa-user" style="margin-right: 8px;"></i> Sender: {st.session_state.sender_info['name'] or 'Not Set'}</div>
            <div><i class="fas fa-message" style="margin-right: 8px;"></i> Messages: {len(st.session_state.generated_messages)}</div>
            <div><i class="fas fa-clock" style="margin-right: 8px;"></i> {datetime.now().strftime('%H:%M:%S')}</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

# --- SENDER CONFIGURATION SECTION ---
st.markdown("---")
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-user-cog" style="margin-right: 12px;"></i>Sender Configuration</h3>', unsafe_allow_html=True)
st.markdown('<p style="color: #8892b0; margin-bottom: 25px;">Configure your sender information for personalized message generation</p>', unsafe_allow_html=True)

# Sender Configuration Form
with st.form("sender_config_form"):
    config_col1, config_col2 = st.columns(2)
    
    with config_col1:
        sender_name = st.text_input(
            "Your Full Name *",
            value=st.session_state.sender_info.get('name', ''),
            placeholder="Enter your name",
            key="sender_name_input"
        )
        
        sender_company = st.text_input(
            "Your Company",
            value=st.session_state.sender_info.get('company', ''),
            placeholder="Company name",
            key="sender_company_input"
        )
    
    with config_col2:
        sender_role = st.text_input(
            "Your Role",
            value=st.session_state.sender_info.get('role', ''),
            placeholder="e.g., Sales Director, Product Manager",
            key="sender_role_input"
        )
        
        sender_expertise = st.text_input(
            "Your Expertise/Industry Focus",
            value=st.session_state.sender_info.get('expertise', ''),
            placeholder="e.g., SaaS, AI, Financial Services",
            key="sender_expertise_input"
        )
    
    # Submit button
    col_submit, col_clear = st.columns([2, 1])
    
    with col_submit:
        config_submitted = st.form_submit_button(
            "💾 Save Sender Configuration",
            use_container_width=True
        )
    
    with col_clear:
        if st.form_submit_button(
            "🗑️ Clear Configuration",
            use_container_width=True,
            type="secondary"
        ):
            st.session_state.sender_info = {
                'name': '',
                'company': '',
                'role': '',
                'expertise': '',
                'configured': False
            }
            st.session_state.show_success_animation = False
            st.rerun()

# Handle configuration submission
if config_submitted:
    if sender_name.strip():
        st.session_state.sender_info = {
            'name': sender_name.strip(),
            'company': sender_company.strip(),
            'role': sender_role.strip(),
            'expertise': sender_expertise.strip(),
            'configured': True
        }
        st.session_state.show_success_animation = True
        st.success("✅ Sender configuration saved successfully!")
        
        # Add animation effect
        st.markdown("""
        <script>
        setTimeout(() => {
            const elements = document.querySelectorAll('.config-card-3d');
            elements.forEach(el => {
                el.classList.add('success-animation');
                setTimeout(() => el.classList.remove('success-animation'), 500);
            });
        }, 100);
        </script>
        """, unsafe_allow_html=True)
    else:
        st.error("❌ Please enter at least your name to save configuration.")

# Display current configuration
if st.session_state.sender_info['configured']:
    st.markdown(f'''
    <div class="config-card-3d" style="margin-top: 20px;">
        <h4 style="color: #e6f7ff; margin-bottom: 15px; display: flex; align-items: center;">
            <i class="fas fa-check-circle" style="color: #00ffd0; margin-right: 10px;"></i>
            Current Configuration
        </h4>
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
            <div>
                <div style="color: #8892b0; font-size: 0.85rem; margin-bottom: 5px;">Name</div>
                <div style="color: #e6f7ff; font-weight: 500;">{st.session_state.sender_info['name']}</div>
            </div>
            <div>
                <div style="color: #8892b0; font-size: 0.85rem; margin-bottom: 5px;">Company</div>
                <div style="color: #e6f7ff; font-weight: 500;">{st.session_state.sender_info['company'] or 'Not specified'}</div>
            </div>
            <div>
                <div style="color: #8892b0; font-size: 0.85rem; margin-bottom: 5px;">Role</div>
                <div style="color: #e6f7ff; font-weight: 500;">{st.session_state.sender_info['role'] or 'Not specified'}</div>
            </div>
            <div>
                <div style="color: #8892b0; font-size: 0.85rem; margin-bottom: 5px;">Expertise</div>
                <div style="color: #e6f7ff; font-weight: 500;">{st.session_state.sender_info['expertise'] or 'Not specified'}</div>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

st.markdown("---")

# --- Profile Analysis Section ---
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 20px;"><i class="fas fa-search" style="margin-right: 12px;"></i>Profile Analysis</h3>', unsafe_allow_html=True)
st.markdown('<p style="color: #8892b0; margin-bottom: 30px;">Enter LinkedIn profile URL for AI-powered analysis and message generation</p>', unsafe_allow_html=True)

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
        "Initiate Analysis", 
        use_container_width=True,
        key="analyze_btn",
        disabled=not st.session_state.sender_info['configured']
    )

if not st.session_state.sender_info['configured']:
    st.warning("⚠️ Please configure your sender information above before analyzing profiles.")

# Custom button styling
st.markdown("""
<style>
div[data-testid="stButton"] > button[kind="secondary"] {
    background: linear-gradient(135deg, #00b4d8 0%, #0077b6 100%);
    color: white;
    border: none;
    padding: 18px 36px;
    border-radius: 16px;
    font-family: 'Space Grotesk', sans-serif;
    font-weight: 600;
    font-size: 1rem;
    cursor: pointer;
    transform-style: preserve-3d;
    transition: all 0.3s ease;
    box-shadow: 
        0 10px 30px rgba(0, 180, 216, 0.4),
        0 5px 15px rgba(0, 180, 216, 0.3),
        inset 0 1px 0 rgba(255, 255, 255, 0.3);
    position: relative;
    overflow: hidden;
    letter-spacing: 0.5px;
    width: 100%;
}

div[data-testid="stButton"] > button[kind="secondary"]:hover:not(:disabled) {
    transform: translateY(-3px) scale(1.02);
    box-shadow: 
        0 15px 40px rgba(0, 180, 216, 0.6),
        0 8px 25px rgba(0, 180, 216, 0.4),
        inset 0 1px 0 rgba(255, 255, 255, 0.4);
}

div[data-testid="stButton"] > button[kind="secondary"]:disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background: linear-gradient(135deg, #666 0%, #444 100%);
}

div[data-testid="stButton"] > button[kind="secondary"]::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
    transition: 0.5s;
}

div[data-testid="stButton"] > button[kind="secondary"]:hover::before {
    left: 100%;
}
</style>
""", unsafe_allow_html=True)

# --- Processing Logic ---
if analyze_clicked and linkedin_url and st.session_state.sender_info['configured']:
    with st.spinner(""):
        if not apify_api_key or not groq_api_key:
            st.error("API configuration required. Please verify secret keys.")
        else:
            st.session_state.processing_status = "Analyzing Profile"
            
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
                    st.session_state.processing_status = "Generating Intelligence"
                    
                    research_brief = generate_research_brief(profile_data, groq_api_key)
                    st.session_state.research_brief = research_brief
                    st.session_state.processing_status = "Analysis Complete"
                    
                    st.success("Profile analysis successfully completed")
                    
                    st.session_state.generated_messages = []
                    st.session_state.current_message_index = -1
                else:
                    st.session_state.processing_status = "Analysis Failed"
                    st.error("Unable to retrieve profile data")

# --- Results Display ---
if st.session_state.profile_data and st.session_state.research_brief:
    st.markdown("---")
    
    # Tab Interface
    tab1, tab2, tab3 = st.tabs([
        "Message Generation", 
        "Research Intelligence", 
        "Profile Data"
    ])
    
    with tab1:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-robot" style="margin-right: 12px;"></i>AI Message Generation</h3>', unsafe_allow_html=True)
        
        # Generate new message
        col_gen1, col_gen2 = st.columns([2, 1])
        
        with col_gen1:
            if st.button(
                "Generate AI Message", 
                use_container_width=True,
                key="generate_message"
            ):
                with st.spinner("Creating personalized message..."):
                    new_message = analyze_and_generate_message(
                        st.session_state.profile_data,
                        groq_api_key,
                        st.session_state.sender_info
                    )
                    
                    if new_message:
                        st.session_state.generated_messages.append(new_message)
                        st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                        st.rerun()
        
        with col_gen2:
            if len(st.session_state.generated_messages) > 0:
                if st.button(
                    "Refine Message", 
                    use_container_width=True,
                    key="refine_message"
                ):
                    st.session_state.regenerate_mode = True
                    st.rerun()
        
        # Display current message
        if len(st.session_state.generated_messages) > 0:
            current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
            
            st.markdown(f'''
            <div class="message-display-3d">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px;">
                    <div>
                        <h4 style="color: #e6f7ff; margin: 0;"><i class="fas fa-envelope" style="margin-right: 10px;"></i>Generated Message</h4>
                        <p style="color: #8892b0; font-size: 0.9rem; margin: 5px 0 0 0;">
                            {len(current_msg)} characters • Version {st.session_state.current_message_index + 1}
                        </p>
                    </div>
                    <div style="background: linear-gradient(135deg, rgba(0, 180, 216, 0.1), rgba(0, 255, 208, 0.1)); padding: 8px 16px; border-radius: 12px;">
                        <span style="color: #00ffd0; font-weight: 600;">AI Generated</span>
                    </div>
                </div>
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 16px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <pre style="white-space: pre-wrap; font-family: 'Inter', sans-serif; line-height: 1.8; margin: 0; color: #e6f7ff; font-size: 1.05rem;">
{current_msg}
                    </pre>
                </div>
            </div>
            ''', unsafe_allow_html=True)
            
            # Action buttons
            col_copy, col_prev, col_next, col_count = st.columns([2, 1, 1, 1])
            
            with col_copy:
                st.code(current_msg, language=None)
            
            with col_prev:
                if st.button("Previous", use_container_width=True, disabled=st.session_state.current_message_index <= 0):
                    st.session_state.current_message_index -= 1
                    st.session_state.regenerate_mode = False
                    st.rerun()
            
            with col_next:
                if st.button("Next", use_container_width=True, disabled=st.session_state.current_message_index >= len(st.session_state.generated_messages) - 1):
                    st.session_state.current_message_index += 1
                    st.session_state.regenerate_mode = False
                    st.rerun()
            
            with col_count:
                st.markdown(f'<p style="color: #e6f7ff; text-align: center; font-weight: 600;">{st.session_state.current_message_index + 1}/{len(st.session_state.generated_messages)}</p>', unsafe_allow_html=True)
            
            # Refinement Mode
            if st.session_state.regenerate_mode:
                st.markdown("---")
                st.markdown('<h4 style="color: #e6f7ff;"><i class="fas fa-magic" style="margin-right: 10px;"></i>Message Refinement</h4>', unsafe_allow_html=True)
                
                with st.form("refinement_form"):
                    instructions = st.text_area(
                        "Refinement Instructions",
                        value=st.session_state.message_instructions,
                        placeholder="Example: 'Make it more technical', 'Focus on leadership experience', 'Shorten to 200 characters'",
                        height=100
                    )
                    
                    col_ref1, col_ref2, col_ref3 = st.columns([2, 1, 1])
                    
                    with col_ref1:
                        refine_submit = st.form_submit_button(
                            "Generate Refined Version",
                            use_container_width=True
                        )
                    
                    with col_ref2:
                        cancel_refine = st.form_submit_button(
                            "Cancel",
                            use_container_width=True
                        )
                    
                    if refine_submit and instructions:
                        with st.spinner("Refining message..."):
                            refined_message = analyze_and_generate_message(
                                st.session_state.profile_data,
                                groq_api_key,
                                st.session_state.sender_info,
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
                st.markdown('<h4 style="color: #e6f7ff; margin-bottom: 20px;"><i class="fas fa-history" style="margin-right: 10px;"></i>Message History</h4>', unsafe_allow_html=True)
                
                for idx, msg in enumerate(st.session_state.generated_messages):
                    is_active = idx == st.session_state.current_message_index
                    border_color = "#00b4d8" if is_active else "rgba(0, 180, 216, 0.2)"
                    bg_color = "rgba(0, 180, 216, 0.05)" if is_active else "rgba(255, 255, 255, 0.02)"
                    
                    st.markdown(f'''
                    <div style="background: {bg_color}; padding: 18px; border-radius: 16px; margin: 10px 0; border: 1px solid {border_color}; cursor: pointer; transition: all 0.3s;"
                         onclick="window.location.href='?select={idx}'">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center;">
                                <span style="color: #e6f7ff; font-weight: 600; margin-right: 15px;">Version {idx + 1}</span>
                                <span style="color: #8892b0; font-size: 0.85rem;">
                                    <i class="fas fa-ruler" style="margin-right: 5px;"></i>{len(msg)} chars
                                </span>
                            </div>
                            {f'<span style="color: #00ffd0; font-weight: 600; font-size: 0.9rem;"><i class="fas fa-check-circle" style="margin-right: 5px;"></i>Active</span>' if is_active else ''}
                        </div>
                        <div style="color: #a8c1d1; font-size: 0.9rem; line-height: 1.5;">
                            {msg.split('\\n')[0][:90]}...
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
        
        else:
            st.markdown('''
            <div class="config-card-3d" style="text-align: center; padding: 60px 30px;">
                <div style="font-size: 4rem; margin-bottom: 20px; color: #00b4d8;">
                    <i class="fas fa-comment-dots"></i>
                </div>
                <h4 style="color: #e6f7ff; margin-bottom: 15px;">Generate Your First Message</h4>
                <p style="color: #8892b0; max-width: 400px; margin: 0 auto;">
                    Click the "Generate AI Message" button above to create a personalized LinkedIn connection message based on the analyzed profile.
                </p>
            </div>
            ''', unsafe_allow_html=True)
    
    with tab2:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-chart-line" style="margin-right: 12px;"></i>Research Intelligence Brief</h3>', unsafe_allow_html=True)
        st.markdown('<div class="config-card-3d">', unsafe_allow_html=True)
        st.markdown(st.session_state.research_brief)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab3:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-user-tie" style="margin-right: 12px;"></i>Profile Data Analysis</h3>', unsafe_allow_html=True)
        with st.expander("View Raw Profile Data", expanded=False):
            st.json(st.session_state.profile_data)

else:
    # Welcome State
    st.markdown('''
    <div style="text-align: center; padding: 80px 20px;">
        <div style="position: relative; display: inline-block; margin-bottom: 40px;">
            <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #00b4d8, #00ffd0); border-radius: 30px; transform: rotate(45deg); margin: 0 auto 40px; position: relative; box-shadow: 0 20px 60px rgba(0, 180, 216, 0.4);">
                <i class="fas fa-brain" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-45deg); font-size: 3rem; color: white;"></i>
            </div>
        </div>
        <h2 style="color: #e6f7ff; margin-bottom: 20px; font-size: 2.5rem;">LINZY</h2>
        <p style="color: #8892b0; max-width: 600px; margin: 0 auto 50px; line-height: 1.8; font-size: 1.1rem;">
            Advanced AI-powered prospect intelligence system. Analyze LinkedIn profiles, generate personalized messages, and create detailed research briefs with neural network precision.
        </p>
        <div style="display: flex; justify-content: center; gap: 30px; flex-wrap: wrap;">
            <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                <div style="color: #00b4d8; font-size: 2rem; margin-bottom: 15px;">
                    <i class="fas fa-bolt"></i>
                </div>
                <h4 style="color: #e6f7ff; margin-bottom: 10px;">Fast Analysis</h4>
                <p style="color: #8892b0; font-size: 0.9rem;">Real-time profile processing with AI intelligence</p>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                <div style="color: #00ffd0; font-size: 2rem; margin-bottom: 15px;">
                    <i class="fas fa-robot"></i>
                </div>
                <h4 style="color: #e6f7ff; margin-bottom: 10px;">AI Powered</h4>
                <p style="color: #8892b0; font-size: 0.9rem;">Linzy message generation and refinement</p>
            </div>
            <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                <div style="color: #c8b6ff; font-size: 2rem; margin-bottom: 15px;">
                    <i class="fas fa-chart-network"></i>
                </div>
                <h4 style="color: #e6f7ff; margin-bottom: 10px;">Smart Insights</h4>
                <p style="color: #8892b0; font-size: 0.9rem;">Comprehensive research and data analysis</p>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

st.markdown('</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown('<p style="color: #8892b0; font-size: 0.9rem;">Linzy v2.1 | AI Prospect Intelligence</p>', unsafe_allow_html=True)
with col_f2:
    st.markdown(f'<p style="color: #8892b0; font-size: 0.9rem; text-align: center;">Last Updated: {datetime.now().strftime("%H:%M:%S")}</p>', unsafe_allow_html=True)
with col_f3:
    if st.session_state.profile_data:
        name = "Profile Loaded"
        if isinstance(st.session_state.profile_data, dict):
            if 'fullname' in st.session_state.profile_data:
                name = st.session_state.profile_data['fullname'][:25]
        st.markdown(f'<p style="color: #8892b0; font-size: 0.9rem; text-align: right;">Active: {name}</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p style="color: #8892b0; font-size: 0.9rem; text-align: right;">Status: Ready</p>', unsafe_allow_html=True)

# Add JavaScript for Enhanced 3D Effects and Input Animations
st.markdown("""
<script>
// Enhanced 3D tilt effect to main card
document.addEventListener('DOMContentLoaded', function() {
    const mainCard = document.querySelector('.main-3d-card');
    
    if (mainCard) {
        mainCard.addEventListener('mousemove', function(e) {
            const rect = this.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const y = e.clientY - rect.top;
            
            const centerX = rect.width / 2;
            const centerY = rect.height / 2;
            
            const rotateY = ((x - centerX) / centerX) * 3;
            const rotateX = ((centerY - y) / centerY) * 3;
            
            this.style.transform = `rotateY(${rotateY}deg) rotateX(${rotateX}deg) translateY(-10px)`;
        });
        
        mainCard.addEventListener('mouseleave', function() {
            this.style.transform = 'rotateY(-2deg) rotateX(1deg) translateY(0)';
        });
    }
    
    // Enhanced input focus effects
    const enhancedInputs = document.querySelectorAll('.enhanced-input-3d');
    enhancedInputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.style.transform = 'translateY(-5px)';
        });
        
        input.addEventListener('blur', function() {
            this.parentElement.style.transform = 'translateY(0)';
        });
    });
    
    // Message history click handler
    const urlParams = new URLSearchParams(window.location.search);
    const selectIdx = urlParams.get('select');
    if (selectIdx) {
        setTimeout(() => {
            window.history.replaceState({}, document.title, window.location.pathname);
        }, 100);
    }
    
    // Success animation trigger
    if (document.querySelector('.success-animation')) {
        setTimeout(() => {
            document.querySelector('.success-animation').classList.remove('success-animation');
        }, 500);
    }
});
</script>
""", unsafe_allow_html=True)
