"""
Ядро SEO-анализа текста.
Здесь живут все алгоритмы расчета метрик: вода, спам, тошнота, закон Ципфа,
индекс читаемости и подсветка проблемных слов.
"""

# === ИМПОРТЫ: подключаем готовые инструменты ===
import re  # Регулярные выражения — для работы с текстом
import math  # Математика — для корня квадратного
import collections  # Для удобного подсчета слов
from stopwords_ru import STOP_WORDS_RU  # Наш словарь стоп-слов
import pymorphy3


# === КЛАСС: "чертеж" анализатора ===
class TextAnalyzer:
    """
    Анализатор текста для SEO-метрик.
    Умеет считать: воду, заспамленность, тошноту, закон Ципфа,
    индекс читаемости и находить проблемные слова.
    """
    
    def __init__(self, stop_words=None):
        self.stop_words = stop_words or STOP_WORDS_RU
        # Инициализируем морфологический анализатор для русского языка
        self.morph = pymorphy3.MorphAnalyzer()
    
    # === МЕТОД 1: Разбиение текста на слова ===
    @staticmethod
    def _tokenize(text):
        """
        Превращает сырой текст в список слов.
        Приводит к нижнему регистру и оставляет только буквы/цифры.
        """
        text = text.lower()
        words = re.findall(r'[а-яёa-z0-9]+', text)
        return words
    
    # === МЕТОД 2: Упрощенная стеммизация ===
    
    def _lemmatize_word(self, word):
            """
            Лемматизация: приводит слово к начальной форме (лемме).
            В отличие от стемминга (который просто отрезает окончания),
            лемматизация понимает грамматику языка.
    
            Примеры:
            - "имплантов" → "имплант"
            - "бежал" → "бежать"
            - "красивые" → "красивый"
            - "Straumann" → "straumann" (приводит к нижнему регистру)
            """
            # Приводим к нижнему регистру
            word = word.lower()
    
            # Получаем морфологический разбор
            parsed = self.morph.parse(word)
    
            # Берем первую (наиболее вероятную) форму и возвращаем лемму
            if parsed:
                return parsed[0].normal_form
    
            # Если не удалось разобрать — возвращаем слово как есть
            return word
    
    # === МЕТОД 3: Подсчёт слогов в слове (для индекса читаемости) ===
    @staticmethod
    def _count_syllables(word):
        """
        Считает количество слогов в русском слове.
        Правило: один слог = одна гласная буква.
        Пример: "ма-ши-на" → 3 слога (а, и, а)
        """
        vowels = 'аеёиоуыэюя'
        count = 0
        for char in word.lower():
            if char in vowels:
                count += 1
        return max(count, 1)
    
               # === МЕТОД 4: Индекс читаемости (Классическая формула Флеша для русского языка) ===
    def _calculate_readability(self, text):
        """
        Рассчитывает индекс удобочитаемости по адаптированной формуле для русского языка.
        """
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        
        if not sentences:
            return {"score": 0, "level": "Недостаточно данных", "recommendation": "Введите больше текста.", "stats": {}}
        
        total_syllables = 0
        total_words = 0
        
        for sentence in sentences:
            words = self._tokenize(sentence)
            if words:
                total_words += len(words)
                for word in words:
                    total_syllables += self._count_syllables(word)
        
        if total_words == 0:
            return {"score": 0, "level": "Недостаточно данных", "recommendation": "Введите больше текста.", "stats": {}}
        
        avg_words_per_sentence = total_words / len(sentences)
        avg_syllables_per_word = total_syllables / total_words
        
        # Классическая формула Флеша для русского языка (без искажающих нормализаций)
        raw_score = 206.835 - (1.3 * avg_words_per_sentence) - (60.1 * avg_syllables_per_word)
        
        # Просто ограничиваем диапазон от 0 до 100
        score = round(max(0, min(100, raw_score)), 2)
        
        # Адаптированные уровни для русского языка
        if score >= 80:
            level = "Очень легко (детский текст, простые посты)"
        elif score >= 65:
            level = "Легко (популярные статьи, новости, блоги)"
        elif score >= 50:
            level = "Средне (стандартные тексты для сайтов, деловая переписка)"
        elif score >= 35:
            level = "Сложно (научные статьи, аналитика, обзоры)"
        else:
            level = "Очень сложно (узкопрофильные, юридические или медицинские тексты)"
            
        recommendations = []
        if avg_words_per_sentence > 15:
            recommendations.append(f"📏 Предложения длинные (в среднем {avg_words_per_sentence:.1f} слов). Разбивайте их на более короткие.")
        if avg_syllables_per_word > 2.5:
            recommendations.append(f"📚 Много сложных слов (в среднем {avg_syllables_per_word:.1f} слогов). Замените термины на простые аналоги.")
        
        if not recommendations:
            recommendations.append("✅ Текст отлично сбалансирован по длине и сложности.")

        return {
            "score": score,
            "level": level,
            "recommendation": " ".join(recommendations),
            "stats": {
                "avg_words_per_sentence": round(avg_words_per_sentence, 2),
                "avg_syllables_per_word": round(avg_syllables_per_word, 2),
            }
        }
    
    # === МЕТОД 5: Получение проблемных слов для подсветки ===
    def _get_problem_words(self, text, meaningful_counts, word_counts):
        """
        Возвращает три списка слов для подсветки в интерфейсе:
        - spam_words: топ-3 самых частых значимых слов (переспам)
        - water_words: стоп-слова, которые встречаются в тексте (вода)
        - mixed_words: слова со смешанными алфавитами
        """
        spam_words = [word for word, _ in meaningful_counts.most_common(3)]
        water_words = [word for word in word_counts.keys() if word in self.stop_words]
        
        mixed_words = []
        for word in word_counts.keys():
            has_cyrillic = bool(re.search(r'[а-яё]', word))
            has_latin = bool(re.search(r'[a-z]', word))
            if has_cyrillic and has_latin:
                mixed_words.append(word)
        
        return {
            "spam_words": spam_words,
            "water_words": water_words[:30],
            "mixed_words": mixed_words,
        }
    
    # === ГЛАВНЫЙ МЕТОД: Полный анализ текста ===
    def analyze(self, text):
        """
        Главный метод: принимает текст и возвращает полный SEO-отчет.
        """
        # ШАГ 1: Разбиваем текст на слова
        words = self._tokenize(text)
        total_words = len(words)
        
        if total_words == 0:
            return {"error": "Текст пуст или не содержит слов"}
        
        # ШАГ 2: Считаем частотность каждого слова
        word_counts = collections.Counter(words)
        
        # ШАГ 3: Отделяем "воду" от значимых слов
        meaningful_words = [w for w in words if w not in self.stop_words]
        stop_words_count = total_words - len(meaningful_words)
        
        meaningful_counts = collections.Counter(meaningful_words)
        stemmed_words = [self._lemmatize_word(w) for w in meaningful_words]
        stemmed_counts = collections.Counter(stemmed_words)
        
        # ШАГ 4: Считаем метрики
        
        # 4.1. ВОДНОСТЬ
        water_percent = (stop_words_count / total_words) * 100
        
        # 4.2. ЗАСПАМЛЕННОСТЬ (формула как у TurboCheck/Advego)
        # Показывает, какой процент слов являются "лишними повторениями"
        unique_meaningful = len(meaningful_counts)
        if total_words > 0:
            spam_percent = ((total_words - unique_meaningful) / total_words) * 100 if total_words > 0 else 0
        else:
            spam_percent = 0
        
        # 4.3. АКАДЕМИЧЕСКАЯ ТОШНОТА
        if meaningful_counts:
            most_common_word, most_common_count = meaningful_counts.most_common(1)[0]
            academic_toxicity = (most_common_count / total_words) * 100
        else:
            academic_toxicity = 0
            most_common_word = ""
            most_common_count = 0
        
        # 4.4. КЛАССИЧЕСКАЯ ТОШНОТА
        classic_toxicity = math.sqrt(most_common_count) if most_common_count > 0 else 0
        
        # 4.5. ЗАКОН ЦИПФА
        zipf_analysis = self._analyze_zipf(meaningful_counts)
        
        # 4.6. ТОП-20 самых частых значимых слов
        top_words = [
            {
                "word": word,
                "count": count,
                "percent": round(count / total_words * 100, 2)
            }
            for word, count in meaningful_counts.most_common(20)
        ]
        
        # ШАГ 5: Общая оценка качества
        quality = self._evaluate_quality(
            water_percent, spam_percent,
            academic_toxicity, classic_toxicity,
            zipf_analysis["deviation"]
        )
        
        # ШАГ 6: Новые метрики — читаемость и проблемные слова
        readability = self._calculate_readability(text)
        problem_words = self._get_problem_words(text, meaningful_counts, word_counts)
        
        # ШАГ 7: Собираем финальный отчет
        return {
            "stats": {
                "total_chars": len(text),
                "total_chars_no_spaces": len(text.replace(" ", "")),
                "total_words": total_words,
                "unique_words": len(word_counts),
                "meaningful_words": len(meaningful_words),
                "unique_meaningful": unique_meaningful,
                "stop_words_count": stop_words_count,
                "sentences": len(re.findall(r'[.!?]+', text)) or 1,
            },
            "metrics": {
                "water_percent": round(water_percent, 2),
                "spam_percent": round(spam_percent, 2),
                "academic_toxicity": round(academic_toxicity, 2),
                "classic_toxicity": round(classic_toxicity, 2),
                "most_common_word": most_common_word,
                "most_common_count": most_common_count,
            },
            "readability": readability,
            "problem_words": problem_words,
            "zipf": zipf_analysis,
            "top_words": top_words,
            "quality": quality,
        }
    
    # === МЕТОД: Анализ закона Ципфа ===
    def _analyze_zipf(self, word_counts):
        """
        Проверяет, соответствует ли текст закону Ципфа.
        """
        if len(word_counts) < 3:
            return {
                "status": "Недостаточно данных",
                "deviation": 0,
                "score": 0,
                "details": []
            }
        
        sorted_words = word_counts.most_common()
        n = len(sorted_words)
        top_n = min(30, n)
        observed = [count for _, count in sorted_words[:top_n]]
        
        f1 = observed[0]
        ideal = [f1 / i for i in range(1, top_n + 1)]
        
        squared_diffs = [(o - i) ** 2 for o, i in zip(observed, ideal)]
        rmse = math.sqrt(sum(squared_diffs) / top_n)
        
        deviation = (rmse / f1) * 100 if f1 > 0 else 0
        
        if deviation < 30:
            status = "Отлично"
            score = 100
        elif deviation < 60:
            status = "Хорошо"
            score = 80
        elif deviation < 100:
            status = "Удовлетворительно"
            score = 60
        else:
            status = "Плохо (переспам или неестественный текст)"
            score = 40
        
        details = []
        for rank, (word, count) in enumerate(sorted_words[:10], start=1):
            expected = f1 / rank
            details.append({
                "rank": rank,
                "word": word,
                "observed": count,
                "expected": round(expected, 2),
                "deviation_percent": round(abs(count - expected) / expected * 100, 1) if expected > 0 else 0
            })
        
        return {
            "status": status,
            "deviation": round(deviation, 2),
            "score": score,
            "details": details,
        }
    
    # === МЕТОД: Общая оценка качества ===
    @staticmethod
    def _evaluate_quality(water, spam, acad_tox, class_tox, zipf_dev):
        """
        Считает общую оценку текста на основе всех метрик.
        """
        issues = []
        score = 100
        
        if water > 60:
            issues.append(f"Высокая водность ({water:.1f}%) — добавьте конкретики")
            score -= 20
        elif water > 55:
            issues.append(f"Повышенная водность ({water:.1f}%)")
            score -= 10
        
        if spam > 50:
            issues.append(f"Сильный переспам ({spam:.1f}%) — используйте синонимы")
            score -= 20
        elif spam > 35:
            issues.append(f"Повышенная заспамленность ({spam:.1f}%)")
            score -= 10
        
        if acad_tox > 9:
            issues.append(f"Высокая академическая тошнота ({acad_tox:.1f}%)")
            score -= 20
        elif acad_tox > 7:
            issues.append(f"Повышенная тошнота ({acad_tox:.1f}%)")
            score -= 10
        
        if class_tox > 10:
            issues.append(f"Высокая классическая тошнота ({class_tox:.1f})")
            score -= 15
        
        if zipf_dev > 100:
            issues.append(f"Сильное нарушение закона Ципфа (отклонение {zipf_dev:.1f}%)")
            score -= 15
        
        if score < 60:
            verdict = "Текст требует доработки"
        elif score < 80:
            verdict = "Текст хороший, но есть замечания"
        else:
            verdict = "Отличный текст"
        
        return {
            "score": max(score, 0),
            "verdict": verdict,
            "issues": issues if issues else ["Замечаний нет"],
        }


# === БЛОК ДЛЯ БЫСТРОГО ТЕСТА ===
if __name__ == "__main__":
    sample_text = """
    SEO-оптимизация текста — это важный процесс, который позволяет улучшить 
    видимость сайта в поисковых системах. SEO-оптимизация включает в себя 
    работу с ключевыми словами, структурой текста и его уникальностью. 
    Правильная SEO-оптимизация помогает привлечь целевую аудиторию и 
    увеличить трафик на сайт. SEO-специалисты рекомендуют соблюдать баланс 
    между оптимизацией и читаемостью текста.
    """
    
    analyzer = TextAnalyzer()
    result = analyzer.analyze(sample_text)
    
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    print("\n" + "=" * 60)
    print("📖 ИНДЕКС ЧИТАЕМОСТИ:")
    print(f"   Балл: {result['readability']['score']}")
    print(f"   Уровень: {result['readability']['level']}")
    
    print("\n🎨 ПРОБЛЕМНЫЕ СЛОВА ДЛЯ ПОДСВЕТКИ:")
    pw = result['problem_words']
    print(f"   🔴 Переспам (топ-3): {pw['spam_words']}")
    print(f"    Вода (стоп-слова): {pw['water_words'][:10]}...")
    print(f"   🔵 Смешанные: {pw['mixed_words']}")
    print("=" * 60)