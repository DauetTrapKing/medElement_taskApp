from celery import shared_task
from django.utils import timezone
from base64 import b64encode
from datetime import datetime, timedelta
from urllib.parse import urlencode
from .models import Status, Review
from django.conf import settings
from celery.signals import celeryd_after_setup

import requests
import logging
import redis
import json
import pytz
import time
import logging
import re
import os

logger = logging.getLogger(__name__)

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
redis_client = redis.Redis(host="localhost", port=6379, db=0)

BASE_URL = "https://api.medelement.com"

def load_accounts_from_env():
    accounts = []
    i = 1
    while True:
        username = os.getenv(f"ACCOUNT_{i}_USERNAME")
        password = os.getenv(f"ACCOUNT_{i}_PASSWORD")
        address = os.getenv(f"ACCOUNT_{i}_ADDRESS")
        if not username or not password or not address:
            break
        accounts.append({"username": username, "password": password, "address": address})
        i += 1
    return accounts

accounts = load_accounts_from_env()

def basic_auth(username, password):
    base_string = f"{username}:{password}".encode("ascii")
    token = b64encode(base_string).decode("ascii")
    return token


def get_headers(username, password):
    auth_token = basic_auth(username, password)
    return {
        "Authorization": f"Basic {auth_token}",
        "Content-Type": "application/x-www-form-urlencoded",
    }


def make_url(base_url, endpoint):
    return f"{base_url}{endpoint}"


def fetch_json(url, headers, params=None):
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

address_mapping = {
        "e29aed230f8bc79bffeb2c8956463d26": "ул. Розыбакиева, д. 37 В, Алматы",
        "c5b31e4eafd401947e840973278a27ee": "ул. Нусупбекова, д. 26/1, Алматы",
        "c3785f889ed005dd85ae1f78622424cd": "ул. Манаса, д. 59, Алматы",
        "a4f426a360fc19e596c500a00d1952fb": "ул. Жандосова, д. 10/55, Алматы",
        "8774808244e0d716045a7ed7d07faeac": "ул. Куйши Дина, д. 9, Астана",
        "09a605ca5e93064abd7f20b53ab953ad": "ул. Рашидова, д. 36/15, Шымкент",
        "7c31eabbb299b2093aa448db5f9b6d18": "микрорайон 18, д. 44, Шымкент",
        "54b045ca7c31872bab9e5e8b68407283": "микрорайон Аксай 2, д. 44 А, Алматы",
        "bffada6dd259b83a409bcbb17739d6eb": "ул. Шаляпина, д. 58А, Алматы",
    }
def find_appointments(username, password, address):
    #address = address_mapping.get(username, "Неизвестный адрес")
    logger.info(f"Using address for username {username}: {address}")
    max_attempts = 5
    attempts = 0
    while attempts < max_attempts:
        try:
            tz = pytz.timezone("Asia/Qyzylorda")
            now = datetime.now(tz)
            two_hours_ago = now - timedelta(hours=2)
            today = now.strftime("%d.%m.%Y")
            tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")

            redis_skip_key = f"appointments_skip_{username}"
            skip = int(redis_client.get(redis_skip_key) or 0)
            skip = max(0, skip - 200)
            logger.info(f"Starting with skip value: {skip}")
            url = make_url(BASE_URL, "/v2/doctor/reception/search")
            data = []
            while True:
                params = {
                    "begin_datetime": today,
                    "end_datetime": tomorrow,
                    "skip": skip,
                    "removed": 0,
                }
                
                logger.info(f"Fetching data with params: {params} and address: {address}")

                headers = get_headers(username, password)
                json_data = fetch_json(url, headers, params=params)
                
                if not json_data or "receptions" not in json_data:
                    logger.warning(f"No data found for username: {username}")
                    break

                for reception in json_data["receptions"]:
                    reception_time = tz.localize(
                        datetime.strptime(reception["STARTTIME"], "%Y-%m-%d %H:%M:%S")
                    )
                    if two_hours_ago <= reception_time <= now:
                        reception["address"] = address  # Устанавливаем адрес в reception
                        data.append(reception)

                if len(json_data["receptions"]) < 50:
                    break

                skip += 50
                redis_client.set(redis_skip_key, skip, ex=86400)
                time.sleep(1)

            logger.info(f"Found {len(data)} appointments for address: {address}")
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

def get_doctor_info(patient_code, two_hours_ago, now, username, password):
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
                time.sleep(1)
                params["skip"] = skip
                headers = get_headers(username, password)
                json_data = fetch_json(url, headers, params=params)
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


def get_patient_info(patient_code, username, password):
    max_attempts = 5
    attempts = 0
    while attempts < max_attempts:
        try:
            url = f"{BASE_URL}/doctor/v1/patient/{patient_code}"
            response = requests.get(url, headers=get_headers(username, password))
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


def save_appointments_to_db(detailed_appointments, order_mapping):
    try:
        for appointment in detailed_appointments:
            appointment_info = appointment["appointment"]
            doctor_info = appointment["doctor_info"]
            patient_info = appointment["patient_info"]

            reception_code = appointment_info.get("RECEPTION_CODE")
            patient_phone = patient_info.get("PATIENT_PHONE")
            patient_code = appointment_info.get("PATIENT_CODE")  # Получаем patient_code
            
            if not reception_code:
                logger.error(f"Missing 'RECEPTION_CODE' in appointment: {appointment}")
                continue

            if not patient_phone:
                logger.warning(f"Missing 'PATIENT_PHONE' in appointment: {appointment}. Skipping...")
                continue

            reception_date = datetime.strptime(appointment_info["STARTTIME"], "%Y-%m-%d %H:%M:%S")

            # Получение адреса из appointment
            address = appointment_info.get("address")
            # Получение имени доктора
            doctor_name = doctor_info.get("SPECIALIST_FULLNAME", "Unknown Doctor")

            # Проверка, существует ли запись с таким же RECEPTION_CODE
            review = Review.objects.filter(RECEPTION_CODE=reception_code).first()
            if review:
                logger.warning(f"Duplicate RECEPTION_CODE found: {reception_code}")
            else:
                # Создание новой записи в Review
                review = Review(
                    number=patient_phone,
                    patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
                    reception_date=reception_date.date(),
                    reception_time=reception_date.time(),
                    doctor=doctor_name,  # Сохраняем имя доктора в Review
                    RECEPTION_CODE=reception_code,
                    address=address,
                    patient_code=patient_code,  # Сохраняем patient_code в Review
                )
                review.save()
                logger.info(f"Successfully added/updated review in database for address: {address}")

            # Добавление order_key в Status
            order_key = order_mapping.get(reception_code)
            if not order_key:
                logger.warning(f"Missing order_key for RECEPTION_CODE: {reception_code}. Skipping status save...")
                continue

            status = Status.objects.filter(RECEPTION_CODE=reception_code).first()
            if not status:
                status = Status(
                    number=patient_phone,
                    patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
                    status="Scheduled",
                    RECEPTION_CODE=reception_code,
                    call_date=timezone.now(),
                    order_key=order_key,
                )
            else:
                status.order_key = order_key
            status.save()
            logger.info(f"Successfully added/updated status in database with order_key: {order_key}")
    except Exception as e:
        logger.error(f"Error saving data to database: {e}")


def send_appointments_to_api(detailed_appointments):
    api_key = os.getenv("ACS_API_KEY")
    acs_url = (
        f"https://back.crm.acsolutions.ai/api/v2/bpm/public/bp/{api_key}/add_orders"
    )
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    max_attempts = 5
    order_mapping = {}

    def send_batch(batch):
        attempts = 0
        while attempts < max_attempts:
            try:
                response = requests.post(acs_url, headers=headers, json=batch)
                response.raise_for_status()
                logger.info(f"Successfully sent batch to API: order_key{batch}")
                response_data = response.json().get("data", {})
                # Сохраняем соответствие import_id и order_key
                for key, value in response_data.items():
                    reception_code = value.get("import_id")
                    order_key = value.get("order")
                    if reception_code and order_key:
                        order_mapping[reception_code] = order_key
                    else:
                        logger.warning(f"Missing import_id or order in API response: {value}")

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
        phone = appointment["patient_info"].get("PATIENT_PHONE")
        if not phone:
            logger.warning(f"No phone number for appointment: {appointment}. Skipping...")
            continue

        data = {
            "phone": phone,
            "import_id": appointment["appointment"]["RECEPTION_CODE"],
            "full_name": f"{appointment['patient_info']['NAME']} {appointment['patient_info']['LASTNAME']} {appointment['patient_info']['MIDDLENAME']}",
        }
        batch.append(data)

        # Отправляем партию, если набралось 10 элементов или если достигнут конец списка
        if len(batch) == 10 or (i + 1) == len(detailed_appointments):
            send_batch(batch)
            batch = []
            time.sleep(1)  # Pause for 1 second between batches

    return order_mapping  # Возвращаем словарь с соответствиями import_id и order_key


@celeryd_after_setup.connect
def run_task_on_start(sender, instance, **kwargs):
    logger.debug("Starting update_status_and_fetch_audio task immediately after worker setup...")
    update_status_and_fetch_audio.apply_async()



# @shared_task
# def test_request_task():
#     try:
#         tz = pytz.timezone("Asia/Almaty")
#         now = datetime.now(tz)
#         logger.info(f"Task started at (localtime): {now} with timezone: {tz}")
#         two_hours_ago = now - timedelta(hours=2)
#         all_detailed_appointments = []
#         for account in accounts:
#             username = account["username"]
#             password = account["password"]
#             address = account["address"]

#             appointments = find_appointments(username, password, address)
#             if "error" in appointments or len(appointments) == 0:
#                 continue

#             # Ограничиваем количество приемов до одного
#             appointments = appointments[:1]
#             detailed_appointments = []
#             for appt in appointments:
#                 doctor_info = get_doctor_info(appt["PATIENT_CODE"], two_hours_ago, now, username, password)
#                 patient_info = get_patient_info(appt["PATIENT_CODE"], username, password)
#                 if doctor_info and patient_info:
#                     detailed_appointments.append(
#                         {
#                             "appointment": appt,
#                             "doctor_info": doctor_info,
#                             "patient_info": {
#                                 "NAME": patient_info.get("NAME", ""),
#                                 "LASTNAME": patient_info.get("LASTNAME", ""),
#                                 "MIDDLENAME": patient_info.get("MIDDLENAME", ""),
#                                 "BIRTHDAY": patient_info.get("BIRTHDAY", ""),
#                                 "GENDER": patient_info.get("GENDER", ""),
#                                 "PATIENT_PHONE": patient_info.get("PATIENT_PHONE", ""),
#                             },
#                         }
#                     )
#             logger.info(f"Collected {len(detailed_appointments)} detailed appointments for account with address {address}.")
#             all_detailed_appointments.extend(detailed_appointments)

#         logger.info(f"Total collected {len(all_detailed_appointments)} detailed appointments from all accounts.")
        
#         # Отправка данных в API и получение order_mapping
#         order_mapping = send_appointments_to_api(all_detailed_appointments)
#         # Сохранение данных в БД с использованием order_mapping
#         save_appointments_to_db(all_detailed_appointments, order_mapping)

#         return all_detailed_appointments
#     except Exception as e:
#         logger.error(f"Error in test_request_task: {e}")
#         return {"error": str(e)}
    
@shared_task
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
            response = requests.get(status_url, params={"keys": order_key})
            response_data = response.json()
            if order_key in response_data:
                status_info = response_data[order_key].get("status_group_8")
                if status_info:
                    print(response_data)
                    new_status_name = status_info.get("name", status.status)
                    if status.status == new_status_name:
                        # Обновляем статус только если он изменился
                        print(f"Обновление статуса для order_key {order_key}: {new_status_name}")
                        status.status = new_status_name
                        status.save()
                        # Запрос на получение аудиозаписей
                        audio_response = requests.get(audio_url, params={"keys": order_key})
                        audio_data = audio_response.json()
                        print(f"Ответ сервера на аудиозаписи {audio_response.status_code}: {audio_data}")

                        if isinstance(audio_data, list):
                            for audio_entry in audio_data:
                                if audio_entry.get("order_key") == order_key:
                                    audio_link = audio_entry.get("link")
                                    print(f"Ссылка на аудио: {audio_link}")
                                    if audio_link:
                                        status.audio_link = audio_link
                                        try:
                                            status.save()
                                            print(f"Ссылка на аудио успешно сохранена для order_key {order_key}")
                                        except Exception as e:
                                            print(f"Ошибка при сохранении ссылки на аудио для order_key {order_key}: {e}")
                        else:
                            print(f"audio_data не является списком: {audio_data}")

    except Exception as e:
        print(f"Error in update_status_and_fetch_audio task: {e}")