from celery import shared_task
from datetime import datetime, timedelta
from .models import  Reviews
from celery.signals import celeryd_after_setup
from .utils import load_accounts_from_env, send_appointments_to_api, process_status_and_audio, send_to_telegram
from .med_element.get_info import get_doctor_info, get_patient_info, find_appointments
from .database.save_data import save_appointments_to_db

import redis
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
    test_request_task.apply_async()
    update_status_and_fetch_audio_task.apply_async()


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
def update_status_and_fetch_audio_task():
    try:
        process_status_and_audio()  # Вызов основной функции
        logger.info("Статусы и аудио успешно обработаны.")
        all_reviews = Reviews.objects.filter(doctor_rating__lt=2) | Reviews.objects.filter(clinic_rating__lt=2)
        for review in all_reviews:
            send_to_telegram(review.RECEPTION_CODE)

    except Exception as e:
        logger.error(f"Ошибка в update_status_and_fetch_audio_task: {e}")


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