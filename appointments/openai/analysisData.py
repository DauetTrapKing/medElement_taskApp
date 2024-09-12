from django.conf import settings
import logging
import json
import openai
import requests
import os
import redis


logger = logging.getLogger(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
redis_client = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)

###OPENAAI
def check_openai_system_status(): 
    try:
        status_url = "https://status.openai.com/api/v2/status.json"
        response = requests.get(status_url)
        
        if response.status_code == 200:
            status_data = response.json()
            system_status = status_data.get('status', {}).get('indicator', 'unknown')
            
            if system_status in ['none', 'minor']:
                logger.info(f"OpenAI system status is '{system_status}'. Proceeding with analysis.")
                return True
            else:
                logger.warning(f"OpenAI system status is '{system_status}'. Skipping analysis.")
                return False
        else:
            logger.error(f"Failed to retrieve OpenAI system status. HTTP Status Code: {response.status_code}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Error while connecting to OpenAI status API: {e}")
        return False

def analyze_comments():
    data = "emm chel my etu fichu ubrali"
    return data

def analyze_transcription(robot_phrases, transcription):
    try:
        logger.info("Starting transcription analysis")

        # Встроенная функция для рекурсивного преобразования множеств и Ellipsis в списки
        def remove_ellipsis(data, depth=0, max_depth=10):
            if depth > max_depth:
                logger.error("Max recursion depth reached")
                return "RECURSION_LIMIT_REACHED"

            if isinstance(data, set):
                logger.debug(f"Converting set at depth {depth}: {data}")
                return [remove_ellipsis(item, depth + 1, max_depth) for item in data]
            elif isinstance(data, dict):
                logger.debug(f"Converting dict at depth {depth}")
                return {key: remove_ellipsis(value, depth + 1, max_depth) for key, value in data.items()}
            elif isinstance(data, list):
                logger.debug(f"Converting list at depth {depth}")
                return [remove_ellipsis(item, depth + 1, max_depth) for item in data]
            elif isinstance(data, tuple):
                logger.debug(f"Converting tuple at depth {depth}")
                return tuple(remove_ellipsis(item, depth + 1, max_depth) for item in data)
            elif data is Ellipsis:
                logger.warning(f"Found Ellipsis at depth {depth}, replacing with empty string")
                return ""  # Заменяем все `Ellipsis` на пустую строку
            else:
                logger.debug(f"Encountered value of type {type(data)} at depth {depth}")
                return data

        # Преобразуем все множества и Ellipsis в сериализуемые объекты (рекурсивно)
        robot_phrases_serializable = remove_ellipsis(robot_phrases)

        # Логируем преобразованные данные для проверки
        logger.debug(f"Original robot_phrases: {robot_phrases}")
        logger.debug(f"Serialized robot phrases: {robot_phrases_serializable}")

        # Логируем саму транскрипцию
        logger.debug(f"Transcription: {transcription}")

        # Формируем массив сообщений
        messages = [
    {
        "role": "system",
        "content": (
            "Ты виртуальный помощник, который анализирует телефонные разговоры между роботом и пациентом. "
            "Твоя задача — извлечь следующую информацию из разговора: "
            "1. Оценка врача (от 1 до 5). Это всегда должно быть целое число (int). Если пациент не дал оценку, верни значение 0. "
            "2. Отзыв о враче. Описание из слов пациента без изменений. "
            "3. Оценка клиники (от 1 до 5). Это всегда должно быть целое число (int). Если пациент не дал оценку, верни значение 0. "
            "4. Отзыв о клинике. Описание из слов пациента без изменений. "
            "Если данные отсутствуют, укажи это явно, например, 'отзыв отсутствует' или 'оценка отсутствует'. "
            "Проанализируй следующие комментарии и верни результат в формате JSON без такого знака ''' и без двойных ковычек. Вот примеры разговоров и соответствующих анализов:"
        ),
    },
    {
        "role": "system",
        "content": (
            "Пример 1: Разговор: "
            "Робот: Как вы оцениваете работу нашего врача по шкале от 1 до 5? "
            "Пациент: Я бы дал 4. "
            "Робот: Спасибо! А есть ли у вас какие-либо комментарии по поводу работы врача? "
            "Пациент: Врач был внимателен и ответил на все мои вопросы. "
            "Робот: Как вы оцениваете работу клиники по шкале от 1 до 5? "
            "Пациент: Думаю, 5. "
            "Робот: Есть ли у вас какие-либо комментарии по поводу работы клиники? "
            "Пациент: Всё было отлично, спасибо! "
            "Робот: Придете ли вы к нам снова? "
            "Пациент: Да, обязательно. "
            "Анализ: "
            '{"оценка_врача": 4, "отзыв_врача": "Врач был внимателен и ответил на все мои вопросы.", "оценка_клиники": 5, "отзыв_клиники": "Всё было отлично, спасибо!"}'
        ),
    },
    {
        "role": "system",
        "content": (
            "Пример 2: Разговор: "
            "Робот: Как вы оцениваете работу нашего врача по шкале от 1 до 5? "
            "Пациент: Поставлю 2. "
            "Робот: Спасибо! А есть ли у вас какие-либо комментарии по поводу работы врача? "
            "Пациент: Врач был не очень внимателен. "
            "Робот: Как вы оцениваете работу клиники по шкале от 1 до 5? "
            "Пациент: На 3. "
            "Робот: Есть ли у вас какие-либо комментарии по поводу работы клиники? "
            "Пациент: В целом неплохо, но есть что улучшить. "
            "Робот: Придете ли вы к нам снова? "
            "Пациент: Возможно, но не уверен. "
            "Анализ: "
            '{"оценка_врача": 2, "отзыв_врача": "Врач был не очень внимателен.", "оценка_клиники": 3, "отзыв_клиники": "В целом неплохо, но есть что улучшить."}'
        ),
    },
    {
        "role": "user",
        "content": transcription
    }
]
        logger.debug(f"Sending prompt to GPT with messages: {messages}")

        # Отправка запроса к GPT
        try:
            response = openai.ChatCompletion.create(model="gpt-4o-mini", messages=messages)
            gpt_response = response.choices[0].message.content.strip()  # Убедитесь, что используете 'content' правильно
            analysis = json.loads(gpt_response)
        except (json.JSONDecodeError, KeyError):
            logger.error("Ошибка при обработке ответа от OpenAI.")
            return {
                "doctor_rating": None,
                "doctor_feedback": None,
                "clinic_rating": None,
                "clinic_feedback": None,
            }
        return {
            "doctor_rating": analysis.get("оценка_врача"),
            "doctor_feedback": analysis.get("отзыв_врача"),
            "clinic_rating": analysis.get("оценка_клиники"),
            "clinic_feedback": analysis.get("отзыв_клиники"),
        }
    except Exception as e:
        logger.error(f"Error in analyze_transcription: {e}")
        return None