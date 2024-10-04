from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from .models import Reviews, Statuses
from .redis.cache import save_comment_to_redis, get_comments_from_redis
from .openai.analysisData import analyze_comments
from .utils import send_to_telegram

import logging
import json
import openai
import requests
import os
import redis

def upload_excel_view(request):
    if request.method == 'POST':
        excel_file = request.FILES['excel_file']
        df = pd.read_excel(excel_file)
        process_excel_data(df)
        return HttpResponse("Файл обработан успешно")
    return render(request, 'upload_excel.html')


def process_excel_data(df):
    for index, row in df.iterrows():
        order_key = row['Order key'] 
        result = row['Result']
        dialog_text = row['Unnamed: 10'] 

        try:
            status_record = Statuses.objects.get(order_key=order_key)
            reception_code = status_record.RECEPTION_CODE
        except Statuses.DoesNotExist:
            continue 
        if Reviews.objects.filter(RECEPTION_CODE=reception_code).exists():
            continue  
        if result == "в процессе":
            continue
        if pd.notna(dialog_text):
            analyzed_data = analyze_data(dialog_text)  
            Reviews.objects.create(
                RECEPTION_CODE=reception_code,  
                doctor_rating=analyzed_data.get("оценка_врача"),
                doctor_feedback=analyzed_data.get("отзыв_врача"),
                clinic_rating=analyzed_data.get("оценка_клиники"),
                clinic_feedback=analyzed_data.get("отзыв_клиники"),
                reception_date=row['Communications'],  
                result=result 
            )
            print(f"Запись для RECEPTION_CODE: {reception_code} успешно создана.")

def analyze_data(dialog_text):
    """
    Отправляет диалог на анализ в GPT и возвращает анализ в виде словаря.
    
    :param dialog_text: Текст диалога, который нужно проанализировать.
    :return: Словарь с результатами анализа (оценка врача, отзыв врача, оценка клиники, отзыв клиники).
    """
    messages = [
        {
            "role": "system",
            "content": (
                "Ты виртуальный помощник, который анализирует телефонные разговоры между роботом и пациентом. "
                "Твоя задача — извлечь следующую информацию из разговора: "
                "1. Оценка врача (от 1 до 5). "
                "2. Отзыв о враче (говорит пациент). "
                "3. Оценка клиники (от 1 до 5). "
                "4. Отзыв о клинике (говорит пациент). "
                "Если какая-либо информация отсутствует в разговоре, оставь соответствующее поле пустым."
            ),
        },
        {
            "role": "user",
            "content": dialog_text, 
        },
    ]
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini", 
            messages=messages
        )
        gpt_response = response.choices[0].message.content.strip()
        analysis = {
            "оценка_врача": None,
            "отзыв_врача": None,
            "оценка_клиники": None,
            "отзыв_клиники": None
        }
        for line in gpt_response.splitlines():
            if "оценка врача" in line.lower():
                analysis["оценка_врача"] = int(line.split(":")[-1].strip())
            elif "отзыв врача" in line.lower():
                analysis["отзыв_врача"] = line.split(":")[-1].strip()
            elif "оценка клиники" in line.lower():
                analysis["оценка_клиники"] = int(line.split(":")[-1].strip())
            elif "отзыв клиники" in line.lower():
                analysis["отзыв_клиники"] = line.split(":")[-1].strip()

        return analysis
    except Exception as e:
        print(f"Ошибка при анализе данных: {str(e)}")
        return {}