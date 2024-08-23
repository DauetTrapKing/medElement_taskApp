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

def analyze_comments(comments):
    if not check_openai_system_status():
        logger.error("OpenAI system status is not optimal. Skipping analysis.")
        return {
            "doctor_rating": None,
            "doctor_feedback": None,
            "clinic_rating": None,
            "clinic_feedback": None,
        }
    
    combined_comments = " ".join(comments)
    messages = [
        {
            "role": "system",
            "content": (
                "Ты виртуальный помощник, который анализирует телефонные разговоры между роботом и пациентом. "
                "Твоя задача — извлечь следующую информацию из разговора: "
                "1. Оценка врача (от 1 до 5). "
                "2. Отзыв о враче. тут не пиши в третьем лице, это говорит пациент" 
                "3. Оценка клиники (от 1 до 5). "
                "4. Отзыв о клинике. "
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
                '{"оценка_врача": 4, "отзыв_врача": "Врач был внимателен и ответил на все мои вопросы.", "оценка_клиники": 5, "отзыв_клиники": "Всё было отлично, спасибо!", }'
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
                '{"оценка_врача": 2, "отзыв_врача": "Врач был не очень внимателен.", "оценка_клиники": 3, "отзыв_клиники": "В целом неплохо, но есть что улучшить.", }'
            ),
        },
        {"role": "user", "content": combined_comments},
    ]
    
    try:
        response = openai.chat.completions.create(model="gpt-4o-mini", messages=messages)
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
