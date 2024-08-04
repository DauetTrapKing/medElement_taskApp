from celery import shared_task
from django.utils import timezone
from base64 import b64encode
from datetime import datetime, timedelta
from urllib.parse import urlencode
from .models import Status, Review
from django.conf import settings

import requests
import logging
import redis
import json
import pytz
import time
import logging
import re


logger = logging.getLogger(__name__)

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
redis_client = redis.Redis(host="localhost", port=6379, db=0)

username = "e29aed230f8bc79bffeb2c8956463d26"
password = "62e210d896e67"


def basic_auth(username, password):
    base_string = f"{username}:{password}".encode("ascii")
    token = b64encode(base_string).decode("ascii")
    return token


BASE_URL = "https://api.medelement.com"


def get_headers():
    auth_token = basic_auth(username, password)
    return {
        "Authorization": f"Basic {auth_token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def make_url(base_url, endpoint):
    return f"{base_url}{endpoint}"


def fetch_json(url, params=None):
    headers = get_headers()
    encoded_params = urlencode(params)
    try:
        logger.info(
            f"Fetching JSON from {url} with params: {encoded_params} and headers: {headers}"
        )
        response = requests.post(url, headers=headers, data=encoded_params)
        response.raise_for_status()
        logger.info(f"Response status: {response.status_code}")
        return response.json()
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return {"error": "http", "status_code": response.status_code}
    except Exception as err:
        logger.error(f"Other error occurred: {err}")
        return None


def find_appointments():
    max_attempts = 5
    attempts = 0
    while attempts < max_attempts:
        try:
            tz = pytz.timezone("Asia/Qyzylorda")
            now = datetime.now(tz)
            two_hours_ago = now - timedelta(hours=2)
            today = now.strftime("%d.%m.%Y")
            tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")

            # Получение сохраненного значения skip из Redis
            redis_skip_key = "appointments_skip"
            skip = int(redis_client.get(redis_skip_key) or 0)
            logger.info(f"Starting with skip value: {skip}")

            url = make_url(BASE_URL, "/v2/doctor/reception/search")
            data = []
            while True:
                params = {
                    "begin_datetime": today,
                    "end_datetime": tomorrow,
                    "skip": skip,
                    "removed": 0,
                    "active": 0,
                    "only_ambulator": 0,
                }

                json_data = fetch_json(url, params=params)
                if not json_data or "receptions" not in json_data:
                    break

                for reception in json_data["receptions"]:
                    reception_time = tz.localize(
                        datetime.strptime(reception["STARTTIME"], "%Y-%m-%d %H:%M:%S")
                    )
                    if two_hours_ago <= reception_time <= now:
                        data.append(reception)

                if len(json_data["receptions"]) < 50:
                    break

                skip += 50
                # Сохранение  значения skip в Redis 24 часа
                redis_client.set(redis_skip_key, skip, ex=86400)
                time.sleep(5)

            return data
        except Exception as e:
            if "502" in str(e):
                attempts += 1
                logger.warning(
                    f"502 error occurred, attempt {attempts}/{max_attempts}. Retrying in 10 seconds..."
                )
                time.sleep(10)
            elif "429" in str(e):
                attempts += 1
                logger.warning(
                    f"429 error occurred, attempt {attempts}/{max_attempts}. Retrying in 60 seconds..."
                )
                time.sleep(60)
            else:
                logger.error(f"Error in find_appointments: {e}")
                return {"error": str(e)}
    logger.error("Max attempts reached. Terminating the task.")
    return {"error": "Max attempts reached"}


def get_doctor_info(patient_code, two_hours_ago, now):
    max_attempts = 5
    attempts = 0
    tz = pytz.timezone("Asia/Qyzylorda")
    while attempts < max_attempts:
        try:
            today = now.strftime("%d.%m.%Y")
            tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")
            params = {
                "patient_code": patient_code,
                "begin_datetime": today,
                "end_datetime": tomorrow,
                "removed": 0,
                "active": 0,
                "only_ambulator": 0,
            }

            url = make_url(BASE_URL, "/v2/doctor/reception/search_with_pd")
            skip = 0
            recent_receptions = []
            while True:
                time.sleep(2)
                params["skip"] = skip
                json_data = fetch_json(url, params=params)
                if not json_data or "receptions" not in json_data:
                    break

                for reception in json_data["receptions"]:
                    reception_time = tz.localize(
                        datetime.strptime(reception["STARTTIME"], "%Y-%m-%d %H:%M:%S")
                    )
                    if two_hours_ago <= reception_time <= now:
                        recent_receptions.append(reception)

                if len(json_data["receptions"]) < 50:
                    break
                skip += 50
            return recent_receptions[0] if recent_receptions else None
        except Exception as e:
            if "502" in str(e):
                attempts += 1
                logger.warning(
                    f"502 error occurred, attempt {attempts}/{max_attempts}. Retrying in 10 seconds..."
                )
                time.sleep(10)
            elif "429" in str(e):
                attempts += 1
                logger.warning(
                    f"429 error occurred, attempt {attempts}/{max_attempts}. Retrying in 60 seconds..."
                )
                time.sleep(60)
            else:
                logger.error(f"Error in get_doctor_info: {e}")
                return None
    logger.error("Max attempts reached. Terminating the task.")
    return None


def get_patient_info(patient_code):
    max_attempts = 5
    attempts = 0
    while attempts < max_attempts:
        try:
            url = f"{BASE_URL}/doctor/v1/patient/{patient_code}"
            response = requests.get(url, headers=get_headers())
            response.raise_for_status()
            patient_data = response.json()

            phones = []
            for i in range(1, 5):
                phone_key = f"PATIENT_PHONE_{i}"
                phone = patient_data.get(phone_key)
                if isinstance(phone, list):
                    phones.extend(phone)
                elif phone:
                    phones.append(phone)

            patient_phone = ", ".join(phones)  # Объединение номеров в строку

            return {
                "NAME": patient_data.get("NAME"),
                "LASTNAME": patient_data.get("LASTNAME"),
                "MIDDLENAME": patient_data.get("MIDDLENAME"),
                "BIRTHDAY": patient_data.get("BIRTHDAY"),
                "GENDER": patient_data.get("GENDER"),
                "PATIENT_PHONE": patient_phone,
            }
        except requests.RequestException as e:
            if "429" in str(e):
                attempts += 1
                logger.warning(
                    f"429 error occurred, attempt {attempts}/{max_attempts}. Retrying in 60 seconds..."
                )
                time.sleep(60)
            else:
                logger.error(f"Error fetching patient info: {e}")
                return None
    logger.error("Max attempts reached. Terminating the task.")
    return None


def save_appointments_to_redis(appointments):
    try:
        now = datetime.now()
        today_key = now.strftime("%Y-%m-%d")

        for appointment in appointments:
            appointment_id = appointment["RECEPTION_CODE"]
            # Проверка уникальности по RECEPTION_CODE
            if not redis_client.sismember(f"{today_key}:appointments", appointment_id):
                # Добавление уникального ид
                redis_client.sadd(f"{today_key}:appointments", appointment_id)
                # Сохранение данных в отдельный кей
                redis_client.set(
                    f"{today_key}:{appointment_id}", json.dumps(appointment)
                )
                # Установка времени жизни
                redis_client.expire(
                    f"{today_key}:{appointment_id}", timedelta(days=1).seconds
                )
    except Exception as e:
        logger.error(f"Error saving appointments to Redis: {e}")


def save_appointments_to_db(detailed_appointments):
    try:
        for appointment in detailed_appointments:
            appointment_info = appointment["appointment"]
            doctor_info = appointment["doctor_info"]
            patient_info = appointment["patient_info"]

            reception_code = appointment_info.get("RECEPTION_CODE")
            if not reception_code:
                logger.error(f"Missing 'RECEPTION_CODE' in appointment: {appointment}")
                continue

            reception_date = datetime.strptime(
                appointment_info["STARTTIME"], "%Y-%m-%d %H:%M:%S"
            )

            # Проверка, существует ли запись с таким же RECEPTION_CODE
            if (
                Status.objects.filter(RECEPTION_CODE=reception_code).exists()
                or Review.objects.filter(RECEPTION_CODE=reception_code).exists()
            ):
                logger.warning(f"Duplicate RECEPTION_CODE found: {reception_code}")
                continue

            # Сохранение данных в таблицу statuses
            status = Status(
                number=patient_info.get("PATIENT_PHONE", ""),
                patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
                status="Scheduled",
                RECEPTION_CODE=reception_code,
                call_date=timezone.now(),
            )
            status.save()
            logger.info(f"Successfully added status to database: {status}")

            # Сохранение данных в таблицу reviews
            review = Review(
                number=patient_info.get("PATIENT_PHONE", ""),
                patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
                reception_date=reception_date.date(),
                reception_time=reception_date.time(),
                doctor=doctor_info.get("FULLNAME", ""),
                RECEPTION_CODE=reception_code,
            )
            review.save()
            logger.info(f"Successfully added review to database: {review}")
    except Exception as e:
        logger.error(f"Error saving data to database: {e}")


def send_appointments_to_api(detailed_appointments):
    api_key = "EwtRPRrUGQuv1Mgk.GlJiFsREJQaorDDn0lw63chkmsTu2tHQF0CsIA0DDMMnGS5"
    acs_url = (
        f"https://back.crm.acsolutions.ai/api/v2/bpm/public/bp/{api_key}/add_orders"
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    max_attempts = 5

    def send_batch(batch):
        attempts = 0
        while attempts < max_attempts:
            try:
                response = requests.post(acs_url, headers=headers, json=batch)
                response.raise_for_status()
                logger.info(f"Successfully sent batch to API: {batch}")
                break  # Exit the retry loop if the request is successful
            except requests.RequestException as e:
                if response.status_code == 401:
                    attempts += 1
                    logger.warning(
                        f"401 error occurred, attempt {attempts}/{max_attempts}. Retrying in 1 second..."
                    )
                    time.sleep(1)
                else:
                    logger.error(f"Error sending batch to API: {e}")
                    break  # Exit the retry loop if the error is not 401

    batch = []
    for i, appointment in enumerate(detailed_appointments):
        data = {
            "phone": appointment["patient_info"]["PATIENT_PHONE"],
            "import_id": appointment["appointment"]["RECEPTION_CODE"],
            "full_name": f"{appointment['patient_info']['NAME']} {appointment['patient_info']['LASTNAME']} {appointment['patient_info']['MIDDLENAME']}",
        }
        batch.append(data)

        if (i + 1) % 10 == 0 or (i + 1) == len(detailed_appointments):
            send_batch(batch)
            batch = []
            time.sleep(1)  # Pause for 1 second between batches


@shared_task
def test_request_task():
    try:
        tz = pytz.timezone("Asia/Almaty")
        now = datetime.now(tz)
        logger.info(f"Task started at (localtime): {now} with timezone: {tz}")
        two_hours_ago = now - timedelta(hours=2)
        appointments = find_appointments()
        if "error" in appointments:
            return appointments

        detailed_appointments = []
        for appt in appointments:
            doctor_info = get_doctor_info(appt["PATIENT_CODE"], two_hours_ago, now)
            patient_info = get_patient_info(appt["PATIENT_CODE"])
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
        logger.info(f"Collected {len(detailed_appointments)} detailed appointments.")
        logger.info("Task completed. Waiting for the next schedule in 2 hours.")
        for detailed_appointment in detailed_appointments:
            logger.info(f"Detailed appointment: {detailed_appointment}")

        save_appointments_to_redis(detailed_appointments)  # Сохранение данных в Redis
        send_appointments_to_api(detailed_appointments)  # Отправка данных в API
        save_appointments_to_db(detailed_appointments)  # Сохранение данных в БД

        return detailed_appointments
    except Exception as e:
        logger.error(f"Error in test_request_task: {e}")
        return {"error": str(e)}


# def get_recent_appointments(two_hours_ago):
#     url = make_url(BASE_URL, 'search_with_pd')
#     params = {
#         'begin_datetime': two_hours_ago.strftime('%Y-%m-%dT%H:%M:%SZ'),
#         'end_datetime': timezone.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
#         'skip': 0,
#         'removed': 0,
#         'acrive':0,
#         'limit': 50
#     }
#     appointments = []
#     while True:
#         data = fetch_json(url, params=params)
#         if not data:
#             break
#         appointments.extend(data)
#         params['skip'] += 50
#     return appointments
# def fetch_json(url, params=None):
#     try:
#         response = requests.post(url, headers=get_headers(), params=params)
#         response.raise_for_status()
#         return response.json()
#     except requests.RequestException as e:
#         logger.error(f"Error fetching JSON data from {url}: {e}")
#         return {}


# def get_patient_data(patient_code):
#     url = make_url(BASE_URL, f'v1_patient_get_data?patient_code={patient_code}')
#     return fetch_json(url)

# def get_doctor_data(specialist_code):
#     url = make_url(BASE_URL, f'')
#     return fetch_json(url)

# def send_to_robot_call(patient_data, doctor_data):
#     url = ''
#     payload = {
#         'import_id': patient_data['patient_code'],
#         'patient_name': patient_data['name'],
#         'phone_number': patient_data['phone'],
#         'doctor_name': doctor_data['name'],
#         'appointment_time': patient_data['appointment_time']
#     }
#     data = post_json(url, payload)
#     return data.get('order_id')


# def post_json(url, payload):
#     try:
#         response = requests.post(url, headers=get_headers(), json=payload)
#         response.raise_for_status()
#         return response.json()
#     except requests.RequestException as e:
#         logger.error(f"Error posting JSON data to {url}: {e}")
#         return {}

# def get_audio_link(order_id):
#     url = make_url(ACS_BASE_URL, f'get_calls.md?order_id={order_id}')
#     data = fetch_json(url)
#     return data.get('audio_link')


# def process_with_chatgpt(comments):
#     try:
#         response = openai.Completion.create(
#             engine="davinci",
#             prompt=f"Пациент сказал: {comments}. Пожалуйста, дайте оценку врача, отзыв о враче, оценку клиники, отзыв о клинике и скажите, придёт ли пациент на следующий приём.",
#             max_tokens=150
#         )
#         data = response.choices[0].text.strip()
#         return extract_data_from_response(data)
#     except openai.error.OpenAIError as e:
#         logger.error(f"Error processing with ChatGPT: {e}")
#         return {}

# def extract_data_from_response(data):
#     extracted_data = {}
#     for line in data.split('\n'):
#         key, value = map(str.strip, line.split(':', 1))
#         if 'оценка врача' in key:
#             extracted_data['doctor_rating'] = int(value)
#         elif 'отзыв  враче' in key:
#             extracted_data['doctor_feedback'] = value
#         elif 'оценка клиники' in key:
#             extracted_data['clinic_rating'] = int(value)
#         elif 'отзыв  клинике' in key:
#             extracted_data['clinic_feedback'] = value
#         elif 'придёт ли пациент' in key:
#             extracted_data['will_return'] = value.lower() == 'да'
#     return extracted_data

# def save_review(order_id, chatgpt_response):
#     try:
#         review = Review.objects.get(order_id=order_id)
#         review.doctor_rating = chatgpt_response.get('doctor_rating')
#         review.doctor_feedback = chatgpt_response.get('doctor_feedback')
#         review.clinic_rating = chatgpt_response.get('clinic_rating')
#         review.clinic_feedback = chatgpt_response.get('clinic_feedback')
#         review.will_return = chatgpt_response.get('will_return')
#         review.audio_link = get_audio_link(order_id)
#         review.save()

#         if review.clinic_rating and review.clinic_rating <= 2:
#             send_to_telegram(review)
#     except Review.DoesNotExist as e:
#         logger.error(f"Review with order_id {order_id} does not exist: {e}")
#     except Exception as e:
#         logger.error(f"Error saving review with order_id {order_id}: {e}")

# def send_to_telegram(review):
#     try:
#         message = (
#             f"Плохой отзыв от {review.patient_name}:\n"
#             f"Дата приёма: {review.appointment_date}\n"
#             f"Оценка: {review.clinic_rating}\n"
#             f"Отзыв: {review.clinic_feedback}\n"
#             f"Врач: {review.doctor_name}\n"
#             f"Аудиозапись: {review.audio_link}"
#         )
#         url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
#         payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': message}
#         response = requests.post(url, data=payload)
#         response.raise_for_status()
#     except requests.RequestException as e:
#         logger.error(f"Error sending message to Telegram: {e}")

# @shared_task
# def collect_and_process_feedback():
#     try:
#         now = timezone.now()
#         two_hours_ago = now - timezone.timedelta(hours=2)

#         recent_appointments = get_recent_appointments(two_hours_ago)

#         for appointment in recent_appointments:
#             patient_data = get_patient_data(appointment['patient_code'])
#             doctor_data = get_doctor_data(appointment['specialist_code'])
#             order_id = send_to_robot_call(patient_data, doctor_data)

#             # Сохранение информации о приеме в базе данных
#             appointment_db = Appointment.objects.create(
#                 patient_code=appointment['patient_code'],
#                 specialist_code=appointment['specialist_code'],
#                 appointment_time=appointment['appointment_time'],
#                 status='completed',
#                 order_id=order_id
#             )

#             # Предполагается, что robot_call посылает комментарии после завершения
#             comments = "Комментарий от робота обзвона"  # Это нужно будет заменить на реальные комментарии
#             chatgpt_response = process_with_chatgpt(comments)
#             save_review(order_id, chatgpt_response)
#     except Exception as e:
#         logger.error(f"Error in collect_and_process_feedback task: {e}")
