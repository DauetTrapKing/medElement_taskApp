from django.shortcuts import render
from django.http import HttpResponse
from .models import Reviews
import datetime
import openai

def generate_monthly_report(request):
    current_month = datetime.datetime.now().month
    last_month_reviews = Reviews.objects.filter(reception_date__month=current_month - 1)

    if not last_month_reviews.exists():
        return HttpResponse("Нет данных для отчета за последний месяц.")
    reviews_data = []
    for review in last_month_reviews:
        reviews_data.append({
            "doctor_rating": review.doctor_rating,
            "doctor_feedback": review.doctor_feedback,
            "clinic_rating": review.clinic_rating,
            "clinic_feedback": review.clinic_feedback
        })
    prompt = (
        "Ты аналитик в клинике. Вот данные за последний месяц: \n"
        f"{reviews_data}\n\n"
        "Сделай анализ на основе этих данных. Выведи основные выводы, укажи средние оценки, выдели положительные и отрицательные моменты."
    )
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты помощник для анализа данных в клинике."},
                {"role": "user", "content": prompt}
            ]
        )
        gpt_response = response.choices[0].message.content.strip()
        return HttpResponse(f"Анализ по данным за последний месяц: {gpt_response}")

    except Exception as e:
        return HttpResponse(f"Ошибка при анализе данных: {str(e)}")
