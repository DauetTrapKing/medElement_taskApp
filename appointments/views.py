from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Reviews
from .redis.cache import save_comment_to_redis, get_comments_from_redis
from .openai.analysisData import analyze_comments
from .utils import send_to_telegram

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

@csrf_exempt
def process_conversation(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            logger.debug(f"Received data: {data}")

            # Извлечение данных
            order_key = data.get("order")
            reception_code = data.get("import")  # Здесь 'import' используется как RECEPTION_CODE
            conversation_parts = [data.get(str(i)) for i in range(1, 11)]

            if not order_key or not reception_code or not all(conversation_parts):
                logger.error(
                    f"Missing order key, RECEPTION_CODE, or conversation parts in request data: {data}"
                )
                return JsonResponse(
                    {"error": "Missing order key, RECEPTION_CODE, or conversation parts"}, status=400
                )

            # Объединение всех частей разговора
            conversation = " ".join(conversation_parts)
            print(conversation)
            # Анализ разговора
            analysis = analyze_comments(conversation)

            # Проверка существования записи и создание новой, если не существует
            review_instance, created = Reviews.objects.get_or_create(
                RECEPTION_CODE=reception_code,
                defaults={
                    'doctor_rating': analysis.get("doctor_rating"),
                    'doctor_feedback': analysis.get("doctor_feedback"),
                    'clinic_rating': analysis.get("clinic_rating"),
                    'clinic_feedback': analysis.get("clinic_feedback"),
                }
            )

            if not created:
                # Если запись уже существовала, обновляем поля
                review_instance.doctor_rating = analysis.get("doctor_rating")
                review_instance.doctor_feedback = analysis.get("doctor_feedback")
                review_instance.clinic_rating = analysis.get("clinic_rating")
                review_instance.clinic_feedback = analysis.get("clinic_feedback")
                review_instance.order_key = order_key  # обновление order_key в базе данных
                review_instance.save()

            # Отправка анализа в Telegram с использованием reception_code
            send_to_telegram(reception_code)

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

# ###UTILS
# def send_to_telegram(message): 
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')  
    chat_id = os.getenv('TELEGRA_CHAT_ID')
    telegram_api_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    doctor_rating = int(message.get('doctor_rating'))
    clinic_rating = int(message.get('clinic_rating'))
    
    # Проверка условия на отправку сообщения
    if (doctor_rating is not None or clinic_rating is not None) and (doctor_rating <= 3 or clinic_rating <= 3):
        text = (
            '*Я Абсолют, и вижу все*\n\n'
            '*Doctor Rating:* {doctor_rating}\n'
            '*Doctor Feedback:* {doctor_feedback}\n'
            '*Clinic Rating:* {clinic_rating}\n'
            '*Clinic Feedback:* {clinic_feedback}\n'
        ).format(
            doctor_rating=doctor_rating,
            doctor_feedback=message.get('doctor_feedback', 'Отзыв отсутствует'),
            clinic_rating=clinic_rating,
            clinic_feedback=message.get('clinic_feedback', 'Отзыв отсутствует')
        )
        
        # Данные, которые мы отправляем в Telegram
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }
        
        # Отправка запроса с использованием JSON
        response = requests.post(telegram_api_url, json=payload)
        
        if response.status_code == 200:
            logger.debug("Message sent to Telegram successfully.")
        else:
            logger.error(f"Failed to send message to Telegram. Status code: {response.status_code}. Response: {response.text}")
    else:
        logger.debug("No message sent to Telegram. Ratings are higher than 3.")