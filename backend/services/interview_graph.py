"""
LangGraph implementation for Voice AI Interview Agent.
Wraps existing functions as nodes in a stateful workflow graph.
"""
from typing import TypedDict, List, Optional, Annotated
from typing_extensions import Annotated
from langgraph.graph import StateGraph, END

# Import existing functions (no changes to these)
from utils.resume_parser import parse_resume_pdf
from services.rag_service import create_rag_chain, query_rag_chain
from services.gemini_service import generate_questions_from_text, evaluate_transcript,check_answer_sufficiency
from utils.send_email import send_evaluation_email,send_candidate_result_email
import re

# --- State Schema ---
class InterviewState(TypedDict):
    """State schema for the interview graph"""
    # Input
    resume_file: Optional[bytes]
    resume_text: Optional[str]
    job_description: str
    company_facts: str
    candidate_mail: str
    hr_email: str
    session_id:str
    # Processing
    # rag_chain: Optional[object]
    rag_context: Optional[str]
    questions: Annotated[List[str], "List of interview questions"]
    current_question_index: int
    
    # Interview
    transcript: Annotated[List[dict], "List of {question, answer} pairs"]
    current_question: Optional[str]
    current_answer: Optional[str]
    waiting_for_answer: bool
    follow_up_count:int
    
    # Output
    evaluation: Optional[str]
    email_sent: bool
    hr_decision: Optional[str]
    # Control
    status: str  # "parsing", "rag_ready", "questions_ready", "asking_question", 
                 # "waiting_answer", "interview_complete", "evaluated", "complete"
    error: Optional[str]


# --- Node Functions (Wrapping Existing Functions) ---

def parse_resume_node(state: InterviewState) -> InterviewState:
    """Node 1: Wraps parse_resume_pdf()"""
    if state.get("resume_text"):
        return state
    try:
        if state.get("resume_file"):
            state["resume_text"] = parse_resume_pdf(state["resume_file"])
            print("Resume parsed successfully.")

            email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', state["resume_text"])
            if email_match:
                state["candidate_mail"] = email_match.group(0)
                print(f"✅ Extracted Candidate Email: {state['candidate_mail']}")
            else:
                print("⚠️ No candidate email found in resume text.")
            state["status"] = "parsed"
        else:
            state["error"] = "No resume file provided"
            state["status"] = "error"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
    return state


def create_rag_context_node(state: InterviewState) -> InterviewState:
    """Node 2: Wraps create_rag_chain() and query_rag_chain()"""
    if state.get("rag_context") is not None:
        return state
    try:
        rag_chain = create_rag_chain(state.get("company_facts", ""))
        # state["rag_chain"] = rag_chain
        if rag_chain:
            query = f"Facts about our company relevant to a {state.get('job_description', 'position')}"
            state["rag_context"] = query_rag_chain(rag_chain, query) or ""
            print("RAG context created successfully.")
        else:
            # RAG chain creation failed (likely quota issue), continue without RAG context
            state["rag_context"] = ""
            print("⚠️ Continuing without RAG context (embeddings quota may be exceeded)")
        state["status"] = "rag_ready"
    except Exception as e:
        error_msg = str(e)
        # If it's a quota error, continue without RAG
        if "429" in error_msg or "quota" in error_msg.lower():
            state["rag_context"] = ""
            state["status"] = "rag_ready"  # Continue anyway
            print("⚠️ RAG quota exceeded, continuing without company context")
        else:
            state["error"] = error_msg
            state["status"] = "error"
    return state

def generate_questions_node(state: InterviewState) -> InterviewState:
    """Node 3: Wraps generate_questions_from_text()"""
    if state.get("questions") and len(state["questions"]) > 0:
        return state
    try:
        print("Generating questions...")
        questions = generate_questions_from_text(
            state.get("resume_text", ""),
            state.get("job_description", ""),
            state.get("rag_context", "")
        )
        print(questions)
        state["questions"] = questions
        state["current_question_index"] = 0
        state["status"] = "questions_ready"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
    return state


def ask_question_node(state: InterviewState) -> InterviewState:
    """Node 4: Sets up the current question for TTS"""
    try:
        index = state.get("current_question_index", 0)
        questions = state.get("questions", [])
        
        if index < len(questions):
            state["current_question"] = questions[index]
            state["waiting_for_answer"] = True
            state["current_answer"] = None
            state["status"] = "asking_question"
            state
        else:
            state["status"] = "interview_complete"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
    return state

# In interview_graph.py

# Replace the old process_answer_node with this:
async def process_answer_node(state: InterviewState) -> InterviewState:
    """
    Node 5: Processes user's answer, checks for sufficiency,
    and prepares for routing.
    """
    try:
        current_question = state.get("current_question")
        current_answer = state.get("current_answer", "")
        
        if current_question:
            transcript_entry = {
                "question": current_question,
                "answer": current_answer if current_answer else "[No answer provided]"
            }
            state["transcript"] = state.get("transcript", []) + [transcript_entry]
        
        # --- New Follow-up Logic ---
        try:
            # This is the new function you'll create in gemini_service.py
            check = await check_answer_sufficiency(current_question, current_answer)
            is_sufficient = check.get("is_sufficient", True)
            follow_up_question = check.get("follow_up_question")
        except Exception as e:
            print(f"⚠️ Error checking answer sufficiency: {e}. Assuming answer is sufficient.")
            is_sufficient = True
            follow_up_question = None

        follow_up_count = state.get("follow_up_count", 0)
        
        if is_sufficient:
            # Answer is good, move to the next main question
            state["current_question_index"] = state.get("current_question_index", 0) + 1
            state["status"] = "answer_sufficient"
            state["follow_up_count"] = 1 # Reset follow-up count for next question
            state["current_answer"]=None
        elif follow_up_count < 2:
            # Answer is bad, but we can ask a follow-up (max 2)
            state["follow_up_count"] = follow_up_count + 1
            state["current_question"] = follow_up_question # Set new follow-up as current question
            state["current_answer"] = None
            state["waiting_for_answer"] = True # We need to wait for an answer to this
            state["status"] = "needs_follow_up"
        else:
            # Answer is bad, and we are out of follow-ups
            print("Max follow-ups reached. Moving to next question.")
            state["current_question_index"] = state.get("current_question_index", 0) + 1
            state["status"] = "max_follow_ups_reached"
            state["follow_up_count"] = 0 # RESET COUNT
            state["current_answer"] = None # Clear answer
        # --- End New Logic ---

    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
    return state

async def evaluate_interview_node(state: InterviewState) -> InterviewState:
    """Node 6: Wraps evaluate_transcript()"""
    try:
        transcript = state.get("transcript", [])
        transcript_text = "\n\n".join(
            [f"Question {i+1}: {item['question']}\nAnswer {i+1}: {item['answer']}" 
             for i, item in enumerate(transcript)]
        )
        evaluation = await evaluate_transcript(transcript_text)
        state["evaluation"] = evaluation
        state["status"] = "evaluated"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
    return state


def send_email_node(state: InterviewState) -> InterviewState:
    """Node 7: Wraps send_evaluation_email()"""
    try:
        success = send_evaluation_email(
            recipient_email=state.get("hr_email", ""),
            candidate_resume=state.get("resume_text", ""),
            evaluation_report=state.get("evaluation", ""),
            session_id=state.get("session_id") # <--- PASS THE ID HERE
        )
        state["email_sent"] = success
        state["status"] = "complete" if success else "email_failed"
    except Exception as e:
        state["error"] = str(e)
        state["status"] = "error"
    return state


# --- Conditional Edges (Routing Logic) ---

# In interview_graph.py

def should_continue_interview(state: InterviewState) -> str:
    """Determines if we ask a follow-up, next question, or finish"""
    status = state.get("status")

    if status == "needs_follow_up":
        # `process_answer_node` already set the follow-up question.
        # We just need to stop and wait for the user to answer it.
        # Returning "wait_for_followup" will go to END, stopping the stream.
        return "wait_for_followup"
    
    # If answer was sufficient OR max follow-ups was reached,
    # we check if there are more *main* questions.
    
    index = state.get("current_question_index", 0)
    questions = state.get("questions", [])
    
    if index < len(questions):
        # Go to `ask_question` to set up the next main question
        return "continue"
    else:
        # No more main questions, go to evaluate
        print("Interview complete. Proceeding to evaluation.")
        return "finish"


def route_after_answer(state: InterviewState) -> str:
    """Routes after processing an answer"""
    if state.get("status") == "error":
        return "error"
    return "continue"



def send_candidate_notification_node(state: InterviewState) -> InterviewState:
    """Node 8: Sends email to candidate based on HR decision"""
    decision = state.get("hr_decision")
    
    # --- USE THE EXTRACTED EMAIL ---
    candidate_email = state.get("candidate_mail")
    
    if not candidate_email:
        print("❌ Cannot send email: Candidate email not found.")
        return state
        
    print(f"📧 Sending '{decision}' email to Candidate at: {candidate_email}")
    
    # Example call (assuming you have a send function):
    print( f"Decision: {decision}, Candidate Email: {candidate_email}" )
    send_candidate_result_email(candidate_email, decision)
    
    state["status"] = "candidate_notified"
    return state

# --- Graph Construction ---

def create_interview_graph(checkpointer=None):
    """Creates and compiles the interview workflow graph"""
    # Create graph
    workflow = StateGraph(InterviewState)
    
    # Add nodes (wrapping existing functions)
    workflow.add_node("parse_resume", parse_resume_node)
    workflow.add_node("create_rag", create_rag_context_node)
    workflow.add_node("generate_questions", generate_questions_node)
    workflow.add_node("ask_question", ask_question_node)
    workflow.add_node("process_answer", process_answer_node)
    workflow.add_node("evaluate", evaluate_interview_node)
    workflow.add_node("send_email", send_email_node)
    workflow.add_node("send_candidate_notification", send_candidate_notification_node)
    # Define edges
    workflow.set_entry_point("parse_resume")
    workflow.add_edge("parse_resume", "create_rag")
    workflow.add_edge("create_rag", "generate_questions")
    workflow.add_edge("generate_questions", "ask_question")
    workflow.add_edge("evaluate", "send_email")
    workflow.add_edge("send_email", "send_candidate_notification")
    workflow.add_edge("send_candidate_notification", END)
    # After asking question, we need to wait for external answer.
    # So ask_question goes to a "wait" state, but we'll handle this externally.
    # For now, we'll make ask_question transition to END (we'll resume manually)
    # Actually, better: ask_question can conditionally go to process_answer or evaluate
    # But we control this externally by invoking process_answer with the answer
    
    # After processing answer, check if we should continue or finish.
    workflow.add_conditional_edges(
        "process_answer",
        should_continue_interview,
        {
            "continue": "ask_question",
            "finish": "evaluate",
            "wait_for_followup": END
        }
    )
    
    # ask_question needs an edge - it will wait, but we add a conditional that goes to END
    # We'll manually continue from process_answer
    workflow.add_conditional_edges(
        "ask_question",
        lambda state: "wait",  # Always wait for external answer
        {
            "wait": END  # Stop here, will resume via process_answer
        }
    )
    # Compile graph
    return workflow.compile(
        checkpointer = checkpointer,
        interrupt_before = ["send_candidate_notification"]
    )


# --- Helper function to create initial state ---

def create_initial_state(
    resume_file: bytes,
    job_description: str,
    company_facts: str,
    hr_email: str
) -> InterviewState:
    """Creates initial state for the graph"""
    return {
        "resume_file": resume_file,
        "candidate_mail": None,
        "resume_text": None,
        "job_description": job_description,
        "company_facts": company_facts,
        "hr_email": hr_email,
        "rag_context": None,
        "questions": [],
        "current_question_index": 1,
        "transcript": [],
        "current_question": None,
        "current_answer": None,
        "waiting_for_answer": False,
        "follow_up_count": 1,
        "evaluation": None,
        "email_sent": False,
        "status": "starting",
        "error": None
    }

