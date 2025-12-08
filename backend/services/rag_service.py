from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
# from langchain_classic.chains import RetrievalQA  
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from langchain_classic.chains import create_retrieval_chain  
from langchain_classic.chains.combine_documents import create_stuff_documents_chain
import os

from dotenv import load_dotenv
import pathlib
current_dir = pathlib.Path(__file__).parent
env_path = current_dir.parent.parent / '.env'

# 2. Load the .env file
load_dotenv(dotenv_path=env_path)

# 3. Now you can access the variable


def create_rag_chain(company_facts: str):
    """
    Creates a RAG (Retrieval-Augmented Generation) chain from company facts.
    """
    if not company_facts:
        return None

    # 1. Split the company facts into manageable chunks
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    # Wrap in Document objects, which LangChain expects
    documents = [Document(page_content=chunk) for chunk in text_splitter.split_text(company_facts)]
    
    if not documents:
        return None

    # 2. Create embeddings
    api_key = os.getenv("GOOGLE_API_KEY")
    print("Creating embeddings for RAG...",api_key)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", task_type="retrieval_document",google_api_key = api_key)
    # 3. Create a FAISS vector store
    # print(documents)
    try:
        vector_store = FAISS.from_texts([doc.page_content for doc in documents], embeddings)
    except Exception as e:
        error_msg = str(e)
        print(f"Error creating FAISS vector store: {e}")
        
        # Check for quota errors
        if "429" in error_msg or "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
            print("⚠️ WARNING: API quota exceeded for embeddings. RAG context will be empty.")
            print("   The interview will continue without company-specific context.")
            return None
        
        # Check for API key errors
        if "API_KEY" in error_msg or "api key" in error_msg.lower():
            print("This may be due to an invalid or missing Google API Key.")
        
        return None

    # 4. Create the LLM for the chain
    # --- MODIFIED: Corrected model name ---
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
    
    # 5. Create the RAG chain
    # --- MODIFIED: Replaced deprecated RetrievalQA with create_retrieval_chain ---
    
    # This is the prompt template that will be "stuffed" with context
    prompt = ChatPromptTemplate.from_template(
        """Answer the following question based only on the provided context:

        <context>
        {context}
        </context>

        Question: {input}"""
    )

    # This chain handles "stuffing" the documents into the prompt
    # Create a RetrievalQA chain that retrieves documents then runs the LLM with the "stuff" chain_type
    document_chain = create_stuff_documents_chain(llm, prompt)
    
    # This is the full chain that:
    # 1. Takes the "input" (question)
    # 2. Passes it to the retriever
    # 3. Passes the (input, context) to the document_chain
    retriever = vector_store.as_retriever(search_kwargs={"k": 2})
    rag_chain = create_retrieval_chain(retriever, document_chain)
    print("RAG chain created successfully.")
    
    return rag_chain
def query_rag_chain(rag_chain, query: str) -> str:
    """
    Queries the RAG chain and returns the AI-generated answer.
    """
    if rag_chain is None:
        print("RAG chain is not initialized.")
        return ""
        # --- MODIFIED: Use new input/output keys ---
    try:
        # Run the RetrievalQA chain directly and return the string result
        res = rag_chain.invoke({"input": query})
        return res["answer"]
        
    except Exception as e:
        print(f"Error querying RAG chain: {e}")
        return ""