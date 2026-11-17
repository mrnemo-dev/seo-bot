from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from analyzer import TextAnalyzer
from fpdf import FPDF
from datetime import datetime
import os, httpx, io, re, sys, threading, matplotlib, uvicorn
import matplotlib.pyplot as plt
from matplotlib import rcParams
from openai import OpenAI

from seo_parser import analyze_seo

matplotlib.use('Agg')
app = FastAPI(title="SEO Text Analyzer API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(base_path, "static")), name="static")

analyzer = TextAnalyzer()

class TextRequest(BaseModel):
    text: str
    include_zipf_details: Optional[bool] = True
    seo_url: Optional[str] = None
    seo_title: Optional[str] = None
    seo_title_length: Optional[int] = None
    seo_description: Optional[str] = None
    seo_description_length: Optional[int] = None
    seo_keywords: Optional[str] = None
    seo_canonical: Optional[str] = None
    seo_headings: Optional[dict] = None

class RewriteRequest(BaseModel):
    text: str

def fix_mixed_alphabet_words(text):
    words = text.split()
    latin_to_cyrillic = {'A': 'А', 'B': 'В', 'C': 'С', 'E': 'Е', 'H': 'Н', 'K': 'К', 'M': 'М', 'O': 'О', 'P': 'Р', 'T': 'Т', 'X': 'Х', 'Y': 'У', 'a': 'а', 'c': 'с', 'e': 'е', 'o': 'о', 'p': 'р', 'x': 'х', 'y': 'у'}
    fixed = []
    for word in words:
        if bool(re.search(r'[а-яё]', word.lower())) and bool(re.search(r'[a-z]', word.lower())):
            if word[0].isascii() and word[0].isalpha() and word[0] in latin_to_cyrillic:
                word = latin_to_cyrillic[word[0]] + word[1:]
        fixed.append(word)
    return ' '.join(fixed)

@app.get("/", response_class=FileResponse)
async def root():
    path = os.path.join(sys._MEIPASS, "static", "index.html") if getattr(sys, 'frozen', False) else "static/index.html"
    return FileResponse(path)

# ================= ЛОКАЛЬНЫЙ РЕРАЙТ (Qwen 2.5 14B) =================
# Инициализация локального клиента (порт 11434 — стандарт для Ollama)
# Если вы используете LM Studio, замените 11434 на 1234
local_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")

@app.post("/rewrite/local")
async def rewrite_text_local(request: RewriteRequest):
    if len(request.text.strip()) < 20:
        raise HTTPException(status_code=400, detail="Текст слишком короткий")
    
    try:
        model_name = "qwen2.5:14b" 
        
        # Специальный промпт в формате ChatML для Qwen 2.5
        prompt = f"""<|im_start|>system
Ты — профессиональный редактор и копирайтер. Твоя задача — сделать качественный рерайт текста на русском языке.
Сохрани исходный смысл, факты и структуру, но полностью перепиши текст своими словами. Сделай его уникальным, читаемым и естественным.
Не добавляй вступлений, комментариев или выводов. Верни ТОЛЬКО готовый переработанный текст.
<|im_end|>
<|im_start|>user
Исходный текст:
{request.text}
<|im_end|>
<|im_start|>assistant"""

        response = local_client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2048,
            stream=False
        )
        
        rewritten_text = response.choices[0].message.content.strip()
        rewritten_text = rewritten_text.replace("</s>", "").strip()
        
        return {"success": True, "rewritten": rewritten_text, "model": f"Local Qwen ({model_name})"}
        
    except Exception as e:
        error_msg = str(e)
        if "Connection refused" in error_msg or "ConnectError" in error_msg:
            raise HTTPException(status_code=503, detail="Локальный сервер не запущен или неверный порт. Проверьте настройки программы.")
        raise HTTPException(status_code=500, detail=f"Ошибка локальной модели: {error_msg}")
# =====================================================================

@app.post("/analyze")
async def analyze_text(request: TextRequest):
    if len(request.text.strip()) < 50: 
        raise HTTPException(status_code=400, detail="Текст слишком короткий")
    result = analyzer.analyze(request.text)
    if not request.include_zipf_details: 
        result["zipf"].pop("details", None)
    return result

class SEOPDF(FPDF):
    def __init__(self):
        super().__init__()
        font_path = os.path.join(sys._MEIPASS, 'arial.ttf') if getattr(sys, 'frozen', False) else os.path.join(os.path.dirname(__file__), 'arial.ttf')
        self.add_font('Arial', '', font_path, uni=True)
        self.add_font('Arial', 'B', font_path, uni=True)
        self.add_font('Arial', 'I', font_path, uni=True)
        self.first_page = True

    def header(self):
        if self.first_page:
            self.set_font('Arial', 'B', 16)
            self.cell(0, 10, 'SEO Анализ Текста', new_x="LMARGIN", new_y="NEXT", align='C')
            self.ln(5)
            self.first_page = False

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'Разработано: SEO Analyzer Team | Страница {self.page_no()}', align='C')
        self.set_text_color(0, 0, 0)

    def section_title(self, title):
        self.set_font('Arial', 'B', 14)
        self.set_fill_color(102, 126, 234)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(5)

    def metric_row(self, label, value, description=""):
        self.set_font('Arial', 'B', 11)
        self.cell(90, 8, label)
        self.set_font('Arial', '', 11)
        self.cell(0, 8, str(value), new_x="LMARGIN", new_y="NEXT")
        if description:
            self.set_font('Arial', 'I', 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, description, new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0, 0, 0)
        self.ln(3)

@app.post("/export/pdf")
async def export_pdf(request: TextRequest):
    result = analyzer.analyze(request.text)
    pdf = SEOPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_font('Arial', '', 10)
    pdf.cell(0, 8, f'Дата анализа: {datetime.now().strftime("%d.%m.%Y %H:%M")}', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f'Количество символов: {result["stats"]["total_chars"]}', new_x="LMARGIN", new_y="NEXT")
    
    if request.seo_url:
        pdf.ln(8)
        pdf.section_title('SEO метаданные страницы')
        pdf.set_font('Arial', 'B', 11); pdf.cell(0, 8, 'URL:', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Arial', '', 9); pdf.multi_cell(0, 5, request.seo_url); pdf.ln(3)
        
        t_len = request.seo_title_length or 0
        t_status = ' ❌ Отсутствует' if t_len == 0 else (f' ⚠️ {t_len} симв. (норма: 30-65)' if t_len < 30 or t_len > 65 else f' ✅ {t_len} симв.')
        pdf.set_font('Arial', 'B', 11); pdf.cell(0, 8, 'Title:', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Arial', '', 9); pdf.set_text_color(220 if '❌' in t_status else (255 if '⚠️' in t_status else 40), 53 if '❌' in t_status else (193 if '⚠️' in t_status else 167), 69 if '❌' in t_status else (7 if '⚠️' in t_status else 69))
        pdf.multi_cell(0, 5, (request.seo_title or '—') + t_status); pdf.set_text_color(0, 0, 0); pdf.ln(3)
        
        d_len = request.seo_description_length or 0
        d_status = ' ❌ Отсутствует' if d_len == 0 else (f' ⚠️ {d_len} симв. (норма: 120-230)' if d_len < 120 or d_len > 230 else f' ✅ {d_len} симв.')
        pdf.set_font('Arial', 'B', 11); pdf.cell(0, 8, 'Description:', new_x="LMARGIN", new_y="NEXT")
        pdf.set_font('Arial', '', 9); pdf.set_text_color(220 if '❌' in d_status else (255 if '⚠️' in d_status else 40), 53 if '❌' in d_status else (193 if '⚠️' in d_status else 167), 69 if '❌' in d_status else (7 if '⚠️' in d_status else 69))
        pdf.multi_cell(0, 5, (request.seo_description or '—') + d_status); pdf.set_text_color(0, 0, 0); pdf.ln(3)

        if request.seo_keywords:
            pdf.set_font('Arial', 'B', 11); pdf.cell(0, 8, 'Keywords:', new_x="LMARGIN", new_y="NEXT")
            pdf.set_font('Arial', '', 9); pdf.multi_cell(0, 5, request.seo_keywords); pdf.ln(3)
        else:
            pdf.set_font('Arial', 'I', 9); pdf.set_text_color(100, 100, 100); pdf.cell(0, 6, 'Keywords: не указаны', new_x="LMARGIN", new_y="NEXT"); pdf.set_text_color(0, 0, 0); pdf.ln(3)

        if request.seo_headings:
            pdf.ln(3); pdf.set_font('Arial', 'B', 11); pdf.cell(0, 8, 'Структура заголовков:', new_x="LMARGIN", new_y="NEXT")
            pdf.set_font('Arial', '', 9)
            h = request.seo_headings
            if h.get('H1'):
                for t in h['H1']: pdf.set_font('Arial', 'B', 9); pdf.cell(0, 6, f'H1: {t}', new_x="LMARGIN", new_y="NEXT")
            for level in range(2, 7):
                if h.get(f'H{level}'):
                    indent = '  ' * (level - 1)
                    pdf.set_font('Arial', '', 9)
                    for t in h[f'H{level}']: pdf.cell(0, 6, f'{indent}└─ H{level}: {t}', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)

    pdf.section_title('Общая оценка качества')
    pdf.set_font('Arial', 'B', 20); pdf.cell(0, 15, f'{result["quality"]["score"]} / 100', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font('Arial', '', 12); pdf.cell(0, 10, result["quality"]["verdict"], new_x="LMARGIN", new_y="NEXT", align='C'); pdf.ln(10)
    
    pdf.section_title('Индекс читаемости')
    pdf.metric_row('Балл:', result['readability']['score'])
    pdf.set_font('Arial', 'B', 11); pdf.cell(90, 8, 'Уровень:'); pdf.set_font('Arial', '', 11); pdf.multi_cell(0, 6, result['readability']['level']); pdf.ln(3)
    pdf.metric_row('Среднее слов в предл.:', result['readability']['stats']['avg_words_per_sentence'], '(норма: 12-15)')
    pdf.metric_row('Среднее слогов на слово:', result['readability']['stats']['avg_syllables_per_word'], '(норма: 2.2-2.5)'); pdf.ln(5)
    pdf.set_font('Arial', 'I', 10); pdf.multi_cell(0, 6, result['readability']['recommendation']); pdf.ln(10)
    
    pdf.section_title('SEO-метрики текста')
    pdf.metric_row('Водность:', f'{result["metrics"]["water_percent"]}%', 'Норма: до 55-60%')
    pdf.metric_row('Заспамленность:', f'{result["metrics"]["spam_percent"]}%', 'Норма: до 50%')
    pdf.metric_row('Акад. тошнота:', f'{result["metrics"]["academic_toxicity"]}%', 'Норма: до 8-9%')
    pdf.metric_row('Класс. тошнота:', result['metrics']['classic_toxicity'], 'Норма: до 7-10')
    pdf.metric_row('Закон Ципфа:', result['zipf']['status'], f'Отклонение: {result["zipf"]["deviation"]}%'); pdf.ln(10)
    
    pdf.section_title('Проблемные слова')
    pw = result['problem_words']
    
    pdf.set_font('Arial', 'I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, '🔴 Переспам   🟡 Вода   🔵 Смешанные алфавиты', new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, f"🔴 Переспам ({len(pw['spam_words'])} слов):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Arial', '', 10)
    pdf.multi_cell(0, 6, ', '.join(pw['spam_words']) if pw['spam_words'] else 'Не обнаружено')
    pdf.ln(2)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, f"🟡 Вода ({len(pw['water_words'])} слов):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Arial', '', 10)
    water_display = ', '.join(pw['water_words'][:15]) + ('...' if len(pw['water_words']) > 15 else '')
    pdf.multi_cell(0, 6, water_display if water_display else 'Не обнаружено')
    pdf.ln(2)
    
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(0, 8, f"🔵 Смешанные алфавиты ({len(pw['mixed_words'])} слов):", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font('Arial', '', 10)
    mixed_display = ', '.join(pw['mixed_words'][:15]) + ('...' if len(pw['mixed_words']) > 15 else '')
    pdf.multi_cell(0, 6, mixed_display if mixed_display else 'Не обнаружено')
    pdf.ln(8)
    
    pdf.section_title('Топ-20 слов')
    pdf.set_font('Arial', '', 10)
    for i, item in enumerate(result['top_words'], 1):
        pdf.cell(10, 6, f'{i}.'); pdf.cell(60, 6, item['word']); pdf.cell(0, 6, f'{item["count"]} раз ({item["percent"]}%)', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    pdf.section_title('Замечания')
    pdf.set_font('Arial', '', 10)
    for issue in result['quality']['issues']: pdf.cell(5, 6, '•'); pdf.multi_cell(0, 6, issue); pdf.ln(2)
    
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    return StreamingResponse(pdf_buffer, media_type='application/pdf', headers={'Content-Disposition': 'attachment; filename=seo_report.pdf'})

@app.get("/analyze/url")
async def analyze_url(url: str = Query(..., description="URL сайта")):
    seo_data = analyze_seo(url)
    if seo_data.get('status') == 'error': raise HTTPException(status_code=400, detail=seo_data.get('error'))
    text = seo_data.get('page_text', '')
    if len(text.strip()) < 50: raise HTTPException(status_code=400, detail="Мало текста")
    return {
        "seo_meta": {"url": seo_data['url'], "title": seo_data['Title'], "title_length": seo_data.get('Title_length', 0),
                     "meta_description": seo_data['Meta description'], "meta_description_length": seo_data.get('Meta_description_length', 0),
                     "meta_keywords": seo_data.get('Meta keywords', ''), "canonical": seo_data.get('Canonical', ''), "headings": seo_data['Headings']},
        "text_analysis": analyzer.analyze(text), "page_text": text
    }

if __name__ == "__main__":
    if sys.stdout is None: sys.stdout = io.StringIO()
    if sys.stderr is None: sys.stderr = io.StringIO()
    def open_browser():
        import time, webbrowser
        time.sleep(2); webbrowser.open('http://127.0.0.1:8000/')
    threading.Thread(target=open_browser, daemon=True).start()
    print("SEO Analyzer запущен: http://127.0.0.1:8000/")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")