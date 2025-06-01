import re
import requests
from collections import defaultdict
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import spacy
from Levenshtein import distance as lev_distance


# Загрузка списка матерных слов из GitHub + дополнительные слова
def load_ban_words():
    url = "https://raw.githubusercontent.com/bars38/Russian_ban_words/master/words.txt"
    try:
        response = requests.get(url)
        response.raise_for_status()
        words = [word.strip().lower() for word in response.text.split('\n') if word.strip()]

        # Добавляем дополнительные слова
        extra_words = [
            "нахуй", "назуй", "пезда", "блятб", "нназуй", "ннахуй",
            "пидор", "буд", "каг", "кага", "педик", "ебаный", "ебанный", "еб", "сука", "блят"
        ]
        words.extend(extra_words)

        return set(words), words
    except Exception as e:
        print(f"⚠️ Ошибка загрузки списка слов: {e}")
        base_words = [
            "хуй", "пизда", "ебал", "сука", "блядь", "мудак", "залупа",
            "нахуй", "назуй", "пезда", "блятб", "нназуй", "ннахуй",
            "пидор", "буд", "каг", "кага", "педик", "ебаный", "ебанный", "еб", "блят"
        ]
        return set(base_words), base_words


BAN_WORDS_SET, BAN_WORDS_LIST = load_ban_words()
print(f"Загружено {len(BAN_WORDS_SET)} запрещенных слов")

# Инициализация spaCy
try:
    nlp = spacy.load("ru_core_news_sm", disable=["parser", "ner"])
    SPACY_AVAILABLE = True
except Exception as e:
    print(f"⚠️ Ошибка загрузки spaCy: {e}")
    SPACY_AVAILABLE = False


# Генерация паттернов для всех слов
def generate_smart_patterns(words):
    patterns = []
    short_words = set()

    for word in words:
        if len(word) <= 3:  # Короткие слова проверяем отдельно
            short_words.add(word)
            continue

        # Базовый паттерн для точного совпадения
        patterns.append(r"(?i)\b" + re.escape(word) + r"\b")

        # Паттерн с заменой похожих символов
        pattern = []
        for char in word:
            if char in {'а', 'a', '@'}:
                pattern.append('[аa@]')
            elif char in {'о', 'o', '0'}:
                pattern.append('[оo0]')
            elif char in {'е', 'e', 'ё'}:
                pattern.append('[еeё]')
            elif char in {'и', 'i', 'ы'}:
                pattern.append('[иiы]')
            else:
                pattern.append(re.escape(char))
        patterns.append(r"(?i)\b" + ''.join(pattern) + r"\b")

    return patterns, short_words


PATTERNS, SHORT_WORDS = generate_smart_patterns(BAN_WORDS_LIST)


# Проверка текста
def contains_bad_content(text: str) -> bool:
    text_lower = text.lower()

    # Быстрая проверка коротких слов
    if any(word in text_lower for word in SHORT_WORDS):
        return True

    # Проверка по паттернам
    for pattern in PATTERNS:
        if re.search(pattern, text_lower):
            return True

    # NLP анализ
    if SPACY_AVAILABLE and len(text_lower) > 3:
        try:
            doc = nlp(text_lower)
            for token in doc:
                if token.lemma_ in BAN_WORDS_SET or token.text in BAN_WORDS_SET:
                    return True
                if len(token.text) > 3:
                    closest_word = min(BAN_WORDS_SET, key=lambda x: lev_distance(token.text, x))
                    if lev_distance(token.text, closest_word) <= 1:
                        return True
        except Exception as e:
            print(f"Ошибка NLP: {e}")

    return False


# Система статистики
user_stats = defaultdict(int)
message_log = []


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not user_stats:
        await update.message.reply_text("Нарушений не зафиксировано")
        return

    stats_text = "📊 Статистика нарушений:\n"
    sorted_stats = sorted(user_stats.items(), key=lambda x: x[1], reverse=True)

    for user_id, count in sorted_stats[:20]:
        try:
            user = await context.bot.get_chat_member(update.message.chat_id, user_id)
            name = user.user.first_name or user.user.username or f"ID:{user_id}"
            stats_text += f"🔴 {name}: {count} нарушений\n"
        except:
            stats_text += f"🔴 ID:{user_id}: {count} нарушений\n"

    await update.message.reply_text(stats_text)


async def log_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    text = update.message.text

    if contains_bad_content(text):
        user_stats[user.id] += 1
        log_entry = f"Нарушение от {user.id} (@{user.username or 'нет'}): '{text}'"
        message_log.append(log_entry)
        print(log_entry)


def main():
    application = Application.builder().token("7777974311:AAEeEkhcjo34GJkIJptPsFeSW1-ZWz9sNKk").build()

    application.add_handler(CommandHandler("statkarma", show_stats))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, log_message))

    print("🟢 Бот запущен. Ожидание сообщений...")
    application.run_polling()


if __name__ == "__main__":
    main()