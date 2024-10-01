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

def upload_excel_view(request):
    if request.method == 'POST':
        excel_file = request.FILES['excel_file']
        df = pd.read_excel(excel_file)
        
        # Ваша логика для обработки данных
        process_excel_data(df)

        return HttpResponse("Файл обработан успешно")
    return render(request, 'upload_excel.html')
