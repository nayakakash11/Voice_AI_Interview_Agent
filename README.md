# Voice-based AI Interview Agent

This project is a full-stack application that simulates a real-time, voice-based AI-powered interview. It's designed to automate the initial screening process by parsing a candidate's resume, generating tailored questions, conducting a voice interview, evaluating the candidate's answers, and emailing a full report to HR.

This application is based on the "Agentic AI" flow, where different services (parsing, question generation, TTS, STT, evaluation, notification) work together to achieve a complex task.

## Features

* **Resume Parsing:** Upload a PDF resume, and the backend extracts the text.

* **Dynamic Question Generation (RAG):** Uses a Retrieval-Augmented Generation (RAG) approach. The Google Gemini API generates 5 unique interview questions based on the candidate's resume, a pre-defined job description, and company-specific facts read from a local file.

* **Text-to-Speech (TTS):** The agent asks questions using a realistic voice (Gemini TTS API).

* **Speech-to-Text (STT):** The candidate's spoken answers are captured using the browser's built-in Web Speech API.

* **AI-Powered Evaluation:** The complete interview transcript (all Q&A pairs) is sent to the Gemini API for a comprehensive evaluation, which includes an overall summary, strengths, weaknesses, and a competency score.

* **Automated Email Report:** The final evaluation report is automatically and securely emailed to a pre-configured HR email address. The candidate does not see the final report.

## Technology Stack

**Backend:**

**Python 3.10+**  
**FastAPI:** For creating the robust, asynchronous API.  
**Uvicorn:** As the ASGI server.  
**Google Gemini API (```google-generativeai```):** For question generation, evaluation, and TTS.  
```python-dotenv```: For managing environment variables.  
```pdfminer.six```: For parsing text from PDF resumes.  

**Frontend:**

**HTML5:** For the application structure.  
**CSS3:** For modern, responsive styling.  
**JavaScript (ES6+):** For all client-side logic, API calls, and state management.  
**Web Speech API (SpeechRecognition):** For capturing the candidate's voice from the browser.

## Project Structure

```
/Voice_AI_Interview_Agent/  
|  
|-- /backend/  
|   |-- /data/  
|   |   |-- company_facts.txt     # (You must create this)  
|   |   |-- job_description.txt   # (You must create this)  
|   |-- /models/  
|   |   |-- api_models.py  
|   |-- /services/  
|   |   |-- gemini_service.py  
|   |   |-- rag_service.py  
|   |-- /utils/  
|   |   |-- send_email.py  
|   |   |-- file_reader.py  
|   |   |-- resume_parser.py  
|   |-- main.py  
|  
|-- /frontend/  
|   |-- /css/  
|   |   |-- style.css  
|   |-- /js/  
|   |   |-- api.js  
|   |   |-- audio.js  
|   |   |-- main.js  
|   |   |-- speech.js  
|   |   |-- ui.js  
|   |-- index.html  
|  
|-- README.md                   # (This file)  
|-- requirements.txt  
|-- .env
```


## Setup and Installation

Follow these steps precisely to run the application locally.

**A) Backend Setup**

1. Navigate to the Backend:
```
cd backend
```

2. Create a Virtual Environment:
```
python3 -m venv venv
```

3. Activate the Environment:
```
source venv/bin/activate
```

4. Install Requirements:
```
pip install -r requirements.txt
```

5. Create Data Files:

* Create a new folder named ```data``` inside the ```backend``` directory.

* Inside ```backend/data/```, create ```job_description.txt``` and paste the job description you want to hire for.

* Inside ```backend/data/```, create ```company_facts.txt``` and paste some key facts about your company for the RAG system.  
  
  
**B) Frontend Setup**

* The frontend has no dependencies to install. You just need to serve the files.
  
  
**C) Create Environment File (```.env```):**

* Edit the ```.env``` file with your credentials:
```
# Get this from Google AI Studio
GOOGLE_API_KEY="YOUR_GOOGLE_AI_API_KEY"

# The email address you want reports sent TO
HR_EMAIL="your_hr_email@company.com"

# Your email credentials (for sending the report)
# Example for Gmail:
EMAIl_HOST="smtp.gmail.com"
EMAIL_PORT=587
EMAIL_USER="your_sending_email@gmail.com"

# IMPORTANT: For Gmail, this is an "App Password", not your regular password
# See: [https://support.google.com/accounts/answer/185833](https://support.google.com/accounts/answer/185833)
EMAIL_PASS="YOUR_SMTP_APP_PASSWORD" 
```


## How to Run the Application

You must have two separate terminals open and running simultaneously.


**Terminal 1: Run the Backend**

1. Navigate to the ```backend``` directory.

2. Activate your virtual environment (e.g., source ```venv/bin/activate```).

3. Run the Uvicorn server:

```
uvicorn main:app --reload
```

4. Keep this terminal running. You should see it running on ```http://127.0.0.1:8000```.

**Terminal 2: Run the Frontend**

1. Navigate to the ```frontend``` directory.

2. Start a simple Python HTTP server:
```
python3 -m http.server 8001
```

3. Keep this terminal running.

**Step 3: Access the Application**

1. Open your web browser (Chrome or Edge recommended for best Speech API support).

2. Go to: ```http://127.0.0.1:8001```

3. The application should load. Upload a PDF resume and click **"Start Interview"**.

4. Your browser will ask for microphone permission. You must click **Allow**.

5. The interview will begin.


langchain==1.0.6
langchain-classic==1.0.0
langchain-community==0.4.1
langchain-core==1.0.5
langchain-google-genai
langchain-text-splitters==1.0.0
langgraph==1.0.3
langgraph-checkpoint==3.0.0
langgraph-checkpoint-sqlite==3.0.0
langgraph-prebuilt==1.0.4
langgraph-sdk==0.2.9
langsmith==0.4.42
google-api-core
google-api-python-client==2.185.0
google-auth==2.41.1
google-auth-httplib2==0.2.0
google-generativeai
googleapis-common-protos==1.71.0
grpcio
grpcio-status