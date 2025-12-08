import os
from google import genai
from google.genai import types
from typing import List, Tuple, Optional, TypedDict
import json
import base64

# Configure the Gemini API key
api_key = os.getenv("GOOGLE_API_KEY")
client = None

if not api_key:
    print("⚠️ WARNING: GOOGLE_API_KEY not found in environment variables.")
    print("   Please set it in your .env file in the project root.")
else:
    client = genai.Client(api_key=api_key)

# In services/gemini_service.py (add this new class)

class AnswerSufficiency(TypedDict):
    """Schema for the answer sufficiency check"""
    is_sufficient: bool
    follow_up_question: Optional[str]

# --- Safety Settings ---
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

# --- Model Initialization ---
# We do not initialize a tts_model, as we use the client for everything.

if not client:
    print("⚠️ WARNING: Models not initialized - GOOGLE_API_KEY not set")

# In services/gemini_service.py (add this new async function)

async def check_answer_sufficiency(question: str, answer: str) -> AnswerSufficiency:
    """
    Checks if an answer is sufficient for the question and generates a follow-up
    if it's not.
    """
    print(f"Checking sufficiency for Q: {question} | A: {answer}")
    
    # Define the generation config to force JSON output
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=AnswerSufficiency,
    )

    prompt = f"""
You are an expert technical interviewer. Evaluate the candidate's answer.

    **Question:** "{question}"
    **Answer:** "{answer}"

    **Task:**
    Determine if the answer is sufficient. 
    - If YES: Set "is_sufficient" to true and "follow_up_question" to null.
    - If NO (vague, incomplete, or completely wrong): Set "is_sufficient" to false and provide a polite, probing "follow_up_question".

    **Output Format:**
    You must respond with a SINGLE JSON object. Do not add markdown formatting like ```json.
    
    Example 1 (Sufficient):
    {{
        "is_sufficient": true,
        "follow_up_question": null
    }}

    Example 2 (Insufficient):
    {{
        "is_sufficient": false,
        "follow_up_question": "Could you elaborate on the specific database schema you used?"
    }} """

    try:
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=config
        )
        text_response = response.text.strip()
        # Parse the JSON response
        if text_response.startswith("```json"):
            text_response = text_response[7:]
        if text_response.endswith("```"):
            text_response = text_response[:-3]
            
        response_json = json.loads(text_response)
        
        # Validate and return
        print(f"Raw sufficiency response: {response_json}")
        is_sufficient = response_json.get("is_sufficient", True)
        follow_up = response_json.get("follow_up_question", None)

        if is_sufficient:
            print("Answer is sufficient.")
            return {"is_sufficient": True, "follow_up_question": None}
        else:
            if not follow_up:
                follow_up = "Could you please provide more details?"
            print(f"Answer is insufficient. Follow-up: {follow_up}")
            return {"is_sufficient": False, "follow_up_question": follow_up}

    except Exception as e:
        print(f"Error checking answer sufficiency: {e}")
        # Fallback: If the check fails, assume the answer is sufficient
        # to avoid breaking the interview flow.
        return {"is_sufficient": True, "follow_up_question": None}

# --- FIXED: Changed to 'def' (synchronous) ---
def generate_questions_from_text(resume_text: str, job_description: str, rag_context: str) -> List[str]:
    """
    Generates interview questions using Gemini. (SYNCHRONOUS)
    """
    if not client:
        raise ValueError("Gemini client not initialized. Please check GOOGLE_API_KEY in .env file.")
    # 3. Third question?
    system_prompt = f"""
You are an expert HR manager conducting a technical and behavioral interview. 
Based on the provided resume, job_description, and company facts, generate exactly 1 interview questions.
The questions should be a mix of:
- Resume-specific (e.g., "Tell me about your project X...")
- Behavioral (e.g., "Describe a time when...")
- Role-specific (e.g., "How would you handle Y task...")
- Company-specific (using the provided company facts)

Format the output as a numbered list. Do NOT include any preamble or conclusion.
Example:
1. First question?

"""
    user_prompt = f"""
--- RESUME ---
{resume_text}

--- JOB DESCRIPTION ---
{job_description}

--- RELEVANT COMPANY FACTS (from RAG) ---
{rag_context or "N/A"}
"""

    try:
        # --- FIXED: Changed to 'generate_content' (synchronous) ---
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[system_prompt, user_prompt],
            config=types.GenerateContentConfig(temperature=0.7)
        )
        
        text = response.text
        # Parse the numbered list of questions
        questions = text.split('\n')
        questions = [q.replace(f"{i+1}.", "").strip() for i, q in enumerate(questions) if q]
        
        if not questions:
            raise ValueError("Model did not return any questions.")
        # print(questions)
        return questions

    except Exception as e:
        print(f"Error in Gemini question generation: {e}")
        # Fallback in case of API error
        return [
            "Can you tell me about your most recent project?",
            "What challenges did you face and how did you overcome them?",
            "Why are you interested in this role?",
            "How do you handle working under pressure?",
            "What do you know about our company?"
        ]

# --- FIXED: Changed to 'def' (synchronous) ---
async def evaluate_transcript(transcript_text: str) -> str: # Made a change
    """
    Evaluates a full interview transcript using Gemini. (SYNCHRONOUS)
    """
    if not client:
        raise ValueError("Gemini client not initialized. Please check GOOGLE_API_KEY in .env file.")
    
    system_prompt = """
You are a senior hiring manager providing a final evaluation for a job candidate. 
You will be given the full transcript of an AI-conducted interview.
Your task is to provide a comprehensive evaluation of the candidate's performance.

The evaluation report must include the following sections, formatted using Markdown:
- **Overall Summary:** A brief, 2-3 sentence summary of the candidate's performance.
- **Strengths:** A bulleted list of the candidate's strong points.
- **Weaknesses / Areas for Improvement:** A bulleted list of areas where the candidate could improve.
- **Competency Score:** An overall score from 1 to 10 (e.g., **Score: 7.5/10**).

Base your evaluation *only* on the provided transcript. Be critical but fair.
Do not evaluate the AI's questions, only the candidate's answers.
Be concise and professional.
"""
    
    user_prompt = f"""
--- INTERVIEW TRANSCRIPT ---
{transcript_text}

--- END OF TRANSCRIPT ---

Please provide your evaluation now.
"""
    
    try:
        # --- FIXED: Changed to 'generate_content' (synchronous) ---
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[system_prompt, user_prompt],
            config=types.GenerateContentConfig(temperature=0.5)
        )
        return response.text
    
    except Exception as e:
        print(f"Error in Gemini evaluation: {e}")
        return f"Error: Could not evaluate transcript. {e}"

# --- FIXED: TTS Function (Synchronous REST API call) ---
async def generate_tts_audio(text_to_speak: str, voice: str = "Kore") -> Tuple[Optional[str], Optional[str]]: # change
    """
    Generates TTS audio using the Gemini API via the google-genai SDK.
    Returns (base64_audio_data, mime_type)
    """
    print(f"Generating TTS audio for text: {text_to_speak}")
    if not client:
        print("Error in TTS: GOOGLE_API_KEY not set.")
        return None, None

    prompt = f"Say in a professional, clear, and neutral tone: {text_to_speak}"
    
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                    )
                )
            )
        )
        
        # Extract audio data
        # The response structure for audio might be in candidates[0].content.parts[0].inline_data
        if response.candidates and len(response.candidates) > 0:
            part = response.candidates[0].content.parts[0]
            if part.inline_data:
                audio_bytes = part.inline_data.data
                mime_type = part.inline_data.mime_type
                
                # Convert bytes to base64 string
                audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
                
                print(f"Generated audio MIME type: {mime_type}")
                return audio_b64, mime_type
        
        print(f"Invalid audio response structure from API.")
        return None, None
            
    except Exception as e:
        print(f"Error in Gemini TTS generation: {e}")
        return None, None