import asyncio
import logging
import time
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.dispatcher.middlewares.base import BaseMiddleware
from analyzer import TextAnalyzer
from seo_parser import analyze_seo
from openai import OpenAI
from pdf_maker import generate_pdf_bytes

# ================= ЗАЩИТА ОТ СПАМА =================
class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 1.0):
        self.rate_limit = rate_limit
        self.last_request = {}

    async def __call__(self, handler, event, data):
        if not hasattr(event, 'from_user') or event.from_user is None:
            return await handler(event, data)
        if event.from_user.is_bot:
            return
        user_id = event.from_user.id
        now = time.time()
        if user_id in self.last_request:
            if now - self.last_request[user_id] < self.rate_limit:
                return
        self.last_request[user_id] = now
        return await handler(event, data)

# --- НАСТРОЙКИ ---
BOT_TOKEN = "your_telegram_bot_token_here"
MODEL_NAME = "qwen2.5:14b"

analyzer = TextAnalyzer()
local_client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
ollama_semaphore = asyncio.Semaphore(2)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.message.middleware(ThrottleMiddleware(rate_limit=1.0))
dp.callback_query.middleware(ThrottleMiddleware(rate_limit=0.5))

# ================= СОСТОЯНИЯ =================
class UserState(StatesGroup):
    waiting_for_text = State()
    waiting_for_url = State()
    waiting_for_rewrite = State()
    waiting_for_pdf_text = State()

# ================= КЛАВИАТУРЫ =================
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Анализ текста", callback_data="analyze_text")
    builder.button(text="🔗 Анализ сайта (URL)", callback_data="analyze_url")
    builder.button(text="✨ Рерайт текста", callback_data="rewrite_menu")
    builder.button(text="📄 Полный PDF-отчёт", callback_data="pdf_report")
    builder.adjust(1, 1, 1, 1)
    return builder.as_markup()

def get_rewrite_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Быстрый рерайт", callback_data="rewrite_fast")
    builder.button(text="🎯 SEO-оптимизированный", callback_data="rewrite_seo")
    builder.button(text="🔄 Главное меню", callback_data="main_menu")
    builder.adjust(1, 1)
    return builder.as_markup()

def get_back_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Главное меню", callback_data="main_menu")
    return builder.as_markup()

# ================= СТАРТ =================
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "👋 **Привет! Я ваш AI-ассистент для SEO.**\n\n"
        "Выберите действие:\n"
        "• 📊 **Анализ текста** — водность, тошнота, Ципф\n"
        "• 🔗 **Анализ сайта** — метаданные + заголовки\n"
        "• ✨ **Рерайт** — переписывание через Qwen 2.5\n"
        "• 📄 **PDF-отчёт** — скачать файл",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )

@dp.callback_query(F.data == "main_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "**Главное меню**\n\nВыберите действие:",
        reply_markup=get_main_menu(),
        parse_mode="Markdown"
    )
    await callback.answer()

# ================= ФУНКЦИЯ ДЛЯ ДЛИННЫХ СООБЩЕНИЙ =================
async def send_long_message(message: types.Message, text: str, reply_markup=None):
    """Разбивает длинное сообщение на части по 4000 символов"""
    chunk_size = 4000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    for i, chunk in enumerate(chunks):
        if i == len(chunks) - 1 and reply_markup:
            await message.answer(chunk, reply_markup=reply_markup, parse_mode="Markdown")
        else:
            await message.answer(chunk, parse_mode="Markdown")

# ================= АНАЛИЗ ТЕКСТА =================
@dp.callback_query(F.data == "analyze_text")
async def start_text_analysis(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📝 **Отправьте текст для SEO-анализа**\n\nМинимум 50 символов.",
        reply_markup=get_back_menu(),
        parse_mode="Markdown"
    )
    await state.set_state(UserState.waiting_for_text)
    await callback.answer()

@dp.message(UserState.waiting_for_text)
async def process_text_analysis(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 50:
        await message.answer("️ Текст слишком короткий. Нужно минимум 50 символов.", reply_markup=get_back_menu())
        return

    progress_msg = await message.answer("⏳ **Анализирую текст...**")
    
    try:
        result = await asyncio.to_thread(analyzer.analyze, text)
        await progress_msg.delete()
        
        report = (
            f"📊 **РЕЗУЛЬТАТЫ АНАЛИЗА**\n\n"
            f"📈 **Оценка:** {result['quality']['score']}/100 — {result['quality']['verdict']}\n\n"
            f"📖 **Читаемость:** {result['readability']['score']}/100\n"
            f"Уровень: {result['readability']['level']}\n"
            f"Слов/предл: {result['readability']['stats']['avg_words_per_sentence']} (норма: 12-15)\n"
            f"Слогов/слово: {result['readability']['stats']['avg_syllables_per_word']} (норма: 2.2-2.5)\n\n"
            f"💧 **Водность:** {result['metrics']['water_percent']}% (норма: до 60%)\n"
            f"🔥 **Заспамленность:** {result['metrics']['spam_percent']}% (норма: до 50%)\n"
            f"📈 **Акад. тошнота:** {result['metrics']['academic_toxicity']}% (норма: до 9%)\n"
            f"📉 **Класс. тошнота:** {result['metrics']['classic_toxicity']} (норма: до 10)\n"
            f"📐 **Ципф:** {result['zipf']['status']} (отклонение: {result['zipf']['deviation']}%)\n\n"
            f"📊 Символов: {result['stats']['total_chars']} | Слов: {result['stats']['total_words']} | Уникальных: {result['stats']['unique_words']}\n"
        )
        
        pw = result['problem_words']
        if pw['spam_words'] or pw['water_words'] or pw['mixed_words']:
            report += "\n️ **Проблемные слова:**\n"
            if pw['spam_words']:
                report += f"🔴 Переспам: {', '.join(pw['spam_words'][:5])}{'...' if len(pw['spam_words']) > 5 else ''}\n"
            if pw['water_words']:
                report += f"🟡 Вода: {', '.join(pw['water_words'][:5])}{'...' if len(pw['water_words']) > 5 else ''}\n"
            if pw['mixed_words']:
                report += f"🔵 Смешанные: {', '.join(pw['mixed_words'][:5])}{'...' if len(pw['mixed_words']) > 5 else ''}\n"
        
        if result['quality']['issues']:
            report += "\n⚡ **Рекомендации:**\n"
            for issue in result['quality']['issues'][:5]:
                report += f"• {issue}\n"
        
        await state.update_data(analysis_text=text, analysis_result=result)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✨ Сделать рерайт", callback_data="rewrite_from_analysis")
        builder.button(text=" Скачать PDF", callback_data="pdf_from_analysis")
        builder.button(text="🔄 Главное меню", callback_data="main_menu")
        builder.adjust(1, 1, 1)
        
        # Используем функцию для длинных сообщений
        await send_long_message(message, report, builder.as_markup())
        
    except Exception as e:
        logging.error(f"Ошибка анализа: {e}")
        await progress_msg.delete()
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())

# ================= АНАЛИЗ URL =================
@dp.callback_query(F.data == "analyze_url")
async def start_url_analysis(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        " **Отправьте URL сайта**\n\nНапример: `https://example.com`",
        reply_markup=get_back_menu(),
        parse_mode="Markdown"
    )
    await state.set_state(UserState.waiting_for_url)
    await callback.answer()

@dp.message(UserState.waiting_for_url)
async def process_url_analysis(message: types.Message, state: FSMContext):
    url = message.text.strip()
    if not url.startswith(('http://', 'https://')):
        await message.answer("❌ URL должен начинаться с http:// или https://", reply_markup=get_back_menu())
        return
    
    progress_msg = await message.answer("⏳ **Анализирую сайт...**")
    
    try:
        seo_data = await asyncio.to_thread(analyze_seo, url)
        
        if seo_data.get('status') == 'error':
            await progress_msg.delete()
            await message.answer(f"❌ Ошибка: {seo_data.get('error')}", reply_markup=get_back_menu())
            await state.clear()
            return
        
        text = seo_data.get('page_text', '')
        if len(text.strip()) < 50:
            await progress_msg.delete()
            await message.answer("⚠️ На странице слишком мало текста.", reply_markup=get_back_menu())
            await state.clear()
            return
        
        analysis = await asyncio.to_thread(analyzer.analyze, text)
        meta = seo_data
        
        title_len = meta.get('Title_length', 0) or 0
        title_status = "✅" if 30 <= title_len <= 65 else ("⚠️" if title_len > 0 else "❌")
        desc_len = meta.get('Meta_description_length', 0) or 0
        desc_status = "✅" if 120 <= desc_len <= 230 else ("⚠️" if desc_len > 0 else "❌")
        
        report = (
            f"📋 **АНАЛИЗ САЙТА**\n🔗 `{url[:50]}...`\n\n"
            f"**📋 Метаданные:**\n"
            f"{title_status} **Title:** {title_len} симв. (норма: 30-65)\n"
            f"_{meta.get('Title', '—')}_\n\n"
            f"{desc_status} **Description:** {desc_len} симв. (норма: 120-230)\n"
            f"_{meta.get('Meta description', '—')}_\n\n"
        )
        
        if meta.get('Meta keywords'):
            report += f"🏷️ **Keywords:** {meta['Meta keywords']}\n\n"
        else:
            report += "⚠️ **Keywords:** не указаны\n\n"
        
        headings = meta.get('Headings', {})
        if headings:
            report += "**📑 Заголовки:**\n"
            if headings.get('H1'):
                for h1 in headings['H1']:
                    report += f"**H1:** {h1}\n"
            for level in range(2, 7):
                tag = f'H{level}'
                if headings.get(tag):
                    indent = "  " * (level - 1)
                    for h in headings[tag]:
                        report += f"{indent}└─ **{tag}:** {h}\n"
            report += "\n"
        
        report += (
            f"**📊 SEO-метрики:**\n"
            f"• Качество: {analysis['quality']['score']}/100\n"
            f"• 💧 Водность: {analysis['metrics']['water_percent']}% (норма: до 60%)\n"
            f"• 🔥 Заспамленность: {analysis['metrics']['spam_percent']}% (норма: до 50%)\n"
            f"• 📈 Акад. тошнота: {analysis['metrics']['academic_toxicity']}% (норма: до 9%)\n"
            f"• 📉 Класс. тошнота: {analysis['metrics']['classic_toxicity']} (норма: до 10)\n"
            f"• 📐 Ципф: {analysis['zipf']['status']}\n"
        )
        
        await state.update_data(url_text=text, url_analysis=analysis, url_meta=meta)
        
        await progress_msg.delete()
        
        builder = InlineKeyboardBuilder()
        builder.button(text="✨ Сделать рерайт", callback_data="rewrite_from_url")
        builder.button(text="📄 Скачать PDF", callback_data="pdf_from_url")
        builder.button(text="🔄 Главное меню", callback_data="main_menu")
        builder.adjust(1, 1, 1)
        
        await send_long_message(message, report, builder.as_markup())
        
    except Exception as e:
        logging.error(f"Ошибка URL: {e}")
        await progress_msg.delete()
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())
        await state.clear()

# ================= РЕРАЙТ (ОБЩИЙ БЛОК) =================
async def perform_rewrite(text: str, mode: str = "seo"):
    word_count = len(text.split())
    prompt = f"""<|im_start|>system
Ты — профессиональный SEO-копирайтер. Сделай качественный рерайт текста.

СТРОГИЕ ТРЕБОВАНИЯ:
1. Сохрани ПОЛНЫЙ объем текста. Количество слов должно быть примерно таким же ({word_count} слов).
2. НЕ сокращай текст, НЕ убирай детали.
3. Сохрани смысл и структуру.
4. Измени лексику, чтобы текст стал уникальным.
5. Верни ТОЛЬКО готовый текст.
<|im_end|>
<|im_start|>user
{text}
<|im_end|>
<|im_start|>assistant"""

    async with ollama_semaphore:
        response = await asyncio.to_thread(
            local_client.chat.completions.create,
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=4096,
            stream=False
        )
    
    return response.choices[0].message.content.strip().replace("</s>", "")

# ================= РЕРАЙТ ИЗ URL =================
@dp.callback_query(F.data == "rewrite_from_url")
async def rewrite_from_url(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('url_text', '')
    if not text:
        await callback.answer("❌ Данные устарели", show_alert=True)
        return
    
    progress_msg = await callback.message.answer("⏳ **Qwen 2.5 пишет рерайт...**")
    
    try:
        rewritten = await perform_rewrite(text)
        new_analysis = await asyncio.to_thread(analyzer.analyze, rewritten)
        
        await progress_msg.delete()
        
        preview = rewritten[:1000] + "..." if len(rewritten) > 1000 else rewritten
        
        report = (
            f"✅ **Рерайт завершен!**\n\n"
            f"**📝 Новый текст (preview):**\n_{preview}_\n\n"
            f"**📊 Метрики:**\n"
            f"• Водность: {new_analysis['metrics']['water_percent']}%\n"
            f"• Заспамленность: {new_analysis['metrics']['spam_percent']}%\n"
            f"• Качество: {new_analysis['quality']['score']}/100\n\n"
            f" **Объем:** {len(rewritten)} символов"
        )
        
        await state.update_data(rewritten_text=rewritten)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Отправить полный текст", callback_data="copy_rewritten")
        builder.button(text="📄 Скачать PDF", callback_data="pdf_from_rewritten")
        builder.button(text="🔄 Главное меню", callback_data="main_menu")
        builder.adjust(1, 1, 1)
        
        await callback.message.answer(report, reply_markup=builder.as_markup(), parse_mode="Markdown")
        
    except Exception as e:
        await progress_msg.delete()
        await callback.message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())
    
    await callback.answer()

# ================= РЕРАЙТ ИЗ АНАЛИЗА =================
@dp.callback_query(F.data == "rewrite_from_analysis")
async def rewrite_from_analysis(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('analysis_text', '')
    if not text:
        await callback.answer("❌ Данные устарели", show_alert=True)
        return
    
    progress_msg = await callback.message.answer("⏳ **Qwen 2.5 пишет рерайт...**")
    
    try:
        rewritten = await perform_rewrite(text)
        new_analysis = await asyncio.to_thread(analyzer.analyze, rewritten)
        
        await progress_msg.delete()
        
        preview = rewritten[:1000] + "..." if len(rewritten) > 1000 else rewritten
        
        report = (
            f"✅ **Рерайт завершен!**\n\n"
            f"**📝 Новый текст (preview):**\n_{preview}_\n\n"
            f"**📊 Метрики:**\n"
            f"• Водность: {new_analysis['metrics']['water_percent']}%\n"
            f"• Заспамленность: {new_analysis['metrics']['spam_percent']}%\n"
            f"• Качество: {new_analysis['quality']['score']}/100\n\n"
            f" **Объем:** {len(rewritten)} символов"
        )
        
        await state.update_data(rewritten_text=rewritten)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Отправить полный текст", callback_data="copy_rewritten")
        builder.button(text="📄 Скачать PDF", callback_data="pdf_from_rewritten")
        builder.button(text="🔄 Главное меню", callback_data="main_menu")
        builder.adjust(1, 1, 1)
        
        await callback.message.answer(report, reply_markup=builder.as_markup(), parse_mode="Markdown")
        
    except Exception as e:
        await progress_msg.delete()
        await callback.message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())
    
    await callback.answer()

# ================= МЕНЮ РЕРАЙТА =================
@dp.callback_query(F.data == "rewrite_menu")
async def show_rewrite_menu(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "✨ **Выберите тип рерайта:**\n\n"
        "🔄 **Быстрый** — простое перефразирование\n"
        "🎯 **SEO-оптимизированный** — с улучшением метрик",
        reply_markup=get_rewrite_menu(),
        parse_mode="Markdown"
    )
    await state.set_state(UserState.waiting_for_rewrite)
    await callback.answer()

@dp.callback_query(F.data.in_({"rewrite_fast", "rewrite_seo"}))
async def rewrite_type_selected(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(rewrite_type=callback.data)
    await callback.message.answer(
        "📝 **Отправьте текст для рерайта**\n\nМинимум 20 символов.",
        reply_markup=get_back_menu()
    )
    await callback.answer()

@dp.message(UserState.waiting_for_rewrite)
async def process_rewrite(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 20:
        await message.answer("⚠️ Текст слишком короткий.", reply_markup=get_back_menu())
        return
    
    data = await state.get_data()
    rewrite_type = data.get('rewrite_type', 'rewrite_fast')
    
    progress_msg = await message.answer("⏳ **Qwen 2.5 пишет рерайт...**")
    
    try:
        rewritten = await perform_rewrite(text)
        new_analysis = await asyncio.to_thread(analyzer.analyze, rewritten)
        
        await progress_msg.delete()
        
        preview = rewritten[:1000] + "..." if len(rewritten) > 1000 else rewritten
        
        report = (
            f"✅ **Рерайт завершен!**\n\n"
            f"**📝 Новый текст (preview):**\n_{preview}_\n\n"
            f"**📊 Метрики:**\n"
            f"• Качество: {new_analysis['quality']['score']}/100\n"
            f"• Водность: {new_analysis['metrics']['water_percent']}%\n"
            f"• Заспамленность: {new_analysis['metrics']['spam_percent']}%\n"
            f"• Читаемость: {new_analysis['readability']['score']}/100\n\n"
            f"📏 **Объем:** {len(rewritten)} символов"
        )
        
        await state.update_data(rewritten_text=rewritten)
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📋 Отправить полный текст", callback_data="copy_rewritten")
        builder.button(text=" Скачать PDF", callback_data="pdf_from_rewritten")
        builder.button(text="🔄 Главное меню", callback_data="main_menu")
        builder.adjust(1, 1, 1)
        
        await message.answer(report, reply_markup=builder.as_markup(), parse_mode="Markdown")
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка рерайта: {e}")
        await progress_msg.delete()
        await message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())
        await state.clear()

# ================= КОПИРОВАНИЕ =================
@dp.callback_query(F.data == "copy_rewritten")
async def copy_rewritten(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('rewritten_text', '')
    if not text:
        await callback.answer("❌ Текст не найден", show_alert=True)
        return
    
    chunk_size = 4000
    chunks = [text[i:i+chunk_size] for i in range(0, len(text), chunk_size)]
    
    await callback.answer(f"✅ Отправляю текст ({len(chunks)} сообщ.)!")
    
    for i, chunk in enumerate(chunks, 1):
        await callback.message.answer(f"**Часть {i}/{len(chunks)}:**\n\n{chunk}", parse_mode="Markdown")

# ================= PDF: ИЗ ГЛАВНОГО МЕНЮ =================
@dp.callback_query(F.data == "pdf_report")
async def pdf_report_info(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📄 **Генерация PDF-отчёта**\n\nОтправьте текст (минимум 50 символов), и я создам PDF-файл.",
        reply_markup=get_back_menu(),
        parse_mode="Markdown"
    )
    await state.set_state(UserState.waiting_for_pdf_text)
    await callback.answer()

@dp.message(UserState.waiting_for_pdf_text)
async def process_pdf_from_text(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if len(text) < 50:
        await message.answer("️ Текст слишком короткий.", reply_markup=get_back_menu())
        return
    
    progress_msg = await message.answer("📄 **Генерирую PDF...**")
    
    try:
        analysis = await asyncio.to_thread(analyzer.analyze, text)
        pdf_bytes = generate_pdf_bytes(text, analysis)
        pdf_bytes.seek(0)
        
        await progress_msg.delete()
        
        await message.answer_document(
            document=BufferedInputFile(pdf_bytes.read(), filename="seo_report.pdf"),
            caption="📄 **Ваш PDF-отчёт готов!**"
        )
        await state.clear()
        
    except Exception as e:
        logging.error(f"Ошибка PDF: {e}")
        await progress_msg.delete()
        await message.answer(f"❌ Ошибка генерации PDF: {str(e)}", reply_markup=get_back_menu())
        await state.clear()

# ================= PDF: ИЗ АНАЛИЗА URL =================
@dp.callback_query(F.data == "pdf_from_url")
async def pdf_from_url(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('url_text', '')
    analysis = data.get('url_analysis')
    meta = data.get('url_meta')
    
    if not text or not analysis:
        await callback.answer("❌ Данные устарели", show_alert=True)
        return
    
    progress_msg = await callback.message.answer("📄 **Создаю PDF-файл...**")
    
    try:
        pdf_bytes = generate_pdf_bytes(text, analysis, seo_meta=meta)
        pdf_bytes.seek(0)
        
        await progress_msg.delete()
        
        await callback.message.answer_document(
            document=BufferedInputFile(pdf_bytes.read(), filename="seo_report.pdf"),
            caption="📄 **PDF-отчёт по сайту готов!**"
        )
        
    except Exception as e:
        await progress_msg.delete()
        await callback.message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())
    
    await callback.answer()

# ================= PDF: ИЗ АНАЛИЗА ТЕКСТА =================
@dp.callback_query(F.data == "pdf_from_analysis")
async def pdf_from_analysis(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('analysis_text', '')
    analysis = data.get('analysis_result')
    
    if not text or not analysis:
        await callback.answer("❌ Данные устарели", show_alert=True)
        return
    
    progress_msg = await callback.message.answer("📄 **Создаю PDF-файл...**")
    
    try:
        pdf_bytes = generate_pdf_bytes(text, analysis)
        pdf_bytes.seek(0)
        
        await progress_msg.delete()
        
        await callback.message.answer_document(
            document=BufferedInputFile(pdf_bytes.read(), filename="seo_report.pdf"),
            caption=" **PDF-отчёт готов!**"
        )
        
    except Exception as e:
        await progress_msg.delete()
        await callback.message.answer(f" Ошибка: {str(e)}", reply_markup=get_back_menu())
    
    await callback.answer()

# ================= PDF: ИЗ РЕРАЙТА =================
@dp.callback_query(F.data == "pdf_from_rewritten")
async def pdf_from_rewritten(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    text = data.get('rewritten_text', '')
    
    if not text:
        await callback.answer("❌ Текст не найден", show_alert=True)
        return
    
    progress_msg = await callback.message.answer("📄 **Создаю PDF-файл...**")
    
    try:
        analysis = await asyncio.to_thread(analyzer.analyze, text)
        pdf_bytes = generate_pdf_bytes(text, analysis)
        pdf_bytes.seek(0)
        
        await progress_msg.delete()
        
        await callback.message.answer_document(
            document=BufferedInputFile(pdf_bytes.read(), filename="seo_report_rewritten.pdf"),
            caption="📄 **PDF-отчёт по рерайту готов!**"
        )
        
    except Exception as e:
        await progress_msg.delete()
        await callback.message.answer(f"❌ Ошибка: {str(e)}", reply_markup=get_back_menu())
    
    await callback.answer()

# ================= ЗАПУСК =================
async def main():
    print("🚀 SEO Analyzer Bot запущен локально!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())