import uvicorn
from fastapi import FastAPI, UploadFile, File, HTTPException, Body, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uuid
import json
from typing import Dict
from dotenv import load_dotenv

# Import utility and service modules
from models.api_models import (
    QuestionRequest, QuestionResponse, 
    EvaluateRequest, EvaluateResponse, 
    EmailRequest, EmailResponse
)
from utils.resume_parser import parse_resume_pdf
# Import the file reader
from utils.file_reader import read_text_file 
from services.rag_service import create_rag_chain, query_rag_chain
from services.gemini_service import generate_questions_from_text, evaluate_transcript,generate_tts_audio
from utils.send_email import send_evaluation_email

# Import LangGraph
from services.interview_graph import create_interview_graph, create_initial_state
# --- Add these to your existing imports in main.py ---
import sqlite3
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage # Optional, if you use messages, but good to have
# Load environment variables from .env file
load_dotenv()


app = FastAPI(
    title="Voice AI Interview Agent Backend",
    description="Handles resume parsing, RAG, question generation, and evaluation."
)

# --- Initialize SQLite Checkpointer ---
# This creates a file named 'interview_state.db' in your project folder.
# check_same_thread=False is required for FastAPI to access it from multiple requests.


# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all origins (for local development)
    allow_credentials=True,
    allow_methods=["*"], # Allow all methods (GET, POST, etc.)
    allow_headers=["*"], # Allow all headers
)

# --- State ---
# We now load JD, company facts, and HR email into the app's state
app.state.rag_chain = None
app.state.job_description = ""
app.state.company_facts = ""
app.state.hr_email = ""

# --- LangGraph Session Storage ---
# Store active interview sessions: {session_id: {"graph": graph, "state": state, "websocket": ws}}
active_sessions: Dict[str, dict] = {}


# --- Endpoints ---

@app.on_event("startup")
async def startup_event():
    """
    On startup, load API keys, file data, and env vars into app state.
    """
    if not os.getenv("GOOGLE_API_KEY"):
        raise RuntimeError("GOOGLE_API_KEY environment variable not set.")
    
    # Load HR Email from .env
    app.state.hr_email = os.getenv("HR_EMAIL")
    if not app.state.hr_email:
        raise RuntimeError("HR_EMAIL environment variable not set.")
        
    # Load Job Description from file
    app.state.job_description = read_text_file("data/job_description.txt")
    if not app.state.job_description:
        raise RuntimeError("Could not load data/job_description.txt.")
        
    # Load Company Facts from file
    app.state.company_facts = read_text_file("data/company_facts.txt")
    if not app.state.company_facts:
        print("Warning: Could not load data/company_facts.txt. RAG context will be empty.")
        
    print("Server started. GOOGLE_API_KEY, HR_EMAIL, and data files loaded.")


@app.get("/")
def read_root():
    return {"message": "Voice AI Interview Agent Backend is running."}

@app.post("/upload-resume", response_model=dict)
async def upload_resume(file: UploadFile = File(...)):
    """
    Endpoint to upload a resume PDF and parse it.
    """
    print("Received resume upload request.")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF.")
    
    try:
        contents = await file.read()
        resume_text = parse_resume_pdf(contents)
        if not resume_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from PDF. The PDF might be image-based or empty.")
        
        return {"resume_text": resume_text}
    
    except Exception as e:
        print(f"Error parsing resume: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse resume: {str(e)}")

@app.post("/generate-questions", response_model=QuestionResponse)
async def generate_questions_endpoint(request: QuestionRequest = Body(...)):
    """
    Generates interview questions based on resume and data loaded from server files.
    """
    try:
        # 1. Create RAG chain from company facts (loaded on startup)
        print("Creating RAG chain...")
        app.state.rag_chain = create_rag_chain(app.state.company_facts)
        print("RAG chain created.")
        
        # 2. Get RAG context (if any)
        rag_context = query_rag_chain(
            app.state.rag_chain,
            f"Facts about our company relevant to a {app.state.job_description}"
        )

        # 3. Generate questions
        print("Generating questions...")
        questions =  generate_questions_from_text(
            request.resume_text,
            app.state.job_description,
            rag_context
        )
  
        return QuestionResponse(questions=questions)
        
    except Exception as e:
        print(f"Error generating questions: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")

@app.post("/evaluate-interview", response_model=EvaluateResponse)
async def evaluate_interview_endpoint(request: EvaluateRequest = Body(...)):
    """
    Evaluates the complete interview transcript.
    """
    try:
        print("Evaluating transcript...")
        transcript_text = "\n\n".join(
            [f"Question {i+1}: {item.question}\nAnswer {i+1}: {item.answer}" 
             for i, item in enumerate(request.transcript)]
        )
        
        evaluation = await evaluate_transcript(transcript_text)
        
        return EvaluateResponse(evaluation=evaluation)
        
    except Exception as e:
        print(f"Error evaluating transcript: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to evaluate transcript: {str(e)}")

@app.post("/send-email", response_model=EmailResponse)
async def send_email_endpoint(request: EmailRequest = Body(...)):
    """
    Sends the evaluation report to the HR email loaded from .env.
    """
    try:
        hr_email = app.state.hr_email
        if not hr_email:
            raise HTTPException(status_code=500, detail="HR Email is not configured on the server.")

        print(f"Sending email to {hr_email}...")
        
        success = send_evaluation_email(
            recipient_email=hr_email,
            candidate_resume=request.candidate_resume,
            evaluation_report=request.evaluation_report
        )
        
        if success:
            return EmailResponse(message="Email sent successfully.")
        else:
            raise HTTPException(status_code=500, detail="Failed to send email. Check SMTP server configuration.")
            
    except Exception as e:
        print(f"Error sending email: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")

# --- TTS Endpoint ---
@app.post("/generate-tts")
async def generate_tts_endpoint(request: dict = Body(...)):
    """
    Generates TTS audio for the given text.
    """
    try:
        print("Generating TTS audio...")
        text = request.get("text", "")
        voice = request.get("voice", "Kore")
        
        if not text:
            raise HTTPException(status_code=400, detail="Text is required")
        
        audio_data, mime_type = await generate_tts_audio(text, voice)
        
        if audio_data and mime_type:
            return {
                "audio_data": audio_data,
                "mime_type": mime_type
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to generate TTS audio")
            
    except Exception as e:
        print(f"Error generating TTS: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate TTS: {str(e)}")


# --- LangGraph Endpoints ---

@app.post("/interview-graph/start")
async def start_interview_graph(file: UploadFile = File(...)):
    """
    Starts a new interview using LangGraph.
    Returns session_id and initial state.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a PDF.")
    
    try:
        # Create session
        session_id = str(uuid.uuid4())
        
        # Read resume file
        resume_file = await file.read()
        
        # Create initial state
        initial_state = create_initial_state(
            resume_file=resume_file,
            job_description=app.state.job_description,
            company_facts=app.state.company_facts,
            hr_email=app.state.hr_email
        )
        initial_state["session_id"] = session_id
        
        # Create graph
        async with AsyncSqliteSaver.from_conn_string("interview_state.db") as memory:
            graph = create_interview_graph(checkpointer=memory)
            config = {"configurable": {"thread_id": session_id}}
            
            # Run graph up to first question (parse, RAG, generate questions, ask first question)
            current_state = initial_state
            async for state_update in graph.astream(initial_state, config=config):
                # Get the last node's output
                for node_name, node_state in state_update.items():
                    current_state = node_state
                    # Stop after asking first question
                    if node_name == "ask_question" and current_state.get("status") == "asking_question":
                        break
            
            # Store session
            active_sessions[session_id] = {
                "graph": graph,
                "state": current_state,
                "websocket": None
            }
            
            return {
                "session_id": session_id,
                "status": current_state.get("status"),
                "current_question": current_state.get("current_question"),
                "question_index": current_state.get("current_question_index", 0),
                "total_questions": len(current_state.get("questions", []))
            }
        
    except Exception as e:
        print(f"Error starting interview graph: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to start interview: {str(e)}")

@app.post("/interview-graph/{session_id}/submit-answer")
async def submit_answer(session_id: str, answer: str = Body(..., embed=True)):
    print(f"🎤 Submitting answer for session {session_id}")
    
    try:
        async with AsyncSqliteSaver.from_conn_string("interview_state.db") as memory:
            graph = create_interview_graph(checkpointer=memory)
            config = {"configurable": {"thread_id": session_id}}
            
            # 1. Get State
            snapshot = await graph.aget_state(config)
            if not snapshot or not snapshot.values:
                raise HTTPException(status_code=404, detail="Session not found.")
            
            current_state = snapshot.values
            current_state["current_answer"] = answer
            current_state["waiting_for_answer"] = False
            
            # 2. Process Answer Node
            from services.interview_graph import process_answer_node
            current_state = await process_answer_node(current_state)
            
            # [SAFETY CHECK] Unwrap tuple if present
            if isinstance(current_state, tuple):
                current_state = current_state[0]

            # 3. Save State
            await graph.aupdate_state(config, current_state, as_node="process_answer")

            final_state = current_state
            
            # 4. Run Graph
            if current_state.get("status") != "needs_follow_up":
                async for state_update in graph.astream(None, config=config):
                    for node_name, node_state in state_update.items():
                        
                        # --- FIX 1: IGNORE INTERNAL INTERRUPT SIGNALS ---
                        if node_name == "__interrupt__":
                            print("⏸️ Graph execution paused (Interrupt triggered).")
                            continue
                        # ------------------------------------------------
                        
                        # --- FIX 2: SAFER TUPLE CHECKING ---
                        if isinstance(node_state, tuple):
                            print(f"⚠️ Node '{node_name}' returned a TUPLE!")
                            if len(node_state) > 0:
                                final_state = node_state[0]
                            else:
                                print(f"⚠️ Tuple was empty. Keeping previous state.")
                        else:
                            final_state = node_state
                        # -----------------------------------
                        
                        print(f"Node executed: {node_name}, status: {final_state.get('status')}")
                        
                        if node_name == "ask_question" and final_state.get("status") == "asking_question":
                            print("➡️ Next question asked.")
                        elif node_name == "send_email":
                            print("💼 Interview complete. Waiting for HR decision...")

            # 5. Final Response
            print(f"✅ Answer processed. Final Status: {final_state.get('status')}")

            is_complete = final_state.get("status") in ["interview_complete", "complete", "candidate_notified"]

            return {
                "status": final_state.get("status"),
                "current_question": final_state.get("current_question"),
                "question_index": final_state.get("current_question_index", 0),
                "total_questions": len(final_state.get("questions", [])),
                "interview_complete": is_complete,
                "evaluation": final_state.get("evaluation"),
                "email_sent": final_state.get("email_sent", False)
            }
        
    except Exception as e:
        print(f"❌ Error submitting answer: {e}")
        if "GeneratorExit" in str(e):
            pass
        else:
            raise HTTPException(status_code=500, detail=f"Failed to submit answer: {str(e)}")
        
@app.get("/interview-graph/{session_id}/state")
async def get_interview_state(session_id: str):
    """
    Gets the current state of an interview session.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    state = session["state"]
    
    return {
        "status": state.get("status"),
        "current_question": state.get("current_question"),
        "question_index": state.get("current_question_index", 0),
        "total_questions": len(state.get("questions", [])),
        "transcript": state.get("transcript", []),
        "waiting_for_answer": state.get("waiting_for_answer", False),
        "interview_complete": state.get("status") == "interview_complete",
        "evaluation": state.get("evaluation"),
        "email_sent": state.get("email_sent", False),
        "error": state.get("error")
    }


@app.websocket("/interview-graph/{session_id}/ws")
async def interview_websocket(websocket: WebSocket, session_id: str):
    """
    WebSocket endpoint for real-time interview updates.
    """
    await websocket.accept()
    
    if session_id not in active_sessions:
        await websocket.send_json({"error": "Session not found"})
        await websocket.close()
        return
    
    try:
        # Store websocket in session
        active_sessions[session_id]["websocket"] = websocket
        
        # Send current state
        state = active_sessions[session_id]["state"]
        await websocket.send_json({
            "type": "state_update",
            "data": {
                "status": state.get("status"),
                "current_question": state.get("current_question"),
                "question_index": state.get("current_question_index", 0),
                "total_questions": len(state.get("questions", []))
            }
        })
        
        # Listen for answers
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "answer":
                answer = data.get("answer", "")
                # Process answer (similar to submit_answer endpoint)
                session = active_sessions[session_id]
                graph = session["graph"]
                current_state = session["state"]
                
                current_state["current_answer"] = answer
                current_state["waiting_for_answer"] = False
                
                # Process and continue
                from services.interview_graph import process_answer_node
                current_state = await process_answer_node(current_state)
                final_state = current_state
                
                if current_state.get("status") != "needs_follow_up":
                    async for state_update in graph.astream(current_state):
                        for node_name, node_state in state_update.items():
                            final_state = node_state
                            if node_name == "ask_question" and final_state.get("status") == "asking_question":
                                break
                            elif node_name == "send_email":
                                break
                
                session["state"] = final_state
                
                # Send update
                await websocket.send_json({
                    "type": "state_update",
                    "data": {
                        "status": final_state.get("status"),
                        "current_question": final_state.get("current_question"),
                        "question_index": final_state.get("current_question_index", 0),
                        "total_questions": len(final_state.get("questions", [])),
                        "interview_complete": final_state.get("status") == "interview_complete",
                        "evaluation": final_state.get("evaluation"),
                        "email_sent": final_state.get("email_sent", False)
                    }
                })
                
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for session {session_id}")
    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.send_json({"error": str(e)})
    finally:
        # Clean up
        if session_id in active_sessions:
            active_sessions[session_id]["websocket"] = None

# Add this new endpoint to main.py

@app.get("/hr-decision")
async def hr_decision_endpoint(session_id: str, decision: str):
    """
    Resumes the interview graph after HR decision.
    decision: 'hired' or 'rejected'
    """
    try:
        async with AsyncSqliteSaver.from_conn_string("interview_state.db") as memory:
            print(f"Received HR decision for session {session_id}: {decision}")
            
            # 1. Re-initialize graph with memory
            graph = create_interview_graph(checkpointer=memory)
            config = {"configurable": {"thread_id": session_id}}
            
            # 2. Check if session exists
            snapshot = await graph.aget_state(config)
            if not snapshot.values:
                raise HTTPException(status_code=404, detail="Session not found in DB")

            # 3. Update state with the decision
            # This injects the variable into the paused state
            await graph.aupdate_state(config, {"hr_decision": decision})
            
            # 4. Resume the graph! 
            # It will run 'send_candidate_notification' then END.
            async for event in graph.astream(None, config=config):
                pass # Just let it finish
                
            return {"message": f"Decision '{decision}' recorded. Candidate notified."}
        
    except Exception as e:
        print(f"Error processing HR decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="127.0.0.1", port=port, reload=True)
