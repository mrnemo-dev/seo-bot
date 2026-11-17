import io
import os
from datetime import datetime
from fpdf import FPDF


class SEOPDF(FPDF):
    def __init__(self):
        super().__init__()
        font_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'arial.ttf')
        if os.path.exists(font_path):
            self.add_font('Arial', '', font_path, uni=True)
            self.add_font('Arial', 'B', font_path, uni=True)
            self.add_font('Arial', 'I', font_path, uni=True)
            self._no_custom_font = False
        else:
            self._no_custom_font = True
        self.first_page = True

    def _font(self, style='', size=10):
        if self._no_custom_font:
            self.set_font("Helvetica", style, size)
        else:
            self.set_font('Arial', style, size)

    def header(self):
        if self.first_page:
            self._font('B', 16)
            self.cell(0, 10, 'SEO Анализ Текста', new_x="LMARGIN", new_y="NEXT", align='C')
            self.ln(5)
            self.first_page = False

    def footer(self):
        self.set_y(-15)
        self._font('I', 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f'SEO Analyzer | Страница {self.page_no()}', align='C')
        self.set_text_color(0, 0, 0)

    def section_title(self, title):
        self._font('B', 14)
        self.set_fill_color(102, 126, 234)
        self.set_text_color(255, 255, 255)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT", fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(5)

    def metric_row(self, label, value, description=""):
        self._font('B', 11)
        self.cell(90, 8, label)
        self._font('', 11)
        self.cell(0, 8, str(value), new_x="LMARGIN", new_y="NEXT")
        if description:
            self._font('I', 9)
            self.set_text_color(100, 100, 100)
            self.cell(0, 6, description, new_x="LMARGIN", new_y="NEXT")
            self.set_text_color(0, 0, 0)
        self.ln(3)


def generate_pdf_bytes(text: str, analysis: dict, seo_meta: dict = None) -> io.BytesIO:
    """Генерирует PDF и возвращает BytesIO объект"""
    pdf = SEOPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf._font('', 10)
    
    pdf.cell(0, 8, f'Дата анализа: {datetime.now().strftime("%d.%m.%Y %H:%M")}', new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f'Количество символов: {analysis["stats"]["total_chars"]}', new_x="LMARGIN", new_y="NEXT")
    
    if seo_meta:
        pdf.ln(8)
        pdf.section_title('SEO метаданные страницы')
        pdf._font('B', 11); pdf.cell(0, 8, 'URL:', new_x="LMARGIN", new_y="NEXT")
        pdf._font('', 9); pdf.multi_cell(0, 5, seo_meta.get('url', '—')); pdf.ln(3)
        
        t_len = seo_meta.get('Title_length', 0) or 0
        t_status = ' ❌ Отсутствует' if t_len == 0 else (f' ⚠️ {t_len} симв. (норма: 30-65)' if t_len < 30 or t_len > 65 else f' ✅ {t_len} симв.')
        pdf._font('B', 11); pdf.cell(0, 8, 'Title:', new_x="LMARGIN", new_y="NEXT")
        pdf._font('', 9)
        pdf.set_text_color(220 if '❌' in t_status else (255 if '⚠️' in t_status else 40),
                          53 if '❌' in t_status else (193 if '️' in t_status else 167),
                          69 if '❌' in t_status else (7 if '⚠️' in t_status else 69))
        pdf.multi_cell(0, 5, (seo_meta.get('Title', '') or '—') + t_status)
        pdf.set_text_color(0, 0, 0); pdf.ln(3)
        
        d_len = seo_meta.get('Meta_description_length', 0) or 0
        d_status = '  Отсутствует' if d_len == 0 else (f' ⚠️ {d_len} симв. (норма: 120-230)' if d_len < 120 or d_len > 230 else f' ✅ {d_len} симв.')
        pdf._font('B', 11); pdf.cell(0, 8, 'Description:', new_x="LMARGIN", new_y="NEXT")
        pdf._font('', 9)
        pdf.set_text_color(220 if '' in d_status else (255 if '⚠️' in d_status else 40),
                          53 if '❌' in d_status else (193 if '⚠️' in d_status else 167),
                          69 if '❌' in d_status else (7 if '⚠️' in d_status else 69))
        pdf.multi_cell(0, 5, (seo_meta.get('Meta description', '') or '—') + d_status)
        pdf.set_text_color(0, 0, 0); pdf.ln(3)

        if seo_meta.get('Meta keywords'):
            pdf._font('B', 11); pdf.cell(0, 8, 'Keywords:', new_x="LMARGIN", new_y="NEXT")
            pdf._font('', 9); pdf.multi_cell(0, 5, seo_meta['Meta keywords']); pdf.ln(3)

        if seo_meta.get('Headings'):
            pdf.ln(3)
            pdf._font('B', 11); pdf.cell(0, 8, 'Структура заголовков:', new_x="LMARGIN", new_y="NEXT")
            pdf._font('', 9)
            h = seo_meta['Headings']
            if h.get('H1'):
                for t in h['H1']:
                    pdf._font('B', 9); pdf.cell(0, 6, f'H1: {t}', new_x="LMARGIN", new_y="NEXT")
            for level in range(2, 7):
                if h.get(f'H{level}'):
                    indent = '  ' * (level - 1)
                    pdf._font('', 9)
                    for t in h[f'H{level}']:
                        pdf.cell(0, 6, f'{indent}└─ H{level}: {t}', new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)

    pdf.section_title('Общая оценка качества')
    pdf._font('B', 20); pdf.cell(0, 15, f'{analysis["quality"]["score"]} / 100', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf._font('', 12); pdf.cell(0, 10, analysis["quality"]["verdict"], new_x="LMARGIN", new_y="NEXT", align='C'); pdf.ln(10)
    
    pdf.section_title('Индекс читаемости')
    pdf.metric_row('Балл:', analysis['readability']['score'])
    pdf._font('B', 11); pdf.cell(90, 8, 'Уровень:'); pdf._font('', 11); pdf.multi_cell(0, 6, analysis['readability']['level']); pdf.ln(3)
    pdf.metric_row('Среднее слов в предл.:', analysis['readability']['stats']['avg_words_per_sentence'], '(норма: 12-15)')
    pdf.metric_row('Среднее слогов на слово:', analysis['readability']['stats']['avg_syllables_per_word'], '(норма: 2.2-2.5)'); pdf.ln(5)
    pdf._font('I', 10); pdf.multi_cell(0, 6, analysis['readability']['recommendation']); pdf.ln(10)
    
    pdf.section_title('SEO-метрики текста')
    pdf.metric_row('Водность:', f'{analysis["metrics"]["water_percent"]}%', 'Норма: до 55-60%')
    pdf.metric_row('Заспамленность:', f'{analysis["metrics"]["spam_percent"]}%', 'Норма: до 50%')
    pdf.metric_row('Акад. тошнота:', f'{analysis["metrics"]["academic_toxicity"]}%', 'Норма: до 8-9%')
    pdf.metric_row('Класс. тошнота:', analysis['metrics']['classic_toxicity'], 'Норма: до 7-10')
    pdf.metric_row('Закон Ципфа:', analysis['zipf']['status'], f'Отклонение: {analysis["zipf"]["deviation"]}%'); pdf.ln(10)
    
    pdf.section_title('Проблемные слова')
    pw = analysis['problem_words']
    
    pdf._font('I', 9)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 6, '🔴 Переспам    Вода   🔵 Смешанные алфавиты', new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(3)
    
    pdf._font('B', 10)
    pdf.cell(0, 8, f"🔴 Переспам ({len(pw['spam_words'])} слов):", new_x="LMARGIN", new_y="NEXT")
    pdf._font('', 10)
    pdf.multi_cell(0, 6, ', '.join(pw['spam_words']) if pw['spam_words'] else 'Не обнаружено')
    pdf.ln(2)
    
    pdf._font('B', 10)
    pdf.cell(0, 8, f"🟡 Вода ({len(pw['water_words'])} слов):", new_x="LMARGIN", new_y="NEXT")
    pdf._font('', 10)
    water_display = ', '.join(pw['water_words'][:15]) + ('...' if len(pw['water_words']) > 15 else '')
    pdf.multi_cell(0, 6, water_display if water_display else 'Не обнаружено')
    pdf.ln(2)
    
    pdf._font('B', 10)
    pdf.cell(0, 8, f"🔵 Смешанные алфавиты ({len(pw['mixed_words'])} слов):", new_x="LMARGIN", new_y="NEXT")
    pdf._font('', 10)
    mixed_display = ', '.join(pw['mixed_words'][:15]) + ('...' if len(pw['mixed_words']) > 15 else '')
    pdf.multi_cell(0, 6, mixed_display if mixed_display else 'Не обнаружено')
    pdf.ln(8)
    
    pdf.section_title('Топ-20 слов')
    pdf._font('', 10)
    for i, item in enumerate(analysis['top_words'], 1):
        pdf.cell(10, 6, f'{i}.'); pdf.cell(60, 6, item['word']); pdf.cell(0, 6, f'{item["count"]} раз ({item["percent"]}%)', new_x="LMARGIN", new_y="NEXT")
    pdf.ln(10)
    
    pdf.section_title('Замечания')
    pdf._font('', 10)
    for issue in analysis['quality']['issues']:
        pdf.cell(5, 6, '•'); pdf.multi_cell(0, 6, issue); pdf.ln(2)
    
    pdf_buffer = io.BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)
    return pdf_buffer