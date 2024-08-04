import logging
import json
import openai
import requests
import redis
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
from .models import AnalysisResult


logger = logging.getLogger(__name__)
openai.api_key = "sk-proj-sRoFBbkQhLHMZmYrCXduT3BlbkFJKz801QoLGLa6SDibzQ1J"
redis_client = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)


@csrf_exempt
def save_comment_to_redis(reception_code, comment):
    redis_client.rpush(reception_code, comment)
    redis_client.expire(reception_code, 600)  # Устанавливаем время жизни ключа в 10 минут

def get_comments_from_redis(reception_code):
    comments = redis_client.lrange(reception_code, 0, -1)
    redis_client.delete(reception_code)
    return comments

def analyze_comments(comments):
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
                "5. Вернется ли пациент (Да или Нет) . Только так"
                "Проанализируй следующие комментарии и верни результат в формате JSON без''' такого занака и без двойных ковычек. Вот примеры разговоров и соответствующих анализов:"
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
                '{"оценка_врача": 4, "отзыв_врача": "Врач был внимателен и ответил на все мои вопросы.", "оценка_клиники": 5, "отзыв_клиники": "Всё было отлично, спасибо!", "придет_не_придет": "да"}'
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
                '{"оценка_врача": 2, "отзыв_врача": "Врач был не очень внимателен.", "оценка_клиники": 3, "отзыв_клиники": "В целом неплохо, но есть что улучшить.", "придет_не_придет": "возможно"}'
            ),
        },
        {"role": "user", "content": combined_comments},
    ]

    # Отправка комментариев в ChatGPT
    response = openai.chat.completions.create(model="gpt-4o-mini", messages=messages)

    gpt_response = response.choices[0].message.content.strip()
    print(gpt_response)
    try:
        analysis = json.loads(gpt_response)
    except json.JSONDecodeError:
        logger.error(f"Ошибка декодирования JSON от GPT: {gpt_response}")
        return {
            "doctor_rating": None,
            "doctor_feedback": None,
            "clinic_rating": None,
            "clinic_feedback": None,
            "will_return": None,
        }

    return {
        "doctor_rating": analysis.get("оценка_врача"),
        "doctor_feedback": analysis.get("отзыв_врача"),
        "clinic_rating": analysis.get("оценка_клиники"),
        "clinic_feedback": analysis.get("отзыв_клиники"),
        "will_return": analysis.get("придет_не_придет"),
    }

@csrf_exempt
def receive_comment(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            logger.debug(f"Received data: {data}")

            reception_code = data.get("RECEPTION_CODE")
            comment_text = data.get("comment")

            if not reception_code or not comment_text:
                logger.error(
                    f"Missing RECEPTION_CODE or comment in request data: {data}"
                )
                return JsonResponse(
                    {"error": "Missing RECEPTION_CODE or comment"}, status=400
                )

            save_comment_to_redis(reception_code, comment_text)
            
            return JsonResponse({"status": "Comment received successfully"}, status=201)

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {request.body}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    logger.error(f"Invalid request method: {request.method}")
    return JsonResponse({"error": "Invalid method"}, status=405)

@csrf_exempt
def end_of_speech(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            logger.debug(f"Received data: {data}")

            reception_code = data.get("RECEPTION_CODE")

            if not reception_code:
                logger.error(f"Missing RECEPTION_CODE in request data: {data}")
                return JsonResponse({"error": "Missing RECEPTION_CODE"}, status=400)

            comments = get_comments_from_redis(reception_code)

            if not comments:
                logger.error(f"No comments found for RECEPTION_CODE: {reception_code}")
                return JsonResponse(
                    {"error": "No comments found for this RECEPTION_CODE"}, status=404
                )

            analysis = analyze_comments(comments)

            # Сохранение результатов анализа
            AnalysisResult.objects.update_or_create(
                reception_code=reception_code,
                defaults={
                    "doctor_rating": analysis.get("doctor_rating"),
                    "doctor_feedback": analysis.get("doctor_feedback"),
                    "clinic_rating": analysis.get("clinic_rating"),
                    "clinic_feedback": analysis.get("clinic_feedback"),
                    "will_return": analysis.get("will_return"),
                    "analyzed_at": timezone.now(),
                },
            )

            # Отправка анализа в Telegram
            send_to_telegram(analysis)

            return JsonResponse(
                {
                    "status": "Analysis completed and saved successfully",
                    "analysis": analysis,
                },
                status=200,
            )
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {request.body}")
            return JsonResponse({"error": "Invalid JSON"}, status=400)

    logger.error(f"Invalid request method: {request.method}")
    return JsonResponse({"error": "Invalid method"}, status=405)

def send_to_telegram(message):
    bot_token = '7279203867:AAHEwdAd8gmgFOO00t42KtXXf6C-loaVVVk'
    chat_id = '910943180'
    telegram_api_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    
    text = f"Analysis Result:\nDoctor Rating: {message.get('doctor_rating')}\nDoctor Feedback: {message.get('doctor_feedback')}\nClinic Rating: {message.get('clinic_rating')}\nClinic Feedback: {message.get('clinic_feedback')}\nWill Return: {message.get('will_return')}"
    
    requests.post(telegram_api_url, data={'chat_id': chat_id, 'text': text})