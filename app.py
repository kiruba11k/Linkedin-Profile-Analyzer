import streamlit as st
import requests
import json
from datetime import datetime
import time

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
    
    status_placeholder = st.empty()
    progress_bar = st.progress(0)
    
    for attempt in range(max_attempts):
        progress = min(100, int((attempt + 1) / max_attempts * 80))
        progress_bar.progress(progress)
        
        status_placeholder.info(f"Scraping LinkedIn profile. Attempt {attempt + 1} of {max_attempts}")
        
        try:
            status_endpoint = f"https://api.apify.com/v2/actor-runs/{run_id}"
            status_response = requests.get(status_endpoint, headers=headers, timeout=15)
            
            if status_response.status_code == 200:
                status_data = status_response.json()["data"]
                current_status = status_data.get("status", "UNKNOWN")
                
                status_placeholder.info(f"Apify status: {current_status}")
                
                if current_status == "SUCCEEDED":
                    status_placeholder.success("LinkedIn data fetched successfully")
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
                    status_placeholder.error(f"Apify run failed: {current_status}")
                    return None
                    
                elif current_status == "RUNNING":
                    time.sleep(10)
                    continue
                    
            else:
                status_placeholder.warning(f"Failed to check status: {status_response.status_code}")
                time.sleep(10)
                
        except Exception as e:
            status_placeholder.warning(f"Error checking status: {str(e)}")
            time.sleep(10)
    
    status_placeholder.error("Polling timeout - Apify taking too long")
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
            "model": "mixtral-8x7b-32768",
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
    Users can provide instructions to refine messages.
    """
    # Prepare profile summary
    profile_summary = json.dumps(profile_data, indent=2)[:1500]
    
    # Build learning examples from your messages
    learning_examples = '''
    "Hi David,
    Your FP&A leadership at Planet—especially across Adaptive Planning and comp modeling—shows rare execution depth across both finance and tech ops. I focus on automating financial workflows to improve accuracy and forecasting agility. Would be glad to connect.
    Best, Joseph"

    "Hi Gabriel,
    Your move to Planet Home Lending builds on deep experience in origination, recruiting, and growth across the Southeast. I focus on automating lending workflows to improve turnaround and reduce manual bottlenecks. Would be glad to connect.
    Best, Joseph"

    "Hi James,
    Your work leading renovation lending at Planet—built on decades across 203(k), HomeStyle, and builder programs—gives you sharp insight into delivery gaps. I focus on automating loan workflows to reduce friction and improve control.
    Best, Joseph"

    "Hi John,
    I noticed your leadership in mortgage lending at Planet Home Lending. I've been exploring how technology is reshaping lending workflows and enhancing efficiency. Coming from a similar ecosystem, I'd like to connect.
    Best, Joseph"

    "Hi Heather,
    Adam mentioned your name when we spoke about retention and analytics at Planet. Given your leadership in marketing and data-driven strategies, I'd love to connect and exchange perspectives on how automation is evolving retention strategy.
    Best, Joseph"
    '''
    
    if user_instructions and previous_message:
        # Refinement mode
        prompt = f'''
        REFINE THIS MESSAGE BASED ON USER INSTRUCTIONS:
        
        ORIGINAL MESSAGE:
        {previous_message}
        
        USER INSTRUCTIONS:
        {user_instructions}
        
        PROFILE CONTEXT:
        {profile_summary}
        
        MESSAGE PATTERN EXAMPLES:
        {learning_examples}
        
        TASK: Modify the original message following the user's instructions while maintaining:
        1. Under 275 characters
        2. Natural three-part structure (about them, about you, connection)
        3. Professional tone matching the examples
        4. End with: Best, {sender_name}
        
        Generate only the refined message.
        '''
    else:
        # New generation mode
        prompt = f'''
        ANALYZE THESE MESSAGE PATTERNS AND CREATE A NEW ONE:
        
        STUDY THESE NATURAL MESSAGES (understand their organic flow):
        {learning_examples}
        
        OBSERVED PATTERN (not template):
        1. Personalized opening about recipient's work/thoughts/recent activity
        2. What sender does related to that work
        3. Natural connection request
        4. Under 275 characters
        5. Ends with: Best, [Sender Name]
        
        NOW CREATE A MESSAGE FOR THIS PROFILE:
        {profile_summary}
        
        YOUR TASK:
        1. ANALYZE the profile data naturally
        2. CREATE a message that follows the organic pattern you observed
        3. DO NOT use templates or fixed structures
        4. Make it feel personal and specific to this person
        5. Keep under 275 characters
        6. Sign it: Best, {sender_name}
        
        Generate only the message content.
        '''
    
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
                    "content": f'''You are a skilled communicator who understands message patterns organically. 
                    You don't use templates. You analyze how people naturally write and create messages with similar flow.
                    You're creative but professional. Your signature is always: Best, {sender_name}'''
                },
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.8,
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
            
            # Clean up but preserve natural flow
            message = message.replace('"', '').replace("''", "'")
            
            # Ensure proper signature
            if f"Best, {sender_name}" not in message:
                message = f"{message.rstrip()}\nBest, {sender_name}"
            
            # Length check
            if len(message) > 275:
                # Try to shorten while preserving meaning
                lines = message.split('\n')
                if len(lines) >= 2:
                    # Keep the core parts
                    important_lines = [lines[0]]
                    for line in lines[1:-1]:
                        if line.strip() and 'Best,' not in line:
                            important_lines.append(line)
                            if len('\n'.join(important_lines)) > 200:
                                break
                    important_lines.append(lines[-1])
                    message = '\n'.join(important_lines)
                
                if len(message) > 275:
                    message = message[:272] + '...'
            
            return message
        else:
            return f"Hi there,\nI came across your profile and wanted to connect.\nI focus on workflow automation in your industry.\nWould be glad to connect.\nBest, {sender_name}"
            
    except Exception as e:
        return f"Hi,\nYour professional background caught my attention.\nI work on operational improvements in your field.\nWould be good to connect.\nBest, {sender_name}"

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
    }
    
    .status-led.active {
        background: #00ff00;
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
if 'sender_name' not in st.session_state:
    st.session_state.sender_name = "Joseph"
if 'message_instructions' not in st.session_state:
    st.session_state.message_instructions = ""
if 'regenerate_mode' not in st.session_state:
    st.session_state.regenerate_mode = False

# --- Header ---
st.markdown("<h1 class='glitch-header'>PROSPECT RESEARCH ASSISTANT</h1>", unsafe_allow_html=True)
st.markdown("---")

# --- Sidebar Configuration ---
with st.sidebar:
    st.markdown("### SYSTEM CONFIGURATION")
    
    # Use secrets for API keys
    apify_api_key = st.secrets.get("APIFY", "")
    groq_api_key = st.secrets.get("GROQ", "")
    
    # Display API key status
    if apify_api_key:
        st.success("Apify API: Configured")
    else:
        st.error("Apify API: Missing - add to secrets")
        
    if groq_api_key:
        st.success("Groq API: Configured")
    else:
        st.error("Groq API: Missing - add to secrets")
    
    st.markdown("---")
    
    # Sender name configuration
    new_sender_name = st.text_input(
        "YOUR NAME FOR MESSAGES",
        value=st.session_state.sender_name,
        help="This name will sign all messages"
    )
    
    if new_sender_name != st.session_state.sender_name:
        st.session_state.sender_name = new_sender_name
    
    st.markdown("---")
    
    # System Status
    st.markdown("### SYSTEM STATUS")
    status_text = st.session_state.processing_status
    status_class = "active" if status_text == "READY" else ""
    
    st.markdown(f"""
    <div class="terminal-box">
        <span class="status-led {status_class}"></span>
        <strong>STATUS: {status_text}</strong><br>
        Profiles Loaded: {1 if st.session_state.profile_data else 0}<br>
        Messages Generated: {len(st.session_state.generated_messages)}<br>
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
        st.error("ERROR: BOTH API KEYS ARE REQUIRED. Check Streamlit secrets.")
    else:
        st.session_state.processing_status = "STARTING"
        
        username = extract_username_from_url(linkedin_url)
        run_info = start_apify_run(username, apify_api_key)
        
        if run_info:
            st.info(f"Apify Run ID: {run_info['run_id'][:20]}...")
            st.info(f"Dataset ID: {run_info['dataset_id'][:20]}...")
            st.info("This may take 30-60 seconds. Please wait...")
            
            profile_data = poll_apify_run_with_status(
                run_info["run_id"],
                run_info["dataset_id"],
                apify_api_key
            )
            
            if profile_data:
                st.session_state.profile_data = profile_data
                st.session_state.processing_status = "DATA RECEIVED"
                
                with st.spinner("Generating research brief with AI..."):
                    research_brief = generate_research_brief(
                        profile_data,
                        groq_api_key
                    )
                    st.session_state.research_brief = research_brief
                    st.session_state.processing_status = "COMPLETE"
                    st.success("Analysis complete")
            else:
                st.session_state.processing_status = "ERROR"
                st.error("Failed to get data from Apify")
        else:
            st.session_state.processing_status = "ERROR"

# --- Display Results ---
if st.session_state.profile_data and st.session_state.research_brief:
    st.markdown("---")
    
    tab1, tab2, tab3 = st.tabs(["RESEARCH BRIEF", "MESSAGES", "RAW DATA"])
    
    with tab1:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown(f"**RESEARCH BRIEF - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}**")
        st.markdown("---")
        st.markdown(st.session_state.research_brief)
        st.markdown("</div>", unsafe_allow_html=True)
    
    with tab2:
        if st.session_state.profile_data:
            # Sender name display
            st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
            st.markdown(f"**SENDER NAME:** {st.session_state.sender_name}")
            st.markdown("</div>")
            
            # Message generation and refinement area
            st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
            st.markdown("### MESSAGE GENERATION")
            
            if not st.session_state.regenerate_mode:
                # Normal message generation
                col_gen1, col_gen2 = st.columns([2, 1])
                
                with col_gen1:
                    if st.button("GENERATE NEW MESSAGE", use_container_width=True):
                        with st.spinner("Analyzing patterns and creating message..."):
                            new_message = analyze_and_generate_message(
                                st.session_state.profile_data,
                                groq_api_key,
                                st.session_state.sender_name
                            )
                            
                            if new_message:
                                st.session_state.generated_messages.append(new_message)
                                st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                                st.session_state.regenerate_mode = False
                                st.rerun()
                
                with col_gen2:
                    if st.button("REFINE/CUSTOMIZE", use_container_width=True):
                        if len(st.session_state.generated_messages) > 0:
                            st.session_state.regenerate_mode = True
                            st.session_state.message_instructions = ""
                            st.rerun()
            else:
                # Regeneration mode with instructions
                st.markdown("#### PROVIDE INSTRUCTIONS FOR IMPROVEMENT")
                st.markdown("*Example: 'Make it more technical', 'Shorter', 'Focus on AI projects', etc.*")
                
                user_instructions = st.text_area(
                    "Your instructions:",
                    value=st.session_state.message_instructions,
                    height=100,
                    key="instructions_input",
                    label_visibility="collapsed"
                )
                
                col_ref1, col_ref2, col_ref3 = st.columns(3)
                
                with col_ref1:
                    if st.button("GENERATE WITH INSTRUCTIONS", use_container_width=True):
                        if user_instructions and len(st.session_state.generated_messages) > 0:
                            current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
                            
                            with st.spinner("Creating refined message..."):
                                refined_message = analyze_and_generate_message(
                                    st.session_state.profile_data,
                                    groq_api_key,
                                    st.session_state.sender_name,
                                    user_instructions,
                                    current_msg
                                )
                                
                                if refined_message:
                                    st.session_state.generated_messages.append(refined_message)
                                    st.session_state.current_message_index = len(st.session_state.generated_messages) - 1
                                    st.session_state.regenerate_mode = False
                                    st.session_state.message_instructions = ""
                                    st.rerun()
                
                with col_ref2:
                    if st.button("USE ORIGINAL", use_container_width=True):
                        st.session_state.regenerate_mode = False
                        st.rerun()
                
                with col_ref3:
                    if st.button("CANCEL", use_container_width=True):
                        st.session_state.regenerate_mode = False
                        st.session_state.message_instructions = ""
                        st.rerun()
            
            st.markdown("</div>")
            
            # Display current message
            if len(st.session_state.generated_messages) > 0:
                current_msg = st.session_state.generated_messages[st.session_state.current_message_index]
                
                st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
                st.markdown(f"**CURRENT MESSAGE**")
                if st.session_state.regenerate_mode:
                    st.markdown("*Refinement mode active*")
                st.markdown(f"Length: {len(current_msg)} characters")
                st.markdown("---")
                st.markdown(current_msg)
                st.markdown("</div>")
                
                # Copy functionality
                st.code(current_msg, language=None)
                
                # Navigation and history
                if len(st.session_state.generated_messages) > 1:
                    st.markdown("#### NAVIGATION")
                    col_nav1, col_nav2, col_nav3 = st.columns(3)
                    
                    with col_nav1:
                        if st.button("PREVIOUS", use_container_width=True):
                            if st.session_state.current_message_index > 0:
                                st.session_state.current_message_index -= 1
                                st.session_state.regenerate_mode = False
                                st.rerun()
                    
                    with col_nav2:
                        st.markdown(f"**{st.session_state.current_message_index + 1} / {len(st.session_state.generated_messages)}**")
                    
                    with col_nav3:
                        if st.button("NEXT", use_container_width=True):
                            if st.session_state.current_message_index < len(st.session_state.generated_messages) - 1:
                                st.session_state.current_message_index += 1
                                st.session_state.regenerate_mode = False
                                st.rerun()
                    
                    # Message history
                    st.markdown("#### MESSAGE HISTORY")
                    for idx, msg in enumerate(st.session_state.generated_messages):
                        is_active = idx == st.session_state.current_message_index
                        active_class = "active" if is_active else ""
                        st.markdown(f"""
                        <div class="message-history-item {active_class}">
                            <small>Version {idx + 1} • {len(msg)} chars</small><br>
                            {msg.split('\\n')[0][:80]}...
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("Generate your first message using the button above.")
        else:
            st.info("Complete profile analysis first to generate messages.")
    
    with tab3:
        st.markdown("<div class='terminal-box'>", unsafe_allow_html=True)
        st.markdown("### RAW PROFILE DATA")
        with st.expander("VIEW JSON DATA"):
            st.json(st.session_state.profile_data)
        st.markdown("</div>", unsafe_allow_html=True)

# --- Footer ---
st.markdown("---")
col_f1, col_f2, col_f3 = st.columns(3)
with col_f1:
    st.markdown("**SYSTEM**: Prospect Research v4.0")
with col_f2:
    st.markdown(f"**TIME**: {datetime.now().strftime('%H:%M:%S')}")
with col_f3:
    if st.session_state.profile_data:
        name = "Profile Loaded"
        if isinstance(st.session_state.profile_data, dict):
            if 'fullname' in st.session_state.profile_data:
                name = st.session_state.profile_data['fullname']
            elif 'basic_info' in st.session_state.profile_data and 'fullname' in st.session_state.profile_data['basic_info']:
                name = st.session_state.profile_data['basic_info']['fullname']
        st.markdown(f"**CURRENT**: {name[:20]}")
    else:
        st.markdown("**CURRENT**: No Profile")
