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

def analyze_sender_profile(sender_data: dict) -> dict:
    """Extract key information from sender profile."""
    sender_info = {
        'name': '',
        'headline': '',
        'current_company': '',
        'current_role': '',
        'summary': '',
        'experience': [],
        'expertise': ''
    }
    
    try:
        if isinstance(sender_data, dict):
            # Extract name
            if sender_data.get('fullname'):
                sender_info['name'] = sender_data['fullname']
            elif sender_data.get('basic_info') and sender_data['basic_info'].get('fullname'):
                sender_info['name'] = sender_data['basic_info']['fullname']
            
            # Extract headline
            if sender_data.get('headline'):
                sender_info['headline'] = sender_data['headline']
                # Try to extract role and company from headline
                headline_parts = sender_data['headline'].split(' at ')
                if len(headline_parts) > 1:
                    sender_info['current_role'] = headline_parts[0].strip()
                    sender_info['current_company'] = headline_parts[1].strip()
            
            # Extract summary/about
            if sender_data.get('about'):
                sender_info['summary'] = sender_data['about'][:500]
            
            # Extract experience
            if sender_data.get('experience'):
                experiences = sender_data.get('experience', [])
                if experiences and len(experiences) > 0:
                    sender_info['experience'] = experiences
                    if not sender_info['current_role'] and experiences[0].get('title'):
                        sender_info['current_role'] = experiences[0].get('title')
                    if not sender_info['current_company'] and experiences[0].get('company'):
                        sender_info['current_company'] = experiences[0].get('company')
            
            # Determine expertise based on experience and summary
            expertise_keywords = []
            if sender_info['summary']:
                tech_keywords = ['AI', 'machine learning', 'data', 'software', 'technology', 'engineering', 'cloud', 'SaaS', 'fintech']
                for keyword in tech_keywords:
                    if keyword.lower() in sender_info['summary'].lower():
                        expertise_keywords.append(keyword)
            
            if expertise_keywords:
                sender_info['expertise'] = ', '.join(expertise_keywords)
            else:
                sender_info['expertise'] = sender_info['current_role'] or "Professional"
    
    except Exception as e:
        pass
    
    return sender_info

def analyze_and_generate_message(prospect_data: dict, sender_data: dict, api_key: str, 
                                user_instructions: str = None, previous_message: str = None) -> str:
    """
    Generate LinkedIn messages using 3-line structure:
    1st line: About the prospect
    2nd line: About sender's intention/value
    3rd line: Connection request
    """
    # Extract prospect information
    prospect_name = "there"
    prospect_info = []
    
    try:
        if isinstance(prospect_data, dict):
            # Extract prospect name
            if prospect_data.get('fullname'):
                prospect_name = prospect_data.get('fullname').split()[0]
            elif prospect_data.get('basic_info') and prospect_data['basic_info'].get('fullname'):
                prospect_name = prospect_data['basic_info']['fullname'].split()[0]
            
            # Extract key elements for prospect
            if prospect_data.get('headline'):
                prospect_info.append(f"Current Role: {prospect_data['headline']}")
            if prospect_data.get('about'):
                prospect_info.append(f"About: {prospect_data['about'][:300]}")
            if prospect_data.get('experience'):
                experiences = prospect_data.get('experience', [])
                if experiences and len(experiences) > 0:
                    current_exp = experiences[0]
                    role = current_exp.get('title', '')
                    company = current_exp.get('company', '')
                    if role and company:
                        prospect_info.append(f"Current Position: {role} at {company}")
                        # Get industry/specialty from role
                        if any(word in role.lower() for word in ['data', 'ai', 'machine', 'software', 'tech']):
                            prospect_info.append(f"Field: Technology/Data")
                        elif any(word in role.lower() for word in ['sales', 'business', 'marketing']):
                            prospect_info.append(f"Field: Business Development")
                        elif any(word in role.lower() for word in ['finance', 'accounting', 'banking']):
                            prospect_info.append(f"Field: Finance")
        
        prospect_summary = "\n".join(prospect_info)
        
    except Exception as e:
        prospect_summary = json.dumps(prospect_data, indent=2)[:1500]
    
    # Extract sender information
    sender_info = analyze_sender_profile(sender_data)
    sender_name = sender_info['name'].split()[0] if sender_info['name'] else "Joseph"
    
    # Prepare sender context
    sender_context = f"Sender Name: {sender_info['name']}"
    if sender_info['current_role']:
        sender_context += f"\nSender Role: {sender_info['current_role']}"
    if sender_info['current_company']:
        sender_context += f"\nSender Company: {sender_info['current_company']}"
    if sender_info['expertise']:
        sender_context += f"\nSender Expertise: {sender_info['expertise']}"
    if sender_info['summary']:
        sender_context += f"\nSender Summary: {sender_info['summary'][:300]}"
    
    # CRITICAL: 3-line message structure
    if user_instructions and previous_message:
        # Refinement mode
        prompt = f'''Generate a refined LinkedIn connection message following this EXACT 3-line structure:

1st line: Something specific about the PROSPECT (their role, achievement, or background)
2nd line: Your VALUE/INTENTION related to their field (based on your background)
3rd line: Polite connection request

PROSPECT INFORMATION:
{prospect_summary}

YOUR (SENDER) INFORMATION:
{sender_context}

ORIGINAL MESSAGE TO REFINE:
{previous_message}

REFINEMENT INSTRUCTIONS:
{user_instructions}

CRITICAL REQUIREMENTS:
1. Use EXACTLY 3 lines, each line separate
2. Line 1: Start with "Hi [First Name]," then mention something specific about prospect
3. Line 2: Your value proposition/intention (professional only)
4. Line 3: Connection request like "Would be glad to connect."
5. End with "Best, [Your First Name]"
6. TOTAL CHARACTERS: Under 275
7. NO flirty, romantic, or informal language - strictly professional
8. NO generic phrases like "came across your profile"

Generate ONLY the refined message:'''
    else:
        # New generation mode
        prompt = f'''Generate a LinkedIn connection message following this EXACT 3-line structure:

1st line: Something specific about the PROSPECT (their role, achievement, or background)
2nd line: Your VALUE/INTENTION related to their field (based on your background)
3rd line: Polite connection request

PROSPECT INFORMATION:
{prospect_summary}

YOUR (SENDER) INFORMATION:
{sender_context}

CRITICAL REQUIREMENTS:
1. Use EXACTLY 3 lines, each line separate
2. Line 1: Start with "Hi {prospect_name}," then mention something specific about their profile
3. Line 2: Connect your background/expertise to their field
4. Line 3: Connection request like "Would be glad to connect."
5. End with "Best, {sender_name}"
6. TOTAL CHARACTERS: Under 275
7. NO flirty, romantic, or informal language - strictly professional
8. NO generic phrases like "came across your profile"
9. Focus on mutual professional interests

Examples of proper structure:
"Hi David,
Your FP&A leadership at Planet shows rare execution depth.
I focus on automating financial workflows to improve forecasting.
Would be glad to connect.
Best, Joseph"

Generate ONLY the message with exactly 3 content lines plus greeting and signature:'''
    
    try:
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system", 
                    "content": f'''You are a professional LinkedIn connection message writer.
                    You MUST follow this exact 3-line structure:
                    1. Greeting + something specific about the prospect
                    2. Your value/intention related to their field
                    3. Polite connection request
                    
                    Rules:
                    - No flirty or romantic language
                    - No informal tone
                    - No generic phrases
                    - Keep it professional and concise
                    - Always end with "Best, [First Name]"'''
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 350
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=40
        )
        
        if response.status_code == 200:
            message = response.json()["choices"][0]["message"]["content"].strip()
            
            # Clean and validate message
            message = message.replace('"', '').replace("''", "'").strip()
            
            # Ensure proper greeting
            if not message.lower().startswith(f"hi {prospect_name.lower()},"):
                # Add proper greeting
                message = f"Hi {prospect_name},\n{message}"
            
            # Ensure proper signature
            if not message.strip().endswith(f"Best, {sender_name}"):
                message = f"{message.rstrip()}\nBest, {sender_name}"
            
            # Validate 3-line structure (excluding greeting and signature)
            lines = message.split('\n')
            content_lines = [line for line in lines if line and not line.startswith('Hi ') and not line.startswith('Best, ')]
            
            if len(content_lines) != 3:
                # Try to fix structure
                if len(content_lines) > 3:
                    # Take first 3 content lines
                    content_lines = content_lines[:3]
                elif len(content_lines) < 3:
                    # Add missing lines
                    while len(content_lines) < 3:
                        content_lines.append("Would be glad to connect.")
                
                # Reconstruct message
                message = f"Hi {prospect_name},\n" + "\n".join(content_lines) + f"\nBest, {sender_name}"
            
            # Check for forbidden content
            forbidden_phrases = [
                "beautiful", "attractive", "handsome", "cute", "sexy",
                "date", "dinner", "coffee date", "romantic", "love",
                "hot", "gorgeous", "stunning", "hey baby", "hey sexy",
                "sweetheart", "darling", "honey", "babe", "dear"
            ]
            
            for phrase in forbidden_phrases:
                if phrase.lower() in message.lower():
                    # Regenerate with stricter filter
                    strict_prompt = f'''Regenerate message for {prospect_name}. 
                    REMOVE ALL romantic/flirty language.
                    Keep strictly professional.
                    Profile: {prospect_summary[:300]}
                    Your info: {sender_context[:300]}'''
                    
                    strict_payload = {
                        "model": "llama-3.1-8b-instant",
                        "messages": [
                            {"role": "system", "content": "STRICTLY PROFESSIONAL ONLY. No flirty language. 3-line structure."},
                            {"role": "user", "content": strict_prompt}
                        ],
                        "temperature": 0.5,
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
                if len(lines) >= 5:  # Greeting + 3 content + signature
                    # Shorten middle lines if needed
                    shortened = [lines[0]]
                    for i in range(1, 4):  # Content lines
                        if i < len(lines):
                            if len(lines[i]) > 100:
                                shortened.append(lines[i][:97] + '...')
                            else:
                                shortened.append(lines[i])
                    shortened.append(lines[-1])
                    message = '\n'.join(shortened)
                
                if len(message) > 275:
                    message = message[:272] + '...'
            
            return message
            
        else:
            # Safe fallback with proper structure
            return f"Hi {prospect_name},\nYour professional background in your field is impressive.\nI work on operational improvements in similar areas.\nWould be glad to connect.\nBest, {sender_name}"
            
    except Exception as e:
        # Professional fallback
        return f"Hi {prospect_name},\nYour experience in your industry caught my attention.\nI focus on business improvements in related fields.\nWould be good to connect.\nBest, {sender_name}"

# ========== STREAMLIT APPLICATION ==========

st.set_page_config(
    page_title="Linzy | AI Prospect Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Modern 3D Color Theory CSS ---
modern_3d_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0a192f 0%, #1a1a2e 50%, #16213e 100%);
        font-family: 'Space Grotesk', sans-serif;
        min-height: 100vh;
    }
    
    /* Main Container */
    .main-container {
        background: linear-gradient(145deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
        backdrop-filter: blur(20px);
        border-radius: 32px;
        padding: 40px;
        margin: 20px;
        border: 1px solid rgba(0, 180, 216, 0.1);
        box-shadow: 
            0 50px 100px rgba(0, 180, 216, 0.1),
            inset 0 1px 0 rgba(255, 255, 255, 0.1),
            0 0 100px rgba(0, 180, 216, 0.05);
        animation: float3d 6s ease-in-out infinite;
        position: relative;
        overflow: hidden;
    }
    
    @keyframes float3d {
        0%, 100% { transform: translateY(0) rotateX(1deg); }
        50% { transform: translateY(-10px) rotateX(1deg); }
    }
    
    .main-container::before {
        content: '';
        position: absolute;
        top: 0;
        left: -100%;
        width: 100%;
        height: 100%;
        background: linear-gradient(90deg, transparent, rgba(0, 180, 216, 0.1), transparent);
        transition: 0.5s;
    }
    
    .main-container:hover::before {
        left: 100%;
    }
    
    /* Gradient Text */
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
    
    /* 3D Input Fields */
    .input-3d {
        background: rgba(255, 255, 255, 0.03);
        border: 2px solid rgba(0, 180, 216, 0.2);
        border-radius: 16px;
        padding: 18px 24px;
        font-family: 'Space Grotesk', sans-serif;
        font-size: 1rem;
        color: #e6f7ff;
        transition: all 0.3s ease;
        backdrop-filter: blur(10px);
        box-shadow: 
            inset 0 2px 4px rgba(0, 0, 0, 0.1),
            0 4px 20px rgba(0, 180, 216, 0.1);
    }
    
    .input-3d:focus {
        background: rgba(255, 255, 255, 0.05);
        border-color: #00b4d8;
        box-shadow: 
            0 0 0 4px rgba(0, 180, 216, 0.15),
            inset 0 2px 8px rgba(0, 180, 216, 0.1);
        outline: none;
        animation: inputGlow 2s ease-in-out infinite;
    }
    
    @keyframes inputGlow {
        0%, 100% { box-shadow: 0 0 0 4px rgba(0, 180, 216, 0.15); }
        50% { box-shadow: 0 0 0 6px rgba(0, 180, 216, 0.25); }
    }
    
    /* 3D Cards */
    .card-3d {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 24px;
        padding: 25px;
        margin: 15px 0;
        border: 1px solid rgba(0, 180, 216, 0.1);
        transform-style: preserve-3d;
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        backdrop-filter: blur(10px);
        box-shadow: 
            0 20px 60px rgba(0, 0, 0, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
    
    .card-3d:hover {
        transform: translateY(-5px);
        border-color: rgba(0, 180, 216, 0.3);
        box-shadow: 
            0 30px 80px rgba(0, 180, 216, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 0.15);
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
    
    /* Message Structure Display */
    .message-structure {
        background: linear-gradient(135deg, rgba(0, 180, 216, 0.05), rgba(0, 255, 208, 0.05));
        border-left: 4px solid #00b4d8;
        padding: 25px;
        border-radius: 20px;
        margin: 20px 0;
        font-family: 'Inter', sans-serif;
        line-height: 1.8;
        color: #e6f7ff;
        animation: slideIn 0.6s cubic-bezier(0.175, 0.885, 0.32, 1.275);
    }
    
    @keyframes slideIn {
        from {
            opacity: 0;
            transform: translateY(20px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* Structure Guide */
    .structure-guide {
        background: rgba(255, 255, 255, 0.02);
        border: 1px dashed rgba(0, 180, 216, 0.3);
        border-radius: 16px;
        padding: 20px;
        margin: 15px 0;
    }
    
    .structure-line {
        display: flex;
        align-items: center;
        margin: 8px 0;
        padding: 8px 12px;
        border-radius: 10px;
        background: rgba(0, 180, 216, 0.05);
    }
    
    .line-number {
        width: 30px;
        height: 30px;
        background: linear-gradient(135deg, #00b4d8, #0077b6);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: 600;
        margin-right: 15px;
        box-shadow: 0 4px 15px rgba(0, 180, 216, 0.3);
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
    
    /* Button Styling */
    .stButton > button {
        background: linear-gradient(135deg, #00b4d8 0%, #0077b6 100%);
        color: white;
        border: none;
        padding: 14px 28px;
        border-radius: 14px;
        font-family: 'Space Grotesk', sans-serif;
        font-weight: 600;
        font-size: 0.95rem;
        cursor: pointer;
        transition: all 0.3s ease;
        box-shadow: 
            0 8px 25px rgba(0, 180, 216, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.2);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 
            0 12px 35px rgba(0, 180, 216, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .stButton > button:active {
        transform: translateY(0);
        box-shadow: 
            0 5px 20px rgba(0, 180, 216, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
</style>

<!-- Font Awesome Icons -->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
"""

st.markdown(modern_3d_css, unsafe_allow_html=True)

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
if 'sender_info' not in st.session_state:
    st.session_state.sender_info = None
if 'sender_data' not in st.session_state:
    st.session_state.sender_data = None
if 'message_instructions' not in st.session_state:
    st.session_state.message_instructions = ""
if 'regenerate_mode' not in st.session_state:
    st.session_state.regenerate_mode = False
if 'sender_processing' not in st.session_state:
    st.session_state.sender_processing = False

# --- Main Container ---
st.markdown('<div class="main-container">', unsafe_allow_html=True)

# --- Header Section ---
col1, col2 = st.columns([4, 1])
with col1:
    st.markdown('<h1 class="gradient-text-primary" style="font-size: 3.5rem; margin-bottom: 10px;">LINZY</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color: #8892b0; font-size: 1.2rem; margin-bottom: 40px;">AI-Powered LinkedIn Message Generator</p>', unsafe_allow_html=True)
with col2:
    sender_name = "Not Set"
    if st.session_state.sender_info:
        sender_name = st.session_state.sender_info.get('name', 'Not Set').split()[0][:15]
    
    st.markdown(f'''
    <div class="card-3d" style="text-align: center; padding: 20px;">
        <div style="display: flex; align-items: center; justify-content: center; margin-bottom: 10px;">
            <span class="status-orb {'active' if st.session_state.profile_data else ''}"></span>
            <span style="color: #e6f7ff; font-weight: 600;">{st.session_state.processing_status}</span>
        </div>
        <div style="color: #8892b0; font-size: 0.9rem;">
            <div><i class="fas fa-user" style="margin-right: 8px;"></i> Sender: {sender_name}</div>
            <div><i class="fas fa-message" style="margin-right: 8px;"></i> Messages: {len(st.session_state.generated_messages)}</div>
            <div><i class="fas fa-clock" style="margin-right: 8px;"></i> {datetime.now().strftime('%H:%M:%S')}</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

# --- Message Structure Guide ---
st.markdown("---")
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 20px;"><i class="fas fa-project-diagram" style="margin-right: 12px;"></i>Message Structure</h3>', unsafe_allow_html=True)

st.markdown('''
<div class="structure-guide">
    <div class="structure-line">
        <div class="line-number">1</div>
        <div>
            <strong style="color: #00ffd0;">About the Prospect</strong>
            <div style="color: #8892b0; font-size: 0.9rem;">Specific mention of their role, achievement, or background</div>
        </div>
    </div>
    <div class="structure-line">
        <div class="line-number">2</div>
        <div>
            <strong style="color: #00b4d8;">Your Value/Intention</strong>
            <div style="color: #8892b0; font-size: 0.9rem;">How your expertise relates to their field</div>
        </div>
    </div>
    <div class="structure-line">
        <div class="line-number">3</div>
        <div>
            <strong style="color: #c8b6ff;">Connection Request</strong>
            <div style="color: #8892b0; font-size: 0.9rem;">Polite request to connect professionally</div>
        </div>
    </div>
</div>
''', unsafe_allow_html=True)

# --- Sender Configuration Section ---
st.markdown("---")
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-user-tie" style="margin-right: 12px;"></i>Your Information</h3>', unsafe_allow_html=True)

sender_col1, sender_col2 = st.columns([2, 1])

with sender_col1:
    sender_linkedin_url = st.text_input(
        "Your LinkedIn Profile URL",
        placeholder="https://linkedin.com/in/yourprofile",
        help="Paste your LinkedIn URL to help AI understand your background"
    )

with sender_col2:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    analyze_sender_clicked = st.button(
        "Analyze My Profile",
        use_container_width=True,
        key="analyze_sender"
    )

# Handle sender profile analysis
if analyze_sender_clicked and sender_linkedin_url:
    if not apify_api_key:
        st.error("API key configuration required.")
    else:
        st.session_state.sender_processing = True
        with st.spinner("Analyzing your profile..."):
            username = extract_username_from_url(sender_linkedin_url)
            run_info = start_apify_run(username, apify_api_key)
            
            if run_info:
                sender_data = poll_apify_run_with_status(
                    run_info["run_id"],
                    run_info["dataset_id"],
                    apify_api_key
                )
                
                if sender_data:
                    st.session_state.sender_data = sender_data
                    st.session_state.sender_info = analyze_sender_profile(sender_data)
                    st.success(" Your profile analyzed successfully!")
                    st.session_state.sender_processing = False
                    
                    # Display sender info
                    with st.expander(" Your Profile Summary", expanded=True):
                        if st.session_state.sender_info:
                            info = st.session_state.sender_info
                            st.markdown(f"""
                            **Name:** {info.get('name', 'N/A')}
                            **Current Role:** {info.get('current_role', 'N/A')}
                            **Company:** {info.get('current_company', 'N/A')}
                            **Expertise:** {info.get('expertise', 'N/A')}
                            """)
                else:
                    st.error("Failed to analyze your profile.")
                    st.session_state.sender_processing = False

# Display current sender info if available
if st.session_state.sender_info and not st.session_state.sender_processing:
    with st.expander(" Your Current Profile Info", expanded=False):
        info = st.session_state.sender_info
        st.markdown(f"""
        <div class="card-3d">
            <div style="color: #e6f7ff; margin-bottom: 15px;">
                <strong>Name:</strong> {info.get('name', 'N/A')}<br>
                <strong>Current Role:</strong> {info.get('current_role', 'N/A')}<br>
                <strong>Company:</strong> {info.get('current_company', 'N/A')}<br>
                <strong>Expertise:</strong> {info.get('expertise', 'N/A')}
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- Prospect Analysis Section ---
st.markdown("---")
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 20px;"><i class="fas fa-search" style="margin-right: 12px;"></i>Prospect Analysis</h3>', unsafe_allow_html=True)

prospect_col1, prospect_col2 = st.columns([3, 1])

with prospect_col1:
    prospect_linkedin_url = st.text_input(
        "Prospect's LinkedIn Profile URL",
        placeholder="https://linkedin.com/in/prospectprofile",
        help="Paste the prospect's LinkedIn URL to analyze"
    )

with prospect_col2:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    analyze_prospect_clicked = st.button(
        "Analyze Prospect",
        use_container_width=True,
        key="analyze_prospect",
        disabled=not st.session_state.sender_info
    )

if not st.session_state.sender_info:
    st.warning(" Please analyze your profile first to generate personalized messages.")

# Handle prospect analysis
if analyze_prospect_clicked and prospect_linkedin_url and st.session_state.sender_info:
    if not apify_api_key or not groq_api_key:
        st.error("API configuration required.")
    else:
        st.session_state.processing_status = "Analyzing Prospect"
        
        username = extract_username_from_url(prospect_linkedin_url)
        run_info = start_apify_run(username, apify_api_key)
        
        if run_info:
            profile_data = poll_apify_run_with_status(
                run_info["run_id"],
                run_info["dataset_id"],
                apify_api_key
            )
            
            if profile_data:
                st.session_state.profile_data = profile_data
                st.session_state.processing_status = "Generating Research"
                
                research_brief = generate_research_brief(profile_data, groq_api_key)
                st.session_state.research_brief = research_brief
                st.session_state.processing_status = "Ready"
                
                st.success(" Prospect analysis complete!")
                
                st.session_state.generated_messages = []
                st.session_state.current_message_index = -1
            else:
                st.session_state.processing_status = "Error"
                st.error("Failed to analyze prospect profile.")

# --- Results Display ---
if st.session_state.profile_data and st.session_state.research_brief and st.session_state.sender_info:
    st.markdown("---")
    
    # Tab Interface
    tab1, tab2, tab3 = st.tabs([
        "Message Generation", 
        "Research Brief", 
        "Profile Data"
    ])
    
    with tab1:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-robot" style="margin-right: 12px;"></i>Generate Message</h3>', unsafe_allow_html=True)
        
        # Generate new message
        col_gen1, col_gen2 = st.columns([2, 1])
        
        with col_gen1:
            if st.button(
                "Generate AI Message", 
                use_container_width=True,
                key="generate_message"
            ):
                with st.spinner("Creating 3-line message..."):
                    new_message = analyze_and_generate_message(
                        st.session_state.profile_data,
                        st.session_state.sender_data,
                        groq_api_key
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
            
            # Analyze message structure
            lines = current_msg.split('\n')
            structure_analysis = []
            for i, line in enumerate(lines):
                if i == 0 and line.startswith('Hi '):
                    structure_analysis.append(f" <strong>Greeting:</strong> {line}")
                elif i == len(lines) - 1 and line.startswith('Best, '):
                    structure_analysis.append(f"<strong>Signature:</strong> {line}")
                else:
                    if i == 1:
                        structure_analysis.append(f" <strong>Line 1 (About Prospect):</strong> {line}")
                    elif i == 2:
                        structure_analysis.append(f" <strong>Line 2 (Your Value):</strong> {line}")
                    elif i == 3:
                        structure_analysis.append(f" <strong>Line 3 (Connection):</strong> {line}")
            
            st.markdown(f'''
            <div class="message-structure">
                <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px;">
                    <div>
                        <h4 style="color: #e6f7ff; margin: 0;"><i class="fas fa-envelope" style="margin-right: 10px;"></i>Generated Message</h4>
                        <p style="color: #8892b0; font-size: 0.9rem; margin: 5px 0 0 0;">
                            {len(current_msg)} characters • Version {st.session_state.current_message_index + 1}
                        </p>
                    </div>
                    <div style="background: linear-gradient(135deg, rgba(0, 180, 216, 0.1), rgba(0, 255, 208, 0.1)); padding: 8px 16px; border-radius: 12px;">
                        <span style="color: #00ffd0; font-weight: 600;">3-Line Structure</span>
                    </div>
                </div>
                
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 16px; border: 1px solid rgba(0, 180, 216, 0.1); margin: 20px 0;">
                    <pre style="white-space: pre-wrap; font-family: 'Inter', sans-serif; line-height: 1.8; margin: 0; color: #e6f7ff; font-size: 1.05rem;">
{current_msg}
                    </pre>
                </div>
                
                <div style="margin-top: 25px;">
                    <h5 style="color: #e6f7ff; margin-bottom: 15px;">Structure Analysis:</h5>
                    <div style="background: rgba(255, 255, 255, 0.02); padding: 20px; border-radius: 12px;">
                        {"<br>".join(structure_analysis)}
                    </div>
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
                st.markdown('<h4 style="color: #e6f7ff;"><i class="fas fa-magic" style="margin-right: 10px;"></i>Refine Message</h4>', unsafe_allow_html=True)
                
                with st.form("refinement_form"):
                    instructions = st.text_area(
                        "How would you like to improve this message?",
                        value=st.session_state.message_instructions,
                        placeholder="Example: 'Make line 2 more technical', 'Shorten line 1', 'Focus on AI experience in line 2'",
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
                                st.session_state.sender_data,
                                groq_api_key,
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
                    
                    # Extract first line of content for preview
                    lines = msg.split('\n')
                    preview = lines[1] if len(lines) > 1 else msg[:80]
                    
                    st.markdown(f'''
                    <div style="background: {bg_color}; padding: 18px; border-radius: 16px; margin: 10px 0; border: 1px solid {border_color}; cursor: pointer;"
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
                            {preview[:90]}...
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)
        
        else:
            st.markdown('''
            <div class="card-3d" style="text-align: center; padding: 60px 30px;">
                <div style="font-size: 4rem; margin-bottom: 20px; color: #00b4d8;">
                    <i class="fas fa-comment-dots"></i>
                </div>
                <h4 style="color: #e6f7ff; margin-bottom: 15px;">Generate Your First Message</h4>
                <p style="color: #8892b0; max-width: 400px; margin: 0 auto;">
                    Click "Generate AI Message" to create a 3-line personalized message using your profile and the prospect's information.
                </p>
            </div>
            ''', unsafe_allow_html=True)
    
    with tab2:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-chart-line" style="margin-right: 12px;"></i>Research Brief</h3>', unsafe_allow_html=True)
        st.markdown('<div class="card-3d">', unsafe_allow_html=True)
        st.markdown(st.session_state.research_brief)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab3:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;"><i class="fas fa-user-tie" style="margin-right: 12px;"></i>Profile Data</h3>', unsafe_allow_html=True)
        with st.expander("View Prospect Data", expanded=False):
            st.json(st.session_state.profile_data)
        
        with st.expander("View Your Data", expanded=False):
            if st.session_state.sender_data:
                st.json(st.session_state.sender_data)
            else:
                st.info("Your profile data not loaded.")

else:
    # Welcome State
    if not st.session_state.sender_info:
        st.markdown('''
        <div style="text-align: center; padding: 80px 20px;">
            <div style="position: relative; display: inline-block; margin-bottom: 40px;">
                <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #00b4d8, #00ffd0); border-radius: 30px; transform: rotate(45deg); margin: 0 auto 40px; position: relative; box-shadow: 0 20px 60px rgba(0, 180, 216, 0.4);">
                    <i class="fas fa-brain" style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%) rotate(-45deg); font-size: 3rem; color: white;"></i>
                </div>
            </div>
            <h2 style="color: #e6f7ff; margin-bottom: 20px; font-size: 2.5rem;">Get Started with LINZY</h2>
            <p style="color: #8892b0; max-width: 600px; margin: 0 auto 50px; line-height: 1.8; font-size: 1.1rem;">
                To generate personalized LinkedIn messages, please start by analyzing your own LinkedIn profile above.
            </p>
            <div style="display: flex; justify-content: center; gap: 30px; flex-wrap: wrap;">
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <div style="color: #00b4d8; font-size: 2rem; margin-bottom: 15px;">
                        <i class="fas fa-user-plus"></i>
                    </div>
                    <h4 style="color: #e6f7ff; margin-bottom: 10px;">1. Your Profile</h4>
                    <p style="color: #8892b0; font-size: 0.9rem;">Analyze your LinkedIn profile first</p>
                </div>
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <div style="color: #00ffd0; font-size: 2rem; margin-bottom: 15px;">
                        <i class="fas fa-search"></i>
                    </div>
                    <h4 style="color: #e6f7ff; margin-bottom: 10px;">2. Prospect Profile</h4>
                    <p style="color: #8892b0; font-size: 0.9rem;">Analyze the prospect's LinkedIn profile</p>
                </div>
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <div style="color: #c8b6ff; font-size: 2rem; margin-bottom: 15px;">
                        <i class="fas fa-robot"></i>
                    </div>
                    <h4 style="color: #e6f7ff; margin-bottom: 10px;">3. Generate</h4>
                    <p style="color: #8892b0; font-size: 0.9rem;">AI creates personalized 3-line messages</p>
                </div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.info(" Enter a prospect's LinkedIn URL above and click 'Analyze Prospect' to get started.")

st.markdown('</div>', unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown('<p style="color: #8892b0; font-size: 0.9rem;">Linzy v2.2 | AI LinkedIn Messaging</p>', unsafe_allow_html=True)
with col_f2:
    st.markdown(f'<p style="color: #8892b0; font-size: 0.9rem; text-align: center;">{datetime.now().strftime("%H:%M:%S")}</p>', unsafe_allow_html=True)
with col_f3:
    if st.session_state.profile_data:
        name = "Prospect Loaded"
        if isinstance(st.session_state.profile_data, dict):
            if 'fullname' in st.session_state.profile_data:
                name = st.session_state.profile_data['fullname'][:25]
        st.markdown(f'<p style="color: #8892b0; font-size: 0.9rem; text-align: right;">Prospect: {name}</p>', unsafe_allow_html=True)
    else:
        st.markdown('<p style="color: #8892b0; font-size: 0.9rem; text-align: right;">Status: Ready</p>', unsafe_allow_html=True)

# Add JavaScript for interactive effects
st.markdown("""
<script>
// Interactive input effects
document.addEventListener('DOMContentLoaded', function() {
    // Add focus effects to all inputs
    const inputs = document.querySelectorAll('input[type="text"]');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.style.transform = 'translateY(-3px)';
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
});
</script>
""", unsafe_allow_html=True)
