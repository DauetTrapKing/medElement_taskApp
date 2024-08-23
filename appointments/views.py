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
def receive_comment(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            logger.debug(f"Received data: {data}")

            reception_code = data.get("RECEPTION_CODE")
            comment_text = data.get("COMMENT")

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
            logger.info(f"Received data: {data}")

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
                review_instance.save()

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