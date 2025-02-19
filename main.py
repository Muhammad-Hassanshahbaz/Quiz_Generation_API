from fastapi import FastAPI, HTTPException, Response, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from groq import Groq
from docx import Document
from io import BytesIO
import os
import datetime
import PyPDF2



# Initialize FastAPI app
app = FastAPI()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY is not set. Please add it to your environment variables.")

client = Groq(api_key=GROQ_API_KEY)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class QuizRequest(BaseModel):
    text: str
    num_questions: int = 10

def extract_text_from_pdf(file: UploadFile) -> str:
    """Extract text from a PDF file."""
    reader = PyPDF2.PdfFileReader(file.file)
    text = ""
    for page_num in range(reader.numPages):
        text += reader.getPage(page_num).extract_text()
    return text

def preprocess_text(text: str) -> str:
    """Pre-process text for question generation"""
    prompt = f"Normalize and simplify the following text for question generation:\n{text}"
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": "You are an expert in simplifying text for educational purposes."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        max_tokens=500
    )
    return response.choices[0].message.content.strip()

def select_sentences(text: str, num_questions: int) -> list:
    """Select important sentences for questions"""
    prompt = f"Select {num_questions} most important sentences from the following text for creating quiz questions:\n{text}"
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": f"You are an expert in identifying {num_questions} important sentences for quizzes."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=300
    )
    return response.choices[0].message.content.strip().split("\n")

def generate_question(sentence: str, question_type: str) -> str:
    """Generate a question from a sentence based on the specified type."""
    prompt = f"Create a {question_type} question from the following sentence:\n{sentence}"
    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[
            {"role": "system", "content": f"You are an expert in generating {question_type} quiz questions."},
            {"role": "user", "content": prompt}
        ],
        max_tokens=200
    )
    return response.choices[0].message.content.strip()

def generate_quiz(text: str, num_questions: int) -> list:
    """Generate full quiz with various types of questions."""
    preprocessed_text = preprocess_text(text)
    sentences = select_sentences(preprocessed_text, num_questions)
    quiz = []
    for sentence in sentences:
        # Generate different types of questions
        quiz.append(generate_question(sentence, "multiple-choice"))
        quiz.append(generate_question(sentence, "true/false"))
        quiz.append(generate_question(sentence, "question/answer"))
        quiz.append(generate_question(sentence, "fill in the blanks"))
    return quiz
 
 
def create_quiz_document(quiz: list) -> BytesIO:
    """Create DOCX in memory"""
    doc = Document()
    doc.add_heading('Generated Quiz', 0)
    
    for i, question in enumerate(quiz, 1):
        doc.add_paragraph(f"Question {i}: {question}")
        doc.add_paragraph()
    
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer

@app.post("/generate/")
async def generate_quiz_endpoint(request: QuizRequest):
    try:
        if not request.text.strip():
            raise HTTPException(status_code=400, detail="Text cannot be empty")
        if request.num_questions < 1:
            raise HTTPException(status_code=400, detail="Number of questions must be at least 1")
            
        quiz = generate_quiz(request.text, request.num_questions)
        return {"quiz": quiz}
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/download/")
async def download_quiz_endpoint(request: QuizRequest):
    try:
        quiz = generate_quiz(request.text, request.num_questions)
        buffer = create_quiz_document(quiz)
        
        filename = f"quiz_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.docx"
        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    try:
        text = extract_text_from_pdf(file)
        quiz = generate_quiz(text, 10)  # Default to 10 questions
        buffer = create_quiz_document(quiz)
        
        filename = f"quiz_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.docx"
        return Response(
            content=buffer.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def welcome():
    return {"message": "Welcome to the Quiz Generation API!"}