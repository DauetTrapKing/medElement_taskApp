from datetime import datetime, timedelta
from appointments.models import Reviews, Statuses
from django.utils import timezone

import logging
import redis

logger = logging.getLogger(__name__)

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
redis_client = redis.Redis(host="localhost", port=6379, db=0)

###DATABASE
def save_appointments_to_db(detailed_appointments):
    """Saving data to database"""
    try:
        two_weeks_ago = timezone.now() - timedelta(weeks=2)
        for appointment in detailed_appointments:
            appointment_info = appointment["appointment"]
            doctor_info = appointment["doctor_info"]
            patient_info = appointment["patient_info"]
            reception_code = appointment_info.get("RECEPTION_CODE")
            patient_phone = patient_info.get("PATIENT_PHONE")

            if not reception_code:
                logger.error(f"Missing 'RECEPTION_CODE' in appointment: {appointment}")
                continue

            if not patient_phone:
                logger.warning(f"Missing 'PATIENT_PHONE' in appointment: {appointment}. Skipping...")
                continue

            # Получение имени доктора
            doctor_name = doctor_info.get("SPECIALIST_FULLNAME", "Unknown Doctor")
            
            # Проверка на наличие слова "кабинет" в имени доктора
            if ("кабинет" or "лаборатория" or "callcenter") in doctor_name.lower():
                logger.warning(f"Appointment with RECEPTION_CODE {reception_code} skipped due to 'кабинет' in doctor's name.")
                continue
            # Проверка на дублирование по call_date за последние две недели
            existing_status = Statuses.objects.filter(RECEPTION_CODE=reception_code, call_date__gte=two_weeks_ago).first()
            if existing_status:
                logger.warning(f"Appointment for RECEPTION_CODE {reception_code} has been already processed within the last two weeks.")
                continue

            reception_date = datetime.strptime(appointment_info["STARTTIME"], "%Y-%m-%d %H:%M:%S")
            # Получение адреса из appointment
            address = appointment_info.get("address")

            # Проверка, существует ли запись с таким же RECEPTION_CODE
            review = Reviews.objects.filter(RECEPTION_CODE=reception_code).first()
            if review:
                logger.warning(f"Duplicate RECEPTION_CODE found: {reception_code}")
            else:
                # Создание новой записи в Review
                review = Reviews(
                    phone=patient_phone,
                    patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
                    reception_date=reception_date.date(),
                    reception_time=reception_date.time(),
                    doctor=doctor_name,
                    RECEPTION_CODE=reception_code,
                    address=address,
                )
                review.save()
                logger.info(f"Successfully added/updated review in database for address: {address}")

                # Создание записи в Status без order_key
                # status = Statuses(
                #     phone=patient_phone,
                #     patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
                #     status="Scheduled",
                #     RECEPTION_CODE=reception_code,
                #     call_date=timezone.now()  # call_date будет добавлено позже, при отправке API
                # )
                # status.save()
                # logger.info(f"Successfully added/updated status in database for RECEPTION_CODE: {reception_code}")

    except Exception as e:
        logger.error(f"Error saving data to database: {e}")