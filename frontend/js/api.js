// This file now calls our local backend, not the Gemini API directly.

const BACKEND_URL = "http://localhost:8000";
//  window.env.BACKEND_URL ||
/**
 * Helper function to handle fetch responses
 */
async function handleResponse(response) {
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
        throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
    }
    return response.json();
}

/**
 * Uploads the resume PDF to the backend for parsing.
 * @param {File} file - The resume PDF file.
 * @returns {Promise<object>} - The response containing parsed text.
 */
export async function uploadResume(file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${BACKEND_URL}/upload-resume`, {
        method: 'POST',
        body: formData,
    });
    console.log("Upload response status:", response);
    return handleResponse(response);
}

/**
 * Calls the backend to generate questions.
 * @param {string} resume_text - Parsed resume text.
 * @returns {Promise<object>} - The response containing the list of questions.
 */
export async function getQuestions(resume_text) {
    // Payload no longer includes job_description or company_facts
    const payload = {
        resume_text,
    };

    const response = await fetch(`${BACKEND_URL}/generate-questions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    console.log("Get questions response status:", response);
    return handleResponse(response);
}

/**
 * Calls the backend to evaluate the interview transcript.
 * @param {Array<object>} transcript - The list of {question, answer} pairs.
 * @returns {Promise<object>} - The response containing the evaluation.
 */
export async function evaluateInterview(transcript) {
    const payload = { transcript };

    const response = await fetch(`${BACKEND_URL}/evaluate-interview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return handleResponse(response);
}

/**
 * Calls the backend to send the evaluation email.
 * @param {string} candidate_resume - The parsed resume text.
 * @param {string} evaluation_report - The final evaluation report.
 * @returns {Promise<object>} - The response confirming email status.
 */
export async function sendEmail(candidate_resume, evaluation_report) {
    // Payload no longer includes hr_email
    const payload = {
        candidate_resume,
        evaluation_report,
    };

    const response = await fetch(`${BACKEND_URL}/send-email`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    });
    return handleResponse(response);
}

// --- LangGraph API Functions ---

/**
 * Starts a new interview using LangGraph.
 * @param {File} file - The resume PDF file.
 * @returns {Promise<object>} - The response containing session_id and initial state.
 */
export async function startInterviewGraph(file) {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${BACKEND_URL}/interview-graph/start`, {
        method: 'POST',
        body: formData,
    });
    return handleResponse(response);
}

/**
 * Submits an answer for the current question.
 * @param {string} sessionId - The interview session ID.
 * @param {string} answer - The user's answer.
 * @returns {Promise<object>} - The updated state.
 */
export async function submitAnswer(sessionId, answer) { 
    console.log("Submitting answer to backend:", answer);
    const response = await fetch(`${BACKEND_URL}/interview-graph/${sessionId}/submit-answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 'answer' :answer}),
    });
    return handleResponse(response);
}

/**
 * Gets the current state of an interview session.
 * @param {string} sessionId - The interview session ID.
 * @returns {Promise<object>} - The current state.
 */
export async function getInterviewState(sessionId) {
    const response = await fetch(`${BACKEND_URL}/interview-graph/${sessionId}/state`);
    return handleResponse(response);
}

/**
 * Creates a WebSocket connection for real-time updates.
 * @param {string} sessionId - The interview session ID.
 * @param {function} onMessage - Callback for received messages.
 * @returns {WebSocket} - The WebSocket connection.
 */
export function createInterviewWebSocket(sessionId, onMessage) {
    const ws = new WebSocket(`ws://127.0.0.1:8000/interview-graph/${sessionId}/ws`);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        onMessage(data);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onclose = () => {
        console.log('WebSocket disconnected');
    };
    
    return ws;
}

/**
 * Sends an answer through WebSocket.
 * @param {WebSocket} ws - The WebSocket connection.
 * @param {string} answer - The user's answer.
 */
export function sendAnswerViaWebSocket(ws, answer) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            type: 'answer',
            answer: answer
        }));
    }
}


// --- TTS is still handled by the browser-based Gemini API ---
// This keeps the voice interaction fast and avoids audio streaming.
// You MUST add your Google AI API key here for TTS to work.

// TTS API key should be obtained from backend or environment
// For security, TTS should be handled by the backend, not frontend
// This function will call the backend TTS endpoint instead
const BACKEND_TTS_URL = `${BACKEND_URL}/generate-tts`;

/**
 * Calls the backend TTS endpoint to generate audio.
 * @param {string} textToSpeak - The text to synthesize.
 * @param {string} [voice="Kore"] - The voice to use.
 * @returns {Promise<object>} - The response with audio data and mime type.
 */
export async function callGeminiTTS(textToSpeak, voice = "Kore") {
    try {
        const payload = {
            text: textToSpeak,
            voice: voice
        };

        const response = await fetch(`${BACKEND_URL}/generate-tts`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({ detail: "Unknown error" }));
            throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const result = await response.json();
        return {
            audioData: result.audio_data,
            mimeType: result.mime_type
        };
    } catch (error) {
        console.error("TTS generation error:", error);
        // Return a fallback message instead of throwing
        throw new Error(`TTS generation failed: ${error.message}`);
    }
}
