import logging
import tempfile
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.database import get_session
from backend.models import WebUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pitchdeck", tags=["pitchdeck"])

def parse_pdf_text(file_path: str) -> str:
    """Извлекает текст из PDF-файла используя PyMuPDF (fitz)"""
    try:
        import fitz # PyMuPDF
        doc = fitz.open(file_path)
        text_content = []
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text_content.append(page.get_text("text"))
        doc.close()
        return "\n".join(text_content)
    except Exception as e:
        logger.error(f"Failed to parse PDF with PyMuPDF: {e}")
        # Фолбэк на pdfplumber, если PyMuPDF не сработал
        try:
            import pdfplumber
            text_content = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if text:
                        text_content.append(text)
            return "\n".join(text_content)
        except Exception as e2:
            logger.error(f"Failed to parse PDF with pdfplumber: {e2}")
            return ""


@router.post("/analyze")
async def analyze_pitchdeck(
    file: UploadFile = File(...), 
    session: AsyncSession = Depends(get_session)
):
    """
    Загрузка PDF презентации (Pitch Deck) для анализа.
    Извлекает текст и прогоняет через RAG (заглушка для LLM-анализа).
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
        
    # 1. Сохраняем загруженный файл во временный файл
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save uploaded file")

    # 2. Парсим текст из PDF
    try:
        extracted_text = parse_pdf_text(tmp_path)
        
        # Удаляем временный файл
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
            
        if not extracted_text.strip():
            raise HTTPException(status_code=400, detail="Could not extract text from the PDF. It might be scanned images.")
            
        # 3. Здесь будет RAG анализ текста через LLM
        # Для начала возвращаем базовую статистику по тексту
        
        word_count = len(extracted_text.split())
        
        return {
            "status": "success",
            "filename": file.filename,
            "text_length": len(extracted_text),
            "word_count": word_count,
            "message": "PDF успешно распарсен. Интеграция с RAG/LLM в разработке.",
            # Возвращаем первые 500 символов для превью
            "preview": extracted_text[:500] + ("..." if len(extracted_text) > 500 else "")
        }
        
    except Exception as e:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        logger.error(f"Error analyzing pitchdeck: {e}")
        raise HTTPException(status_code=500, detail=str(e))
