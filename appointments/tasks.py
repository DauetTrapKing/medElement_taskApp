from celery import shared_task
from datetime import datetime, timedelta
from .models import Statuses, Reviews
from celery.signals import celeryd_after_setup
from .utils import load_accounts_from_env, send_appointments_to_api, make_url
from .med_element.get_info import get_doctor_info, get_patient_info, find_appointments
from .database.save_data import save_appointments_to_db

import redis
import requests
import logging
import logging
import os
import pytz


logger = logging.getLogger(__name__)

redis_client = redis.Redis(host="localhost", port=6379, db=0)
BASE_URL = "https://api.medelement.com"
@celeryd_after_setup.connect
def run_task_on_start(sender, instance, **kwargs):
    logger.debug("Starting tasks immediately after worker setup...")
    update_status_and_fetch_audio.apply_async()
    test_request_task.apply_async()


@shared_task
def test_request_task():
    try:
        tz = pytz.timezone("Asia/Almaty")
        now = datetime.now(tz)
        logger.info(f"Task started at (localtime): {now} with timezone: {tz}")
        two_hours_ago = now - timedelta(hours=4)
        all_detailed_appointments = []
        accounts = load_accounts_from_env()
        for account in accounts:
            username = account["username"]
            password = account["password"]
            address = account["address"]

            appointments = find_appointments(username, password, address)
            if "error" in appointments or len(appointments) == 0:
                continue

            # # Ограничиваем количество приемов до одного
            # appointments = appointments[:1]
            detailed_appointments = []
            for appt in appointments:
                doctor_info = get_doctor_info(appt["PATIENT_CODE"], two_hours_ago, now, username, password)
                patient_info = get_patient_info(appt["PATIENT_CODE"], username, password)
                if doctor_info and patient_info:
                    detailed_appointments.append(
                        {
                            "appointment": appt,
                            "doctor_info": doctor_info,
                            "patient_info": {
                                "NAME": patient_info.get("NAME", ""),
                                "LASTNAME": patient_info.get("LASTNAME", ""),
                                "MIDDLENAME": patient_info.get("MIDDLENAME", ""),
                                "BIRTHDAY": patient_info.get("BIRTHDAY", ""),
                                "GENDER": patient_info.get("GENDER", ""),
                                "PATIENT_PHONE": patient_info.get("PATIENT_PHONE", ""),
                            },
                        }
                    )
            logger.info(f"Collected {len(detailed_appointments)} detailed appointments for account with address {address}.")
            all_detailed_appointments.extend(detailed_appointments)

        logger.info(f"Total collected {len(all_detailed_appointments)} detailed appointments from all accounts.")
        
        save_appointments_to_db(all_detailed_appointments)
        # Планирование задачи по отправке данных в API через 2 часа
        send_appointments_to_api_task.apply_async(args=[all_detailed_appointments], countdown=2 * 60 * 60)
        return all_detailed_appointments
    except Exception as e:
        logger.error(f"Error in test_request_task: {e}")
        return {"error": str(e)}



@shared_task
def update_status_and_fetch_audio():
    try:
        api_key = os.getenv("ACS_API_KEY")
        status_url = f"https://back.crm.acsolutions.ai/api/v2/orders/public/{api_key}/get_status"
        audio_url = f"https://back.crm.acsolutions.ai/api/v2/orders/public/{api_key}/get_calls"
        # Получаем все записи из таблицы Status
        all_statuses = Statuses.objects.all()
        for status in all_statuses:
            order_key = status.order_key
            # Запрос на обновление статуса
            response = requests.get(status_url, params={"keys": order_key})
            response_data = response.json()

            # Проверка, что response_data это словарь, а не список
            if isinstance(response_data, dict) and order_key in response_data:
                status_info = response_data[order_key].get("status_group_8")
                if status_info:
                    print(response_data)
                    new_status_name = status_info.get("name", status.status)
                    if status.status != new_status_name:
                        # Обновляем статус только если он изменился
                        print(f"Обновление статуса для order_key {order_key}: {new_status_name}")
                        status.status = new_status_name
                        status.save()
                        # Запрос на получение аудиозаписей
                        audio_response = requests.get(audio_url, params={"keys": order_key})
                        audio_data = audio_response.json()

                        # Проверка, что audio_data это список
                        if isinstance(audio_data, list):
                            for audio_entry in audio_data:
                                # Проверяем, является ли audio_entry словарем
                                if isinstance(audio_entry, dict) and audio_entry.get("order_key") == order_key:
                                    audio_link = audio_entry.get("link")
                                    print(f"Ссылка на аудио: {audio_link}")
                                    if audio_link:
                                        status.audio_link = audio_link
                                        try:
                                            status.save()
                                            print(f"Ссылка на аудио успешно сохранена для order_key {order_key}")
                                            
                                            # Сохранение ссылки на аудио в таблице Reviews по RECEPTION_CODE
                                            try:
                                                review = Reviews.objects.get(RECEPTION_CODE=status.RECEPTION_CODE)
                                                review.audio_link = audio_link
                                                review.save()
                                                print(f"Ссылка на аудио успешно сохранена в Reviews для RECEPTION_CODE {status.RECEPTION_CODE}")
                                            except Reviews.DoesNotExist:
                                                print(f"Запись в Reviews для RECEPTION_CODE {status.RECEPTION_CODE} не найдена")
                                            except Exception as e:
                                                print(f"Ошибка при сохранении ссылки на аудио в Reviews для RECEPTION_CODE {status.RECEPTION_CODE}: {e}")

                                        except Exception as e:
                                            print(f"Ошибка при сохранении ссылки на аудио для order_key {order_key}: {e}")
                                else:
                                    print(f"audio_entry не является словарем или не содержит order_key: {audio_entry}")
                        else:
                            print(f"audio_data не является списком: {audio_data}")
            else:
                print(f"response_data не является словарем или не содержит ключ {order_key}: {response_data}")

    except Exception as e:
        print(f"Error in update_status_and_fetch_audio task: {e}")


@shared_task
def send_appointments_to_api_task(detailed_appointments):
    try:
        order_mapping = send_appointments_to_api(detailed_appointments)
        print(order_mapping)
        logger.info("Data successfully sent to API after 2 hours.")
        return order_mapping
    except Exception as e:
        logger.error(f"Error in send_appointments_to_api_task: {e}")
        return {"error": str(e)}