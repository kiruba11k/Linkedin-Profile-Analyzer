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

def analyze_sender_profile_with_llm(profile_text: str, api_key: str) -> dict:
    """
    Use LLM to analyze and extract sender profile information from any text input.
    """
    try:
        prompt = f'''Analyze this LinkedIn profile information and extract key details:

PROFILE TEXT:
{profile_text}

Extract the following information in JSON format:
1. name (full name)
2. current_role (current job title)
3. current_company (current company)
4. expertise (areas of expertise/skills)
5. industry (industry/sector)
6. key_achievements (notable achievements)
7. professional_summary (brief professional summary)

Return only valid JSON with these keys.'''
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional profile analyzer. Extract structured information from profile text."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 500,
            "response_format": {"type": "json_object"}
        }
        
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()["choices"][0]["message"]["content"]
            return json.loads(result)
        else:
            return {
                "name": "Professional Contact",
                "current_role": "Professional",
                "current_company": "",
                "expertise": "Various",
                "industry": "",
                "key_achievements": "",
                "professional_summary": ""
            }
            
    except Exception as e:
        return {
            "name": "Professional Contact",
            "current_role": "Professional",
            "current_company": "",
            "expertise": "Various",
            "industry": "",
            "key_achievements": "",
            "professional_summary": ""
        }

def extract_sender_info_from_apify_data(apify_data: dict) -> dict:
    """
    Extract structured sender information from Apify LinkedIn profile data.
    """
    sender_info = {
        "name": "Professional Contact",
        "current_role": "Professional",
        "current_company": "",
        "expertise": "",
        "industry": "",
        "key_achievements": "",
        "professional_summary": ""
    }
    
    try:
        if isinstance(apify_data, dict):
            # Extract name
            if apify_data.get('fullname'):
                sender_info['name'] = apify_data['fullname']
            elif apify_data.get('basic_info') and apify_data['basic_info'].get('fullname'):
                sender_info['name'] = apify_data['basic_info']['fullname']
            
            # Extract headline/role
            if apify_data.get('headline'):
                headline = apify_data['headline']
                sender_info['current_role'] = headline
                
                # Try to extract company from headline
                if ' at ' in headline:
                    parts = headline.split(' at ')
                    sender_info['current_role'] = parts[0].strip()
                    if len(parts) > 1:
                        sender_info['current_company'] = parts[1].strip()
            
            # Extract company from experience
            if apify_data.get('experience') and isinstance(apify_data['experience'], list):
                if len(apify_data['experience']) > 0:
                    current_exp = apify_data['experience'][0]
                    if current_exp.get('company'):
                        sender_info['current_company'] = current_exp.get('company')
                    if current_exp.get('title') and not sender_info['current_role']:
                        sender_info['current_role'] = current_exp.get('title')
            
            # Extract summary
            if apify_data.get('about'):
                sender_info['professional_summary'] = apify_data['about'][:300]
            
            # Extract expertise from skills
            if apify_data.get('skills') and isinstance(apify_data['skills'], list):
                expertise_items = []
                for skill in apify_data['skills']:
                    if isinstance(skill, dict) and skill.get('name'):
                        expertise_items.append(skill['name'])
                    elif isinstance(skill, str):
                        expertise_items.append(skill)
                
                if expertise_items:
                    sender_info['expertise'] = ", ".join(expertise_items[:5])
            
            # Determine industry from headline/summary
            industry_keywords = {
                "Technology": ["tech", "software", "AI", "machine learning", "data", "cloud", "SaaS"],
                "Finance": ["finance", "banking", "investment", "financial", "accounting"],
                "Healthcare": ["health", "medical", "pharma", "biotech", "hospital"],
                "Education": ["education", "university", "school", "learning", "academic"],
                "Consulting": ["consulting", "consultant", "advisory", "strategy"],
                "Sales": ["sales", "business development", "account executive", "revenue"]
            }
            
            profile_text = (sender_info.get('current_role', '') + ' ' + 
                          sender_info.get('professional_summary', '')).lower()
            
            for industry, keywords in industry_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in profile_text:
                        sender_info['industry'] = industry
                        break
                if sender_info['industry']:
                    break
            
            if not sender_info['expertise']:
                # Use role as expertise if no skills found
                sender_info['expertise'] = sender_info.get('current_role', 'Professional')
    
    except Exception as e:
        pass
    
    return sender_info

def analyze_and_generate_message(prospect_data: dict, sender_info: dict, api_key: str, 
                                user_instructions: str = None, previous_message: str = None) -> str:
    """
    Generate LinkedIn messages using 3-line structure with both prospect and sender analysis.
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
                prospect_info.append(f"Headline: {prospect_data['headline']}")
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
            
            prospect_summary = "\n".join(prospect_info)
            
    except Exception as e:
        prospect_summary = json.dumps(prospect_data, indent=2)[:1500]
    
    # Prepare sender context
    sender_name = sender_info.get('name', 'Professional Contact').split()[0]
    
    sender_context = f"Sender Name: {sender_info.get('name', '')}"
    if sender_info.get('current_role'):
        sender_context += f"\nSender Role: {sender_info['current_role']}"
    if sender_info.get('current_company'):
        sender_context += f"\nSender Company: {sender_info['current_company']}"
    if sender_info.get('expertise'):
        sender_context += f"\nSender Expertise: {sender_info['expertise']}"
    if sender_info.get('professional_summary'):
        sender_context += f"\nSender Summary: {sender_info['professional_summary']}"
    
    # Generate message based on mode
    if user_instructions and previous_message:
        # Refinement mode
        prompt = f'''PROSPECT INFORMATION:
{prospect_summary}

YOUR (SENDER) INFORMATION:
{sender_context}

ORIGINAL MESSAGE TO REFINE:
{previous_message}

REFINEMENT INSTRUCTIONS:
{user_instructions}

Generate a refined LinkedIn connection message with these requirements:
1. Use exactly 3 content lines
2. Line 1: Start with "Hi {prospect_name}," then mention something specific about their profile
3. Line 2: Connect your background/expertise to their field
4. Line 3: Polite connection request like "Would be glad to connect."
5. End with "Best, {sender_name}"
6. Keep under 300 characters total
7. Use professional, business-appropriate language
8. Show genuine understanding of their work
9. Avoid these words: exploring, interested, learning, no easy feat, impressive, noteworthy, remarkable, fascinating, admiring, inspiring, no small feat, no easy task, stood out

Generate only the refined message:'''
    else:
        # New generation mode
        prompt = f'''PROSPECT INFORMATION:
{prospect_summary}

YOUR (SENDER) INFORMATION:
{sender_context}

Generate a LinkedIn connection message with these requirements:
1. Use exactly 3 content lines
2. Line 1: Start with "Hi {prospect_name}," then mention something specific about their profile
3. Line 2: Connect your background/expertise to their field
4. Line 3: Polite connection request like "Would be glad to connect."
5. End with "Best, {sender_name}"
6. Keep under 300 characters total
7. Use professional, business-appropriate language
8. Show genuine understanding of their work
9. Avoid these words: exploring, interested, learning, no easy feat, impressive, noteworthy, remarkable, fascinating, admiring, inspiring, no small feat, no easy task, stood out

Generate only the message:'''
    
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
                    "content": f'''You are a professional LinkedIn message writer.
                    Rules:
                    - Use exactly 3 content lines
                    - No flirty or romantic language
                    - No informal tone
                    - No generic phrases
                    - Keep it professional and concise
                    - Always end with "Best, [First Name]"
                    - Focus on mutual professional interests
                    - Show understanding of their specific work'''
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
                message = f"Hi {prospect_name},\n{message}"
            
            # Ensure proper signature
            if not message.strip().endswith(f"Best, {sender_name}"):
                message = f"{message.rstrip()}\nBest, {sender_name}"
            
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
                    Remove all romantic/flirty language.
                    Keep strictly professional.
                    Profile: {prospect_summary[:300]}
                    Your info: {sender_context[:300]}'''
                    
                    strict_payload = {
                        "model": "llama-3.1-8b-instant",
                        "messages": [
                            {"role": "system", "content": "Strictly professional only. No flirty language."},
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
            
            return message
            
        else:
            # Safe fallback
            return f"Hi {prospect_name},\nYour professional background in your field shows expertise.\nI focus on improvements in similar areas.\nWould be glad to connect.\nBest, {sender_name}"
            
    except Exception as e:
        # Professional fallback
        return f"Hi {prospect_name},\nYour experience in your industry demonstrates professional depth.\nI work on business improvements in related fields.\nWould be good to connect.\nBest, {sender_name}"

# ========== STREAMLIT APPLICATION ==========

st.set_page_config(
    page_title="Linzy | AI Prospect Intelligence",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Modern CSS ---
modern_css = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');
    
    .stApp {
        background: linear-gradient(135deg, #0a192f 0%, #1a1a2e 50%, #16213e 100%);
        font-family: 'Space Grotesk', sans-serif;
        min-height: 100vh;
    }
    
    .main-container {
        background: linear-gradient(145deg, rgba(255, 255, 255, 0.05), rgba(255, 255, 255, 0.02));
        backdrop-filter: blur(20px);
        border-radius: 32px;
        padding: 40px;
        margin: 20px;
        border: 1px solid rgba(0, 180, 216, 0.1);
        box-shadow: 0 50px 100px rgba(0, 180, 216, 0.1),
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
        box-shadow: inset 0 2px 4px rgba(0, 0, 0, 0.1),
            0 4px 20px rgba(0, 180, 216, 0.1);
    }
    
    .input-3d:focus {
        background: rgba(255, 255, 255, 0.05);
        border-color: #00b4d8;
        box-shadow: 0 0 0 4px rgba(0, 180, 216, 0.15),
            inset 0 2px 8px rgba(0, 180, 216, 0.1);
        outline: none;
    }
    
    .card-3d {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 24px;
        padding: 25px;
        margin: 15px 0;
        border: 1px solid rgba(0, 180, 216, 0.1);
        transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
        backdrop-filter: blur(10px);
        box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
    
    .card-3d:hover {
        transform: translateY(-5px);
        border-color: rgba(0, 180, 216, 0.3);
        box-shadow: 0 30px 80px rgba(0, 180, 216, 0.15),
            inset 0 1px 0 rgba(255, 255, 255, 0.15);
    }
    
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
        box-shadow: 0 8px 25px rgba(0, 180, 216, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.2);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 35px rgba(0, 180, 216, 0.4),
            inset 0 1px 0 rgba(255, 255, 255, 0.3);
    }
    
    .stButton > button:active {
        transform: translateY(0);
        box-shadow: 0 5px 20px rgba(0, 180, 216, 0.3),
            inset 0 1px 0 rgba(255, 255, 255, 0.1);
    }
    
    .tab-button {
        background: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(0, 180, 216, 0.2);
        color: #8892b0;
        padding: 10px 20px;
        border-radius: 10px;
        cursor: pointer;
        transition: all 0.3s ease;
    }
    
    .tab-button:hover {
        background: rgba(0, 180, 216, 0.1);
        color: #e6f7ff;
    }
    
    .tab-button.active {
        background: linear-gradient(135deg, #00b4d8, #0077b6);
        color: white;
        border-color: #00b4d8;
    }
    
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

<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
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
if 'sender_info' not in st.session_state:
    st.session_state.sender_info = None
if 'sender_data' not in st.session_state:
    st.session_state.sender_data = None
if 'message_instructions' not in st.session_state:
    st.session_state.message_instructions = ""
if 'regenerate_mode' not in st.session_state:
    st.session_state.regenerate_mode = False
if 'sender_tab' not in st.session_state:
    st.session_state.sender_tab = "linkedin"
if 'sender_manual_text' not in st.session_state:
    st.session_state.sender_manual_text = ""
if 'sender_analyzing' not in st.session_state:
    st.session_state.sender_analyzing = False

# --- Main Container ---
# st.markdown('<div class="main-container">', unsafe_allow_html=True)

# --- Header Section ---
col1, col2 = st.columns([4, 1])
with col1:
    st.markdown('<h1 class="gradient-text-primary" style="font-size: 3.5rem; margin-bottom: 10px;">LINZY</h1>', unsafe_allow_html=True)
    st.markdown('<p style="color: #8892b0; font-size: 1.2rem; margin-bottom: 40px;">AI Powered LinkedIn Message Generator</p>', unsafe_allow_html=True)
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
            <div>Sender: {sender_name}</div>
            <div>Messages: {len(st.session_state.generated_messages)}</div>
            <div>{datetime.now().strftime("%H:%M:%S")}</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

# --- Message Structure Guide ---
# st.markdown("---")
# st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 20px;">Message Structure</h3>', unsafe_allow_html=True)

# st.markdown('''
# <div class="card-3d">
#     <div style="color: #e6f7ff; margin-bottom: 15px;">
#         <div style="display: flex; align-items: center; margin: 10px 0;">
#             <div style="width: 30px; height: 30px; background: linear-gradient(135deg, #00b4d8, #0077b6); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 600; margin-right: 15px; box-shadow: 0 4px 15px rgba(0, 180, 216, 0.3);">1</div>
#             <div>
#                 <strong style="color: #00ffd0;">About the Prospect</strong>
#                 <div style="color: #8892b0; font-size: 0.9rem;">Specific mention of their role, achievement, or background</div>
#             </div>
#         </div>
#         <div style="display: flex; align-items: center; margin: 10px 0;">
#             <div style="width: 30px; height: 30px; background: linear-gradient(135deg, #00b4d8, #0077b6); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 600; margin-right: 15px; box-shadow: 0 4px 15px rgba(0, 180, 216, 0.3);">2</div>
#             <div>
#                 <strong style="color: #00b4d8;">Your Value/Intention</strong>
#                 <div style="color: #8892b0; font-size: 0.9rem;">How your expertise relates to their field</div>
#             </div>
#         </div>
#         <div style="display: flex; align-items: center; margin: 10px 0;">
#             <div style="width: 30px; height: 30px; background: linear-gradient(135deg, #00b4d8, #0077b6); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 600; margin-right: 15px; box-shadow: 0 4px 15px rgba(0, 180, 216, 0.3);">3</div>
#             <div>
#                 <strong style="color: #c8b6ff;">Connection Request</strong>
#                 <div style="color: #8892b0; font-size: 0.9rem;">Polite request to connect professionally</div>
#             </div>
#         </div>
#     </div>
# </div>
# ''', unsafe_allow_html=True)

# --- Sender Configuration Section ---
st.markdown("---")
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;">Your Information</h3>', unsafe_allow_html=True)

# Tab selection for sender input method
col_tab1, col_tab2 = st.columns(2)
with col_tab1:
    linkedin_active = st.button(
        "LinkedIn URL Analysis",
        key="tab_linkedin",
        use_container_width=True
    )
with col_tab2:
    manual_active = st.button(
        "Manual Profile Entry",
        key="tab_manual",
        use_container_width=True
    )

if linkedin_active:
    st.session_state.sender_tab = "linkedin"
    st.rerun()
if manual_active:
    st.session_state.sender_tab = "manual"
    st.rerun()

# Tab content
if st.session_state.sender_tab == "linkedin":
    st.markdown('<p style="color: #8892b0; margin-bottom: 15px;">Paste your LinkedIn URL to automatically analyze your profile</p>', unsafe_allow_html=True)
    
    sender_linkedin_url = st.text_input(
        "LinkedIn Profile URL",
        placeholder="https://linkedin.com/in/yourprofile",
        key="sender_linkedin_url"
    )
    
    col_analyze, col_clear = st.columns([2, 1])
    
    with col_analyze:
        analyze_sender_clicked = st.button(
            "Analyze LinkedIn Profile",
            use_container_width=True,
            key="analyze_sender_url",
            disabled=not sender_linkedin_url
        )
    
    with col_clear:
        if st.button(
            "Clear Profile",
            use_container_width=True,
            key="clear_sender_url",
            type="secondary"
        ):
            st.session_state.sender_info = None
            st.session_state.sender_data = None
            st.rerun()
    
    if analyze_sender_clicked and sender_linkedin_url:
        if not apify_api_key:
            st.error("API key configuration required.")
        else:
            st.session_state.sender_analyzing = True
            with st.spinner("Analyzing your LinkedIn profile..."):
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
                        # Extract structured info from Apify data
                        st.session_state.sender_info = extract_sender_info_from_apify_data(sender_data)
                        st.success("Profile analyzed successfully")
                        st.session_state.sender_analyzing = False
                    else:
                        st.error("Failed to analyze your LinkedIn profile. Please check the URL or try manual entry.")
                        st.session_state.sender_analyzing = False
                else:
                    st.error("Could not start profile analysis. Please try again.")
                    st.session_state.sender_analyzing = False

else:  # Manual tab
    st.markdown('<p style="color: #8892b0; margin-bottom: 15px;">Paste or type your profile information manually</p>', unsafe_allow_html=True)
    
    st.session_state.sender_manual_text = st.text_area(
        "Your Profile Information",
        value=st.session_state.sender_manual_text,
        placeholder="""Example:
John Smith
Senior Software Engineer at TechCorp
10+ years experience in AI and machine learning
Specialized in natural language processing
Led team that developed award-winning chatbot
Passionate about AI ethics and responsible innovation""",
        height=200,
        key="sender_manual_input"
    )
    
    col_analyze_manual, col_clear_manual = st.columns([2, 1])
    
    with col_analyze_manual:
        analyze_manual_clicked = st.button(
            "Analyze Profile Text",
            use_container_width=True,
            key="analyze_sender_manual",
            disabled=not st.session_state.sender_manual_text
        )
    
    with col_clear_manual:
        if st.button(
            "Clear Profile",
            use_container_width=True,
            key="clear_sender_manual",
            type="secondary"
        ):
            st.session_state.sender_info = None
            st.session_state.sender_manual_text = ""
            st.rerun()
    
    if analyze_manual_clicked and st.session_state.sender_manual_text:
        st.session_state.sender_analyzing = True
        with st.spinner("Analyzing your profile information..."):
            st.session_state.sender_info = analyze_sender_profile_with_llm(
                st.session_state.sender_manual_text, 
                groq_api_key
            )
            st.success("Profile analyzed successfully")
            st.session_state.sender_analyzing = False

# Display current sender info if available
if st.session_state.sender_info and not st.session_state.sender_analyzing:
    with st.expander("Current Profile Information", expanded=False):
        info = st.session_state.sender_info
        st.markdown(f"""
        <div class="card-3d">
            <div style="color: #e6f7ff;">
                <div style="margin-bottom: 10px;"><strong>Name:</strong> {info.get('name', 'N/A')}</div>
                <div style="margin-bottom: 10px;"><strong>Current Role:</strong> {info.get('current_role', 'N/A')}</div>
                <div style="margin-bottom: 10px;"><strong>Company:</strong> {info.get('current_company', 'N/A')}</div>
                <div style="margin-bottom: 10px;"><strong>Expertise:</strong> {info.get('expertise', 'N/A')}</div>
                <div style="margin-bottom: 10px;"><strong>Industry:</strong> {info.get('industry', 'N/A')}</div>
                <div><strong>Summary:</strong> {info.get('professional_summary', 'N/A')[:200]}...</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

# --- Prospect Analysis Section ---
st.markdown("---")
st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 20px;">Prospect Analysis</h3>', unsafe_allow_html=True)

prospect_col1, prospect_col2 = st.columns([3, 1])

with prospect_col1:
    prospect_linkedin_url = st.text_input(
        "Prospect LinkedIn Profile URL",
        placeholder="https://linkedin.com/in/prospectprofile",
        key="prospect_url"
    )

with prospect_col2:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    analyze_prospect_clicked = st.button(
        "Analyze Prospect",
        use_container_width=True,
        key="analyze_prospect",
        disabled=not st.session_state.sender_info or not prospect_linkedin_url
    )

if not st.session_state.sender_info:
    st.warning("Please set up your profile information first to generate personalized messages.")

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
                
                st.success("Prospect analysis complete")
                
                st.session_state.generated_messages = []
                st.session_state.current_message_index = -1
            else:
                st.session_state.processing_status = "Error"
                st.error("Failed to analyze prospect profile.")

# --- Results Display ---
if st.session_state.profile_data and st.session_state.research_brief and st.session_state.sender_info:
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs([
        "Message Generation", 
        "Research Brief", 
        "Profile Data"
    ])
    
    with tab1:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;">Generate Message</h3>', unsafe_allow_html=True)
        
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
                        st.session_state.sender_info,
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
            
            st.markdown(f'''
<div class="message-structure">
    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 20px;">
        <div>
            <h4 style="color: #e6f7ff; margin: 0;">Generated Message</h4>
            <p style="color: #8892b0; font-size: 0.9rem; margin: 5px 0 0 0;">
                {len(current_msg)} characters • Version {st.session_state.current_message_index + 1}
            </p>
        </div>
        <div style="background: linear-gradient(135deg, rgba(0, 180, 216, 0.1), rgba(0, 255, 208, 0.1)); padding: 8px 16px; border-radius: 12px;">
            <span style="color: #00ffd0; font-weight: 600;">3-Line Structure</span>
        </div>
    </div>
    <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 16px; border: 1px solid rgba(0, 180, 216, 0.1); margin: 20px 0;">
        <pre style="white-space: pre-wrap; font-family: 'Inter', sans-serif; line-height: 1.8; margin: 0; color: #e6f7ff; font-size: 1.05rem; word-wrap: break-word; overflow-wrap: break-word;">
{current_msg}
        </pre>
    </div>
</div>
''', unsafe_allow_html=True)
            
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
                st.markdown('<h4 style="color: #e6f7ff;">Refine Message</h4>', unsafe_allow_html=True)
                
                with st.form("refinement_form"):
                    instructions = st.text_area(
                        "How would you like to improve this message?",
                        value=st.session_state.message_instructions,
                        placeholder="Example: Make line 2 more technical, Shorten line 1, Focus on AI experience in line 2",
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
                                st.session_state.sender_info,
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
                st.markdown('<h4 style="color: #e6f7ff; margin-bottom: 20px;">Message History</h4>', unsafe_allow_html=True)
                
                for idx, msg in enumerate(st.session_state.generated_messages):
                    is_active = idx == st.session_state.current_message_index
                    border_color = "#00b4d8" if is_active else "rgba(0, 180, 216, 0.2)"
                    bg_color = "rgba(0, 180, 216, 0.05)" if is_active else "rgba(255, 255, 255, 0.02)"
                    
                    lines = msg.split('\n')
                    preview = lines[1] if len(lines) > 1 else msg[:80]
                    
                    st.markdown(f'''
                    <div style="
                        background: {bg_color};
                        padding: 18px;
                        border-radius: 16px;
                        margin: 10px 0;
                        border: 1px solid {border_color};
                        cursor: pointer;"
                        onclick="window.location.href='?select={idx}'">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <div style="display: flex; align-items: center;">
                                <span style="color: #e6f7ff; font-weight: 600; margin-right: 15px;">
                                    Version {idx + 1}
                                </span>
                                <span style="color: #8892b0; font-size: 0.85rem;">
                                    {len(msg)} characters
                                </span>
                            </div>
                            {f'<span style="color: #00ffd0; font-weight: 600; font-size: 0.9rem;">Active</span>' if is_active else ''}
                        </div>
                        <div style="color: #a8c1d1; font-size: 0.9rem; line-height: 1.5;">
                            {preview[:90]}...
                        </div>
                    </div>
                    ''', unsafe_allow_html=True)

        
        else:
            st.markdown('''
            <div class="card-3d" style="text-align: center; padding: 60px 30px;">
                <h4 style="color: #e6f7ff; margin-bottom: 15px;">Generate Your First Message</h4>
                <p style="color: #8892b0; max-width: 400px; margin: 0 auto;">
                    Click Generate AI Message to create a 3-line personalized message using your profile and the prospect information.
                </p>
            </div>
            ''', unsafe_allow_html=True)
    
    with tab2:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;">Research Brief</h3>', unsafe_allow_html=True)
        st.markdown('<div class="card-3d">', unsafe_allow_html=True)
        st.markdown(st.session_state.research_brief)
        st.markdown('</div>', unsafe_allow_html=True)
    
    with tab3:
        st.markdown('<h3 style="color: #e6f7ff; margin-bottom: 25px;">Profile Data</h3>', unsafe_allow_html=True)
        with st.expander("View Prospect Data", expanded=False):
            st.json(st.session_state.profile_data)
        
        with st.expander("View Your Profile Data", expanded=False):
            if st.session_state.sender_data:
                st.json(st.session_state.sender_data)
            else:
                st.json(st.session_state.sender_info)

else:
    if not st.session_state.sender_info:
        st.markdown('''
        <div style="text-align: center; padding: 80px 20px;">
            <div style="position: relative; display: inline-block; margin-bottom: 40px;">
                <div style="width: 120px; height: 120px; background: linear-gradient(135deg, #00b4d8, #00ffd0); border-radius: 30px; transform: rotate(45deg); margin: 0 auto 40px; position: relative; box-shadow: 0 20px 60px rgba(0, 180, 216, 0.4);">
                </div>
            </div>
            <h2 style="color: #e6f7ff; margin-bottom: 20px; font-size: 2.5rem;">Get Started with LINZY</h2>
            <p style="color: #8892b0; max-width: 600px; margin: 0 auto 50px; line-height: 1.8; font-size: 1.1rem;">
                To generate personalized LinkedIn messages, please start by setting up your profile information above.
            </p>
            <div style="display: flex; justify-content: center; gap: 30px; flex-wrap: wrap;">
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <h4 style="color: #e6f7ff; margin-bottom: 10px;">1. Your Profile</h4>
                    <p style="color: #8892b0; font-size: 0.9rem;">Analyze your LinkedIn profile or enter manually</p>
                </div>
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <h4 style="color: #e6f7ff; margin-bottom: 10px;">2. Prospect Profile</h4>
                    <p style="color: #8892b0; font-size: 0.9rem;">Analyze the prospect LinkedIn profile</p>
                </div>
                <div style="background: rgba(255, 255, 255, 0.03); padding: 25px; border-radius: 20px; width: 200px; border: 1px solid rgba(0, 180, 216, 0.1);">
                    <h4 style="color: #e6f7ff; margin-bottom: 10px;">3. Generate</h4>
                    <p style="color: #8892b0; font-size: 0.9rem;">AI creates personalized 3-line messages</p>
                </div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
    else:
        st.info("Enter a prospect LinkedIn URL above and click Analyze Prospect to get started.")

st.markdown('</div>', unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown('<p style="color: #8892b0; font-size: 0.9rem;">Linzy v2.4 | AI LinkedIn Messaging</p>', unsafe_allow_html=True)
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

# JavaScript for interactivity
st.markdown("""
<script>
document.addEventListener('DOMContentLoaded', function() {
    const inputs = document.querySelectorAll('input[type="text"], textarea');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            this.parentElement.style.transform = 'translateY(-3px)';
        });
        
        input.addEventListener('blur', function() {
            this.parentElement.style.transform = 'translateY(0)';
        });
    });
    
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
