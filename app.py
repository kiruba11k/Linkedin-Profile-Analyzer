import streamlit as st
import requests
import json
from datetime import datetime
import time

# --- API Functions (DEFINED FIRST) ---
def fetch_apify_data(profile_url: str, api_key: str) -> dict:
    """
    Fetch LinkedIn profile data dynamically using Apify API
    Returns whatever structure the actor provides
    """
    try:
        # Using the apimaestro~linkedin-profile-detail actor
        actor_id = "apimaestro~linkedin-profile-detail"
        endpoint = f"https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Dynamic payload - adapts based on URL
        payload = {
            "profileUrls": [profile_url],
            "timeout": 60000,
            "maxProfiles": 1
        }
        
        # Try different payload structures if needed
        alt_payloads = [
            payload,
            {"url": profile_url, "maxResults": 1},
            {"input": {"url": profile_url}}
        ]
        
        for attempt, current_payload in enumerate(alt_payloads):
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=current_payload,
                    timeout=120
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Handle various response formats dynamically
                    if isinstance(data, list) and len(data) > 0:
                        return data[0] if isinstance(data[0], dict) else data
                    elif isinstance(data, dict):
                        if 'data' in data:
                            return data['data']
                        elif 'items' in data:
                            return data['items'][0] if isinstance(data['items'], list) else data['items']
                        elif 'result' in data:
                            return data['result']
                        return data
                    return data
                
            except Exception as e:
                if attempt == len(alt_payloads) - 1:
                    raise e
                continue
        
        # If we get here, try async method
        return try_async_fallback(profile_url, api_key, actor_id)
        
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None

def try_async_fallback(profile_url: str, api_key: str, actor_id: str) -> dict:
    """
    Try asynchronous method as fallback
    """
    try:
        endpoint = f"https://api.apify.com/v2/acts/{actor_id}/runs"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload_variations = [
            {"profileUrls": [profile_url]},
            {"url": profile_url},
            {"startUrls": [{"url": profile_url}]}
        ]
        
        for payload in payload_variations:
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code in [200, 201]:
                    run_data = response.json()
                    run_id = run_data.get('data', {}).get('id') or run_data.get('id')
                    
                    if run_id:
                        # Poll for results
                        return poll_for_run_result(api_key, run_id)
                        
            except:
                continue
        
        return None
        
    except Exception:
        return None

def poll_for_run_result(api_key: str, run_id: str) -> dict:
    """
    Poll for run results dynamically
    """
    try:
        for i in range(20):  # Poll for 40 seconds max
            time.sleep(2)
            
            status_endpoint = f"https://api.apify.com/v2/actor-runs/{run_id}"
            headers = {"Authorization": f"Bearer {api_key}"}
            
            status_response = requests.get(status_endpoint, headers=headers, timeout=10)
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                status = status_data.get("data", {}).get("status") or status_data.get("status")
                
                if status == "SUCCEEDED":
                    # Get output - try different possible output locations
                    dataset_id = status_data.get("data", {}).get("defaultDatasetId")
                    
                    if dataset_id:
                        dataset_endpoint = f"https://api.apify.com/v2/datasets/{dataset_id}/items"
                        dataset_response = requests.get(dataset_endpoint, headers=headers, timeout=10)
                        
                        if dataset_response.status_code == 200:
                            items = dataset_response.json()
                            if items and len(items) > 0:
                                return items[0] if isinstance(items, list) else items
                
                elif status in ["FAILED", "TIMED-OUT", "ABORTED"]:
                    return None
            
        return None
        
    except Exception:
        return None

def generate_research_brief(profile_data: dict, api_key: str, mode: str) -> str:
    """
    Generate research brief using Groq LLM with dynamic data handling
    """
    try:
        # Let LLM analyze whatever structure we get
        prompt = f"""
        Analyze this LinkedIn profile data and create a concise research brief for sales prospecting.
        
        PROFILE DATA (raw JSON structure):
        {json.dumps(profile_data, indent=2)}
        
        ANALYSIS MODE: {mode}
        
        INSTRUCTIONS:
        1. Extract key information dynamically from whatever fields exist in the data
        2. Focus on factual information: current role, experience, skills, projects
        3. Identify potential business needs based on role and industry context
        4. Suggest personalized outreach opportunities
        5. Keep it professional, concise, and actionable
        
        Format the brief with clear sections.
        Do not mention any words like "impressive", "remarkable", "admiring", etc.
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
                    "content": "You are a research analyst. Analyze whatever data structure you receive. Extract insights dynamically. Never use flattery words."
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
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
            return dynamic_fallback_analysis(profile_data)
            
    except Exception:
        return dynamic_fallback_analysis(profile_data)

def dynamic_fallback_analysis(profile_data: dict) -> str:
    """
    Generate analysis based on whatever data exists
    """
    # Extract whatever fields might exist
    analysis_lines = []
    
    # Try to find name
    name_candidates = [
        profile_data.get('fullname'),
        profile_data.get('name'),
        profile_data.get('basic_info', {}).get('fullname'),
        profile_data.get('personal_info', {}).get('name'),
        str(profile_data)[:100]  # Last resort
    ]
    name = next((n for n in name_candidates if n and isinstance(n, str)), "Unknown Profile")
    
    # Try to find current role
    role_candidates = []
    if 'experience' in profile_data and isinstance(profile_data['experience'], list):
        for exp in profile_data['experience']:
            if isinstance(exp, dict):
                if exp.get('is_current') or exp.get('current'):
                    role_candidates.append(f"{exp.get('title', 'Role')} at {exp.get('company', 'Company')}")
                elif exp.get('title'):
                    role_candidates.append(exp.get('title'))
    
    current_role = role_candidates[0] if role_candidates else "Unknown Role"
    
    analysis_lines.append(f"PROFILE: {name}")
    analysis_lines.append(f"OBSERVED ROLE: {current_role}")
    analysis_lines.append("")
    analysis_lines.append("DATA FIELDS DETECTED:")
    
    # List top-level fields for transparency
    fields = list(profile_data.keys())[:10]
    for field in fields:
        field_type = type(profile_data[field]).__name__
        analysis_lines.append(f"- {field} ({field_type})")
    
    analysis_lines.append("")
    analysis_lines.append("SUGGESTED APPROACH:")
    analysis_lines.append("- Reference the specific data fields available")
    analysis_lines.append("- Focus on professional context, not personal details")
    analysis_lines.append("- Keep outreach factual and direct")
    
    return "\n".join(analysis_lines)

def generate_first_level_message(profile_data: dict, api_key: str, tone: str) -> str:
    """
    Generate first-level LinkedIn message dynamically
    """
    try:
        prompt = f"""
        Create a first-level LinkedIn connection request message based on this profile data.
        
        RAW PROFILE DATA:
        {json.dumps(profile_data, indent=2)}
        
        CRITICAL REQUIREMENTS:
        1. UNDER 250 characters total
        2. Focus on EXACT content from their profile (specific projects, technologies, roles)
        3. Tone: {tone}
        4. ABSOLUTELY FORBIDDEN WORDS: exploring, interested, learning, no easy feat, impressive, noteworthy, remarkable, fascinating, admiring, inspiring, no small feat, no easy task, stood out
        5. NO FLATTERY - only factual observations
        6. Must reference something SPECIFIC found in the data
        
        EXAMPLE FORMAT (adapt based on available data):
        "Noticed your work on [specific project/tech]. [Factual observation about it]. Would connect to discuss [related topic]."
        
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
                    "content": "You create direct LinkedIn messages. Extract specific content from whatever data you receive. NEVER use forbidden words. ALWAYS reference something specific found in the data."
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
            
            # Clean message
            message = message.replace('"', '').replace('\n', ' ')
            if len(message) > 250:
                message = message[:247] + '...'
            
            return message
        else:
            return generate_dynamic_fallback_message(profile_data)
            
    except Exception:
        return generate_dynamic_fallback_message(profile_data)

def generate_dynamic_fallback_message(profile_data: dict) -> str:
    """
    Generate fallback message based on whatever data exists
    """
    # Extract any identifiable content
    content_snippets = []
    
    # Look for project names
    if 'projects' in profile_data and isinstance(profile_data['projects'], list):
        for proj in profile_data['projects'][:2]:
            if isinstance(proj, dict) and 'name' in proj:
                content_snippets.append(f"your {proj['name']} project")
    
    # Look for current role
    if 'experience' in profile_data and isinstance(profile_data['experience'], list):
        for exp in profile_data['experience']:
            if isinstance(exp, dict):
                if exp.get('is_current') and exp.get('title'):
                    content_snippets.append(f"your role as {exp['title']}")
                elif exp.get('title'):
                    content_snippets.append(f"your {exp['title']} experience")
    
    # Look for skills/technologies
    if 'skills' in profile_data and isinstance(profile_data['skills'], list):
        for skill in profile_data['skills'][:3]:
            if isinstance(skill, str):
                content_snippets.append(f"{skill} work")
            elif isinstance(skill, dict) and 'name' in skill:
                content_snippets.append(f"{skill['name']} work")
    
    # Generate message based on found content
    if content_snippets:
        focus = content_snippets[0]
        return f"Saw your profile regarding {focus}. Would connect to discuss related areas."
    else:
        # Last resort generic but professional message
        return "Would connect to discuss professional work."

# --- Page Configuration ---
st.set_page_config(
    page_title="DYNAMIC PROSPECT RESEARCH",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Dynamic CSS for Retro UI ---
dynamic_css = """
<style>
    .stApp {
        background: #000000;
        color: #00ff00;
        font-family: 'Courier New', monospace;
        font-size: 14px;
    }
    
    @keyframes dataStream {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    .dynamic-header {
        background: linear-gradient(90deg, #000, #00ff00, #000, #ff00ff, #000);
        background-size: 400% 400%;
        animation: dataStream 10s ease infinite;
        color: #fff;
        padding: 20px;
        text-align: center;
        text-transform: uppercase;
        letter-spacing: 3px;
        font-weight: bold;
        border-bottom: 2px solid #00ff00;
    }
    
    .scan-line {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 2px;
        background: linear-gradient(90deg, transparent, #00ff00, #ff00ff, #00ff00, transparent);
        animation: scan 6s linear infinite;
        pointer-events: none;
        z-index: 9999;
    }
    
    @keyframes scan {
        0% { transform: translateY(-100%); }
        100% { transform: translateY(100vh); }
    }
    
    .dynamic-box {
        background: rgba(0, 30, 0, 0.2);
        border: 1px solid #00ff00;
        margin: 15px 0;
        padding: 20px;
        position: relative;
        overflow: hidden;
    }
    
    .dynamic-box::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: linear-gradient(45deg, transparent, rgba(0, 255, 0, 0.1), transparent);
        animation: shimmer 3s infinite linear;
        pointer-events: none;
    }
    
    @keyframes shimmer {
        0% { transform: translateX(-100%) translateY(-100%) rotate(0deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(360deg); }
    }
    
    .dynamic-input {
        background: #001a00;
        color: #00ff00;
        border: 1px solid #008800;
        border-radius: 0;
        font-family: 'Courier New', monospace;
        padding: 10px;
        width: 100%;
        transition: all 0.3s;
    }
    
    .dynamic-input:focus {
        outline: none;
        border-color: #00ff00;
        box-shadow: 0 0 15px rgba(0, 255, 0, 0.5);
        background: #002200;
    }
    
    .dynamic-button {
        background: #002200;
        color: #00ff00;
        border: 1px solid #00ff00;
        padding: 12px 24px;
        font-family: 'Courier New', monospace;
        font-weight: bold;
        text-transform: uppercase;
        letter-spacing: 1px;
        cursor: pointer;
        transition: all 0.3s;
        position: relative;
        overflow: hidden;
    }
    
    .dynamic-button:hover {
        background: #00ff00;
        color: #000;
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0, 255, 0, 0.3);
    }
    
    .dynamic-button::after {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 5px;
        height: 5px;
        background: rgba(255, 255, 255, 0.5);
        opacity: 0;
        border-radius: 100%;
        transform: scale(1, 1) translate(-50%);
        transform-origin: 50% 50%;
    }
    
    .dynamic-button:focus:not(:active)::after {
        animation: ripple 1s ease-out;
    }
    
    @keyframes ripple {
        0% { transform: scale(0, 0); opacity: 0.5; }
        100% { transform: scale(20, 20); opacity: 0; }
    }
    
    .message-history-item {
        background: #001100;
        border: 1px solid #004400;
        margin: 8px 0;
        padding: 12px;
        transition: all 0.3s;
        cursor: pointer;
    }
    
    .message-history-item:hover {
        border-color: #00ff00;
        background: #002200;
    }
    
    .message-history-item.active {
        border-left: 4px solid #00ff00;
        background: #003300;
    }
    
    .data-preview {
        font-size: 12px;
        color: #008800;
        font-family: 'Consolas', monospace;
        max-height: 300px;
        overflow-y: auto;
        padding: 10px;
        background: rgba(0, 20, 0, 0.3);
        border: 1px solid #004400;
    }
    
    .status-dot {
        display: inline-block;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        margin-right: 8px;
    }
    
    .status-dot.ready { background: #00ff00; box-shadow: 0 0 10px #00ff00; }
    .status-dot.processing { background: #ffff00; box-shadow: 0 0 10px #ffff00; animation: pulse 1s infinite; }
    .status-dot.error { background: #ff0000; box-shadow: 0 0 10px #ff0000; }
    
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
</style>
<div class="scan-line"></div>
"""

st.markdown(dynamic_css, unsafe_allow_html=True)

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
if 'data_structure' not in st.session_state:
    st.session_state.data_structure = None

# --- Dynamic Header ---
st.markdown("""
<div class="dynamic-header">
    <div style="font-size: 24px; margin-bottom: 10px;">DYNAMIC PROSPECT RESEARCH</div>
    <div style="font-size: 12px; color: #88ff88;">ADAPTS TO ANY DATA STRUCTURE • NO STATIC VALUES • AI-DRIVEN ANALYSIS</div>
</div>
""", unsafe_allow_html=True)

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("### SYSTEM CONFIGURATION")
    
    # API Configuration with dynamic validation
    apify_api_key = st.secrets.get("APIFY")
    
    groq_api_key = st.secrets.get("GROQ")
    
    st.markdown("---")
    
    # Dynamic settings
    analysis_mode = st.selectbox(
        "ANALYSIS APPROACH",
        ["AUTOMATIC", "TECHNICAL FOCUS", "BUSINESS CONTEXT", "CAREER PROGRESSION"],
        index=0,
        help="LLM will adapt analysis based on selected focus"
    )
    
    message_style = st.selectbox(
        "MESSAGE STYLE",
        ["DIRECT REFERENCE", "PROJECT-FOCUSED", "ROLE-SPECIFIC", "TECHNICAL"],
        index=0,
        help="Style adapts based on available data"
    )
    
    st.markdown("---")
    
    # Dynamic status display
    status_text = st.session_state.processing_status
    status_class = {
        "READY": "ready",
        "PROCESSING": "processing", 
        "FETCHING": "processing",
        "ANALYZING": "processing",
        "ERROR": "error",
        "COMPLETE": "ready"
    }.get(status_text, "ready")
    
    st.markdown("### SYSTEM STATUS")
    st.markdown(f"""
    <div style="background: #001100; padding: 15px; border: 1px solid #004400;">
        <div style="display: flex; align-items: center; margin-bottom: 10px;">
            <span class="status-dot {status_class}"></span>
            <strong>{status_text}</strong>
        </div>
        <div>Data Fields: {len(st.session_state.data_structure or {})}</div>
        <div>Messages: {len(st.session_state.generated_messages)}</div>
        <div>Last Update: {datetime.now().strftime('%H:%M:%S')}</div>
    </div>
    """, unsafe_allow_html=True)

# --- Main Input Area ---
st.markdown("<div class='dynamic-box'>", unsafe_allow_html=True)
col1, col2 = st.columns([3, 1])

with col1:
    linkedin_url = st.text_input(
        "LINKEDIN PROFILE URL",
        placeholder="https://linkedin.com/in/username",
        label_visibility="collapsed",
        key="profile_url_input"
    )

with col2:
    st.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
    analyze_clicked = st.button(
        "INITIATE ANALYSIS",
        use_container_width=True,
        type="primary"
    )

st.markdown("</div>", unsafe_allow_html=True)

# --- Processing Logic ---
if analyze_clicked and linkedin_url:
    if not apify_api_key or not groq_api_key:
        st.error("API KEYS REQUIRED")
    else:
        st.session_state.processing_status = "FETCHING"
        
        # Fetch data from Apify
        with st.spinner("CONNECTING TO APIFY..."):
            profile_data = fetch_apify_data(linkedin_url, apify_api_key)
            
            if profile_data:
                st.session_state.profile_data = profile_data
                st.session_state.data_structure = {
                    k: type(v).__name__ 
                    for k, v in profile_data.items() 
                    if isinstance(v, (str, int, float, list, dict, bool))
                }
                st.session_state.processing_status = "ANALYZING"
                
                # Generate research brief
                with st.spinner("ANALYZING WITH LLM..."):
                    research_brief = generate_research_brief(
                        profile_data, 
                        groq_api_key, 
                        analysis_mode
                    )
                    st.session_state.research_brief = research_brief
                    st.session_state.processing_status = "COMPLETE"
                    st.success("ANALYSIS COMPLETE • DATA STRUCTURE ADAPTED")
            else:
                st.session_state.processing_status = "ERROR"
                st.error("NO DATA RECEIVED • CHECK URL AND API KEY")

# --- Display Results ---
if st.session_state.profile_data and st.session_state.research_brief:
    st.markdown("---")
    
    # Create dynamic tabs
    tab1, tab2, tab3 = st.tabs(["ANALYSIS RESULTS", "MESSAGES", "RAW DATA"])
    
    with tab1:
        st.markdown("<div class='dynamic-box'>", unsafe_allow_html=True)
        st.markdown(f"**RESEARCH BRIEF • {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
        st.markdown("---")
        st.markdown(st.session_state.research_brief)
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Message generation button
        col_msg1, col_msg2 = st.columns([3, 1])
        with col_msg2:
            if st.button("GENERATE MESSAGE", use_container_width=True):
                new_message = generate_first_level_message(
                    st.session_state.profile_data,
                    groq_api_key,
                    message_style
                )
                if new_message:
                    st.session_state.generated_messages.append(new_message)
                    st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                    st.rerun()
    
    with tab2:
        if len(st.session_state.generated_messages) > 0:
            # Current message display
            current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
            
            st.markdown("<div class='dynamic-box'>", unsafe_allow_html=True)
            st.markdown(f"**MESSAGE {st.session_state.current_message_index + 1} OF {len(st.session_state.generated_messages)}**")
            st.markdown(f"*{len(current_msg)} characters*")
            st.markdown("---")
            st.markdown(f"```\n{current_msg}\n```")
            st.markdown("</div>", unsafe_allow_html=True)
            
            # Copy functionality
            st.code(current_msg, language=None)
            
            # Navigation controls
            if len(st.session_state.generated_messages) > 1:
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
            
            # Message history
            st.markdown("### MESSAGE HISTORY")
            for idx, msg in enumerate(st.session_state.generated_messages):
                is_active = idx == st.session_state.current_message_index
                active_class = "active" if is_active else ""
                st.markdown(f"""
                <div class="message-history-item {active_class}" onclick="this.dispatchEvent(new CustomEvent('msg-click', {{detail: {idx}}}))">
                    <small>#{idx + 1} • {len(msg)} chars</small><br>
                    {msg[:100]}...
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("NO MESSAGES GENERATED • CLICK 'GENERATE MESSAGE' IN ANALYSIS TAB")
    
    with tab3:
        st.markdown("<div class='dynamic-box'>", unsafe_allow_html=True)
        st.markdown("### RAW DATA STRUCTURE")
        
        if st.session_state.data_structure:
            st.markdown("**DETECTED FIELDS:**")
            for field, field_type in st.session_state.data_structure.items():
                st.markdown(f"`{field}` → *{field_type}*")
        
        st.markdown("---")
        st.markdown("**FULL DATA PREVIEW:**")
        with st.expander("VIEW COMPLETE DATA"):
            st.json(st.session_state.profile_data)
        st.markdown("</div>", unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown("**VERSION**: Dynamic 3.0")
with col_f2:
    st.markdown(f"**UPDATED**: {datetime.now().strftime('%H:%M:%S')}")
with col_f3:
    st.markdown("**MODE**: Adaptive Processing")

# --- JavaScript for message history clicks ---
st.markdown("""
<script>
    document.addEventListener('DOMContentLoaded', function() {
        const items = document.querySelectorAll('.message-history-item');
        items.forEach(item => {
            item.addEventListener('click', function() {
                const idx = this.getAttribute('onclick').match(/\\d+/)[0];
                window.parent.postMessage({
                    type: 'streamlit:setComponentValue',
                    value: parseInt(idx)
                }, '*');
            });
        });
    });
</script>
""", unsafe_allow_html=True)

# --- Deployment Info ---
with st.expander("SYSTEM INFO"):
    st.markdown("""
  
    """)
