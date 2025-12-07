import {
    setupScreen, reportScreen, startInterviewBtn, restartBtn,
    resumeFile, resumeText,
    questionText, answerText, reportStatus,
    showModal, updateStatus, switchScreen
} from './ui.js';

import {
    uploadResume, getQuestions, evaluateInterview, sendEmail, callGeminiTTS,
    startInterviewGraph, submitAnswer, getInterviewState, createInterviewWebSocket, sendAnswerViaWebSocket
} from './api.js';

import { playAudioAndListen } from './audio.js';
import { setupSpeechRecognition, startListening } from './speech.js';

// --- State Variables ---
let questions = [];
let transcript = [];
let currentQuestionIndex = 0;
let finalEvaluation = ""; // Store the final report text

// --- LangGraph State Variables ---
let sessionId = null;
let interviewWebSocket = null;
let useGraphMode = true; // Toggle between graph and legacy mode

// --- Core Application Flow ---

/**
 * 1. Entry point: User clicks "Start Interview"
 */
async function handleStartInterview() {
    startInterviewBtn.disabled = true;
    startInterviewBtn.textContent = 'Starting Interview...';
    
    // === 1. VALIDATE INPUTS ===
    const file = resumeFile.files[0];

    if (!file) {
        showModal("Missing Information", "Please upload a resume PDF.");
        startInterviewBtn.disabled = false;
        startInterviewBtn.textContent = 'Start Interview';
        return;
    }
    
    // === 2. SETUP SPEECH RECOGNITION ===
    if (!setupSpeechRecognition({ onAnswer: handleSpeechEnd })) {
        startInterviewBtn.disabled = false;
        startInterviewBtn.textContent = 'Start Interview';
        return; // STT setup failed
    }

    try {
        if (useGraphMode) {
            // === LANGGRAPH MODE ===
            startInterviewBtn.textContent = 'Initializing Interview Graph...';
            console.log("Starting interview graph session...");
            
            // Start interview graph
            const graphResponse = await startInterviewGraph(file);
            sessionId = graphResponse.session_id;
            questions = []; // Will be populated from state
            
            // Store resume text if available
            if (graphResponse.resume_text) {
                resumeText.value = graphResponse.resume_text;
            }
            
            // Setup WebSocket for real-time updates (optional)
            // interviewWebSocket = createInterviewWebSocket(sessionId, handleGraphStateUpdate);
            
            // Get initial state
            const state = await getInterviewState(sessionId);
            questions = Array(state.total_questions).fill(''); // Placeholder, will be updated
            
            // Start interview with first question
            switchScreen('interview');
            await askQuestionFromGraph(state);
            
        } else {
            // === LEGACY MODE (Original Flow) ===
            startInterviewBtn.textContent = 'Parsing Resume...';
            
            // Upload & Parse Resume
            console.log("Uploading resume for parsing...");
            const uploadResponse = await uploadResume(file);
            resumeText.value = uploadResponse.resume_text;
            
            // Generate Questions
            startInterviewBtn.textContent = 'Generating Questions...';
            const questionsResponse = await getQuestions(resumeText.value);
            
            questions = questionsResponse.questions;
            console.log("Received questions:", questions);
            if (questions.length === 0) {
                throw new Error("Backend did not return any questions.");
            }
            
            // Start Interview Q&A Loop
            switchScreen('interview');
            askQuestion(0);
        }

    } catch (error) {
        console.error("Failed to start interview:", error);
        showModal("Error", `Failed to start interview: ${error.message}`);
        startInterviewBtn.disabled = false;
        startInterviewBtn.textContent = 'Start Interview';
    }
}

/**
 * 3. Ask a single question (TTS) and prepare to listen.
 * @param {number} index - The index of the question to ask.
 */
async function askQuestion(index) {
    if (index >= questions.length) {
        finishInterview();
        return;
    }

    const question = questions[index];
    questionText.textContent = question;
    answerText.textContent = ''; // Clear previous answer
    updateStatus(`Asking question ${index + 1} of ${questions.length}...`);

    try {
        // Call TTS API (from frontend js/api.js)
        const { audioData, mimeType } = await callGeminiTTS(question);
        // The playAudio function will call startListening() onended
        playAudioAndListen(audioData, mimeType);
    } catch (error) {
        console.error("TTS Error:", error);
        showModal("TTS Error", `Could not generate audio for the question: ${error.message}. I will start listening instead.`);
        // Fallback: If TTS fails, just start listening
        // Note: startListening() is now called by playAudioAndListen, even on error.
    }
}

/**
 * 4. Callback for when speech recognition provides a final answer.
 * @param {string} answer - The final answer from the speech service.
 */
async function handleSpeechEnd(answer) {
    if (useGraphMode && sessionId) {
        // === LANGGRAPH MODE ===
        try {
            // Submit answer to graph
            const updatedState = await submitAnswer(sessionId, answer);
            console.log("Submitted answer to graph. Updated state:", updatedState);
            // Update local state
            transcript.push({
                question: updatedState.current_question || questions[currentQuestionIndex],
                answer: answer
            });
            
            // Check if interview is complete
            if (updatedState.interview_complete) {
                console.log("Interview complete according to graph state.");
                finishInterviewFromGraph(updatedState);
            } else {
                // Ask next question
                console.log("Asking next question from graph:", updatedState.current_question);
                await askQuestionFromGraph(updatedState);
            }
        } catch (error) {
            console.error("Error submitting answer:", error);
            showModal("Error", `Failed to submit answer: ${error.message}`);
        }
    } else {
        // === LEGACY MODE ===
        // Save to transcript
        transcript.push({
            question: questions[currentQuestionIndex],
            answer: answer
        });

        // Move to the next question or finish
        currentQuestionIndex++;
        if (currentQuestionIndex < questions.length) {
            askQuestion(currentQuestionIndex);
        } else {
            finishInterview();
        }
    }
}

/**
 * Ask question from graph state (LangGraph mode)
 * @param {object} state - The current interview state from graph
 */
async function askQuestionFromGraph(state) {
    const question = state.current_question;
    console.log("Asking question from graph:", question);
    if (!question) {
        // Get updated state
        const updatedState = await getInterviewState(sessionId);
        if (updatedState.current_question) {
            questionText.textContent = updatedState.current_question;
            currentQuestionIndex = updatedState.question_index;
            updateStatus(`Asking question ${updatedState.question_index + 1} of ${updatedState.total_questions}...`);
            
            // Generate TTS and play
            try {
                const { audioData, mimeType } = await callGeminiTTS(updatedState.current_question);
                playAudioAndListen(audioData, mimeType);
            } catch (error) {
                console.error("TTS Error:", error);
                showModal("TTS Error", `Could not generate audio: ${error.message}. Starting to listen...`);
                startListening();
            }
        } else {
            finishInterviewFromGraph(updatedState);
        }
        return;
    }
    
    questionText.textContent = question;
    answerText.textContent = '';
    currentQuestionIndex = state.question_index;
    updateStatus(`Asking question ${state.question_index + 1} of ${state.total_questions}...`);
    
    // Generate TTS and play
    try {
        const { audioData, mimeType } = await callGeminiTTS(question);
        playAudioAndListen(audioData, mimeType);
    } catch (error) {
        console.error("TTS Error:", error);
        showModal("TTS Error", `Could not generate audio: ${error.message}. Starting to listen...`);
        startListening();
    }
}

/**
 * Finish interview from graph state (LangGraph mode)
 * @param {object} state - The final interview state
 */
async function finishInterviewFromGraph(state) {
    updateStatus("Interview complete! Evaluation sent to hiring team.");
    switchScreen('report');
    reportStatus.textContent = "Your evaluation has been sent to the hiring team. Thank you!";
    
    // Store evaluation if available
    if (state.evaluation) {
        finalEvaluation = state.evaluation;
    }
}
/**
 * 5. All questions are done, now evaluate the interview.
 */
async function finishInterview() {
    updateStatus("Interview complete! Evaluating your answers...");
    switchScreen('report'); // Show the report screen
    reportStatus.textContent = "Evaluating performance and sending report to the hiring team...";

    try {
        // === 6. GET EVALUATION ===
        const evalResponse = await evaluateInterview(transcript);
        finalEvaluation = evalResponse.evaluation; // Store for email
        
        // --- Report rendering is REMOVED ---
        // We no longer display the report content in the UI.
        
        // === 7. SEND EMAIL ===
        reportStatus.textContent = `Evaluation complete! Sending report to the hiring team...`;
        
        // Call sendEmail without hr_email argument
        await sendEmail(
            resumeText.value,
            finalEvaluation
        );
        
        // Update status to final confirmation
        reportStatus.textContent = `Your evaluation has been sent to the hiring team. Thank you!`;

    } catch (error) {
        console.error("Failed to generate or send report:", error);
        // Display a more user-friendly error on the report screen
        reportStatus.textContent = "An error occurred while sending your report. Please contact the administrator.";
    }
}

// --- Initial Event Listeners ---
startInterviewBtn.addEventListener('click', handleStartInterview);
restartBtn.addEventListener('click', () => {
    // Reset everything 
    switchScreen('setup');
    questions = [];
    transcript = [];
    currentQuestionIndex = 0;
    finalEvaluation = "";
    sessionId = null;
    
    // Close WebSocket if open
    if (interviewWebSocket) {
        interviewWebSocket.close();
        interviewWebSocket = null;
    }
    
    // Clear form fields
    resumeFile.value = '';
    resumeText.value = '';
    
    reportStatus.textContent = "Generating your evaluation...";
});
