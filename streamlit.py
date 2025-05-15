import streamlit as st
from google import genai
from google.genai import types
from docx import Document
from docx.shared import Pt
from io import BytesIO
import uuid
import os
import re

# Initialize Gemini client
client = genai.Client(api_key=st.secrets["gemini_api_key"])

# Load system instruction for tender drafting
with open("tender_prompt.txt", "r") as file:
    sys_instruct = file.read()

st.title("📄 AI Tender Document Generator")

# Helper: Suggest follow-up sections
def get_prompt_suggestions(user_input, ai_response):
    prompt = f"""
You are a helpful AI assistant that helps users draft professional tender documents. Based on the user's latest input and the AI's response, suggest 3 to 5 logical follow-up prompts or sections the user might want to include next.

Format your output as a Python list of strings.

User Input:
\"\"\"{user_input}\"\"\"

AI Response:
\"\"\"{ai_response}\"\"\"

Return only the list like:
["Add payment terms", "Include evaluation criteria", "Mention timeline and deadlines", "List eligibility criteria"]
"""
    suggestion_chat = client.chats.create(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(
            system_instruction="You are a prompt suggestion expert for AI-generated tender documents.",
            response_mime_type="application/json"
        )
    )
    result = suggestion_chat.send_message(prompt)
    try:
        suggestions = eval(result.text.strip())
        if isinstance(suggestions, list):
            return suggestions
    except Exception as e:
        print(f"Error parsing suggestions: {e}")
    return ["Include scope of work", "Define bidder qualifications", "Mention deliverables"]

# Helper: Format all AI assistant replies into a well-styled Word doc
def generate_formatted_tender_doc(messages):
    doc = Document()
    doc.add_heading("Tender Document", 0)

    style = doc.styles['Normal']
    font = style.font
    font.name = 'Calibri'
    font.size = Pt(11)

    for msg in messages:
        if msg["role"] == "assistant":
            lines = msg["content"].strip().split("\n")
            for line in lines:
                if line.strip().endswith(":"):
                    doc.add_heading(line.strip(), level=1)
                elif line.strip().startswith("-") or line.strip().startswith("•"):
                    doc.add_paragraph(line.strip().lstrip("-• "), style='List Bullet')
                elif line.strip():
                    doc.add_paragraph(line.strip())
    
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

# Helper: Extract placeholders like [Text], <Text>, or {{Text}}
def extract_placeholders(text):
    matches = re.findall(r'\[.*?\]|\{.*?\}|\<.*?\>', text)
    unique = sorted(set([m.strip("[]{}<>") for m in matches]))
    return unique

# Session state initialization
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())

if "chat_session" not in st.session_state:
    st.session_state.chat_session = client.chats.create(
        model="gemini-2.0-flash",
        config=types.GenerateContentConfig(system_instruction=sys_instruct),
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

if "selected_prompt" not in st.session_state:
    st.session_state.selected_prompt = None

if "last_response" not in st.session_state:
    st.session_state.last_response = ""

if "suggestions" not in st.session_state:
    st.session_state.suggestions = []

# Initial greeting
if not st.session_state.messages:
    greeting = "Hello! I can help you draft a professional tender document. Tell me your requirement to get started."
    st.session_state.messages.append({"role": "assistant", "content": greeting})

# Guided input for common tender sections
with st.expander("🧩 Need help drafting your requirement?"):
    st.markdown("Choose a template section to start drafting your tender:")
    template_options = [
        "Scope of Work",
        "Eligibility Criteria",
        "Evaluation Method",
        "Timeline and Deliverables",
        "Terms & Conditions"
    ]
    selected_template = st.selectbox("Select a requirement to draft", template_options)
    if st.button("Generate Draft Section"):
        template_prompt = f"Write a professional and detailed section for: {selected_template}. Use placeholders like [Insert Project Name] if data is missing."
        st.session_state.selected_prompt = template_prompt
        st.rerun()

# Show conversation history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Input field
user_input = st.chat_input("Describe what the tender is for...")

# Handle user input
if user_input:
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    with st.spinner("Drafting section..."):
        response = st.session_state.chat_session.send_message(user_input)
        bot_response = response.text

    st.session_state.last_response = bot_response
    st.session_state.messages.append({"role": "assistant", "content": bot_response})

    with st.chat_message("assistant"):
        st.markdown(bot_response)

    st.session_state.suggestions = get_prompt_suggestions(user_input, bot_response)

    st.rerun()

# Handle clicked suggestions or selected template
if st.session_state.selected_prompt:
    prompt = st.session_state.selected_prompt
    with st.chat_message("user"):
        st.markdown(prompt)
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.spinner("Generating content..."):
        response = st.session_state.chat_session.send_message(prompt)
        bot_response = response.text

    st.session_state.last_response = bot_response
    st.session_state.messages.append({"role": "assistant", "content": bot_response})

    with st.chat_message("assistant"):
        st.markdown(bot_response)

    st.session_state.suggestions = get_prompt_suggestions(prompt, bot_response)
    st.session_state.selected_prompt = None
    st.rerun()

# Show follow-up suggestions
if st.session_state.suggestions and not st.session_state.selected_prompt:
    with st.chat_message("assistant"):
        st.markdown("Would you like to include:")
        for i, suggestion in enumerate(st.session_state.suggestions):
            if st.button(suggestion, key=f"suggest_{i}_{st.session_state.session_id}"):
                st.session_state.selected_prompt = suggestion
                st.rerun()

# Check and replace placeholders in latest AI response
if st.session_state.last_response:
    placeholders = extract_placeholders(st.session_state.last_response)
    if placeholders:
        with st.chat_message("assistant"):
            st.markdown("📝 Please fill in the following missing details to complete the section:")

            filled = {}
            for key in placeholders:
                filled[key] = st.text_input(f"{key}:", key=f"placeholder_{key}")

            if all(filled.values()) and st.button("✅ Update Section with Details", key="fill_data_button"):
                updated_response = st.session_state.last_response
                for key, val in filled.items():
                    updated_response = re.sub(rf"[\[\{{\<]{key}[\]\}}\>]", val, updated_response)

                st.session_state.messages[-1]["content"] = updated_response
                st.session_state.last_response = updated_response

                st.success("✅ Updated draft with your inputs!")
                st.rerun()

# Word document download
if any(m["role"] == "assistant" for m in st.session_state.messages):
    word_file = generate_formatted_tender_doc(st.session_state.messages)
    st.download_button(
        label="📥 Download Full Tender Document (.docx)",
        data=word_file,
        file_name="AI_Generated_Tender_Document.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
