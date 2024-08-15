from appointments.models import Status
from django.conf import settings
import requests
import logging
import logging
import os



logger = logging.getLogger(__name__)
def update_status_and_fetch_audio():
    try:
        api_key = os.getenv("ACS_API_KEY")
        status_url = f"https://back.crm.acsolutions.ai/api/v2/orders/public/{api_key}/get_status"
        audio_url = f"https://back.crm.acsolutions.ai/api/v2/orders/public/{api_key}/get_calls"

        # Получаем все записи из таблицы Status
        all_statuses = Status.objects.all()

        for status in all_statuses:
            order_key = status.order_key

            # Запрос на обновление статуса
            response = requests.get(status_url, params={"order_key": order_key})
            response_data = response.json()

            if order_key in response_data:
                status_info = response_data[order_key].get("status_group_8")
                if status_info:
                    # Обновляем статус
                    new_status_name = status_info.get("name", status.status)
                    status.status = new_status_name
                    status.save()

                    # Запрос на получение аудиозаписей
                    audio_response = requests.get(audio_url, params={"order_key": order_key})
                    audio_data = audio_response.json()

                    # Проверяем, есть ли записи в ответе
                    if audio_data:
                        for audio_entry in audio_data:
                            if audio_entry["order_key"][:-1] == order_key:
                                status.audio_link = audio_entry["link"]
                                status.save()
                else:
                    logger.info(f"No status found in status_group_8 for order_key {order_key}. Moving to the next record.")
            else:
                logger.info(f"No status found for order_key {order_key}. Moving to the next record.")

        logger.info("Status update and audio fetch task completed.")
    except Exception as e:
        logger.error(f"Error in update_status_and_fetch_audio task: {e}")

update_status_and_fetch_audio()
