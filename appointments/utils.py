from base64 import b64encode
from urllib.parse import urlencode
# from datetime import datetime, timedelta
# from .models import Reviews, Statuses
# from django.utils import timezone
import os
import logging
import requests 
import time


###UTILS
logger = logging.getLogger(__name__)
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


def send_to_telegram(message): 
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')  
    chat_id = os.getenv('TELEGRA_CHAT_ID')
    telegram_api_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    doctor_rating = int(message.get('doctor_rating'))
    clinic_rating = int(message.get('clinic_rating'))
    doctor_name = message.get('doctor')
    address = message.get('address')
    audio_link = message.get('audio_link')
    
    # Проверка условия на отправку сообщения
    if (doctor_rating is not None or clinic_rating is not None) and (doctor_rating <= 3 or clinic_rating <= 3):
        text = (
            '*НЕГАТИВНЫЙ ОТЗЫВ*\n\n'
            '*Имя врача:* {doctor_name}\n'
            '*Оценка врача:* {doctor_rating}\n'
            '*Отзыв о враче:* {doctor_feedback}\n'
            '*Оценка клиники:* {clinic_rating}\n'
            '*Отзыв о клинике:* {clinic_feedback}\n'
            '*Адрес:* {address}\n'
            '*Ссылка на аудио:* [Аудиозапись]({audio_link})\n'
        ).format(
            doctor_name=doctor_name or 'Имя не указано',
            doctor_rating=doctor_rating,
            doctor_feedback=message.get('doctor_feedback', 'Отзыв отсутствует'),
            clinic_rating=clinic_rating,
            clinic_feedback=message.get('clinic_feedback', 'Отзыв отсутствует'),
            address=address or 'Адрес не указан',
            audio_link=audio_link or 'Ссылка отсутствует'
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
# ###MED_ELEMENT
# def fetch_json(url, headers, params=None):
#     encoded_params = urlencode(params)
#     try:
#         logger.info(
#             f"Fetching JSON from {url} with params: {encoded_params} and headers: {headers}"
#         )
#         response = requests.post(url, headers=headers, data=encoded_params)
#         response.raise_for_status()
#         logger.info(f"Response status: {response.status_code}")
#         return response.json()
#     except requests.exceptions.HTTPError as http_err:
#         logger.error(f"HTTP error occurred: {http_err}")
#         return {"error": "http", "status_code": response.status_code}
#     except Exception as err:
#         logger.error(f"Other error occurred: {err}")
#         return None


# def find_appointments(username, password, address):
#     tz = pytz.timezone("Asia/Qyzylorda")
#     now = datetime.now(tz)
#     two_hours_ago = now - timedelta(hours=2)
#     today = now.strftime("%d.%m.%Y")
#     tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")

#     redis_skip_key = f"appointments_skip_{username}"
#     skip = int(redis_client.get(redis_skip_key) or 0)
#     skip = max(0, skip - 200)
#     logger.info(f"Starting with skip value: {skip}")
#     url = make_url(BASE_URL, "/v2/doctor/reception/search")
#     data = []
#     while True:
#         params = {
#             "begin_datetime": today,
#             "end_datetime": tomorrow,
#             "skip": skip,
#             "removed": 0,
#         }
        
#         logger.info(f"Fetching data with params: {params} and address: {address}")

#         headers = get_headers(username, password)
#         json_data = fetch_json(url, headers, params=params)
        
#         if not json_data or "receptions" not in json_data:
#             logger.warning(f"No data found for username: {username}")
#             break

#         for reception in json_data["receptions"]:
#             reception_time = tz.localize(
#                 datetime.strptime(reception["STARTTIME"], "%Y-%m-%d %H:%M:%S")
#             )
#             if two_hours_ago <= reception_time <= now:
#                 reception["address"] = address  # Устанавливаем адрес в reception
#                 data.append(reception)

#         if len(json_data["receptions"]) < 50:
#             break

#         skip += 50
#         redis_client.set(redis_skip_key, skip, ex=86400)
#         time.sleep(1)

#     logger.info(f"Found {len(data)} appointments for address: {address}")
#     return data


# def get_doctor_info(patient_code, two_hours_ago, now, username, password):
#     max_attempts = 5
#     attempts = 0
#     tz = pytz.timezone("Asia/Astana")
#     while attempts < max_attempts:
#         try:
#             today = now.strftime("%d.%m.%Y")
#             tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")
#             params = {
#                 "patient_code": patient_code,
#                 "begin_datetime": today,
#                 "end_datetime": tomorrow,
#                 "removed": 0,
#                 "active": 0,
#                 "only_ambulator": 0,
#             }

#             url = make_url(BASE_URL, "/v2/doctor/reception/search_with_pd")
#             skip = 0
#             recent_receptions = []
#             while True:
#                 time.sleep(1)
#                 params["skip"] = skip
#                 headers = get_headers(username, password)
#                 json_data = fetch_json(url, headers, params=params)
#                 if not json_data or "receptions" not in json_data:
#                     break

#                 for reception in json_data["receptions"]:
#                     reception_time = tz.localize(
#                         datetime.strptime(reception["STARTTIME"], "%Y-%m-%d %H:%M:%S")
#                     )
#                     if two_hours_ago <= reception_time <= now:
#                         recent_receptions.append(reception)

#                 if len(json_data["receptions"]) < 50:
#                     break
#                 skip += 50
#             return recent_receptions[0] if recent_receptions else None
#         except Exception as e:
#             if "502" in str(e):
#                 attempts += 1
#                 logger.warning(
#                     f"502 error occurred, attempt {attempts}/{max_attempts}. Retrying in 10 seconds..."
#                 )
#                 time.sleep(10)
#             elif "429" in str(e):
#                 attempts += 1
#                 logger.warning(
#                     f"429 error occurred, attempt {attempts}/{max_attempts}. Retrying in 60 seconds..."
#                 )
#                 time.sleep(60)
#             else:
#                 logger.error(f"Error in get_doctor_info: {e}")
#                 return None
#     logger.error("Max attempts reached. Terminating the task.")
#     return None


# def get_patient_info(patient_code, username, password):
#     max_attempts = 5
#     attempts = 0
#     while attempts < max_attempts:
#         try:
#             url = f"{BASE_URL}/doctor/v1/patient/{patient_code}"
#             response = requests.get(url, headers=get_headers(username, password))
#             response.raise_for_status()
#             patient_data = response.json()

#             phones = []
#             for i in range(1, 5):
#                 phone_key = f"PATIENT_PHONE_{i}"
#                 phone = patient_data.get(phone_key)
#                 if isinstance(phone, list):
#                     phones.extend(phone)
#                 elif phone:
#                     phones.append(phone)

#             patient_phone = ", ".join(phones)  # Объединение номеров в строку

#             return {
#                 "NAME": patient_data.get("NAME"),
#                 "LASTNAME": patient_data.get("LASTNAME"),
#                 "MIDDLENAME": patient_data.get("MIDDLENAME"),

#                 "PATIENT_PHONE": patient_phone,
#             }
#         except requests.RequestException as e:
#             if "429" in str(e):
#                 attempts += 1
#                 logger.warning(
#                     f"429 error occurred, attempt {attempts}/{max_attempts}. Retrying in 60 seconds..."
#                 )
#                 time.sleep(60)
#             else:
#                 logger.error(f"Error fetching patient info: {e}")
#                 return None
#     logger.error("Max attempts reached. Terminating the task.")
#     return None

# ###DATABASE
# def save_appointments_to_db(detailed_appointments, order_mapping):
#     try:
#         for appointment in detailed_appointments:
#             appointment_info = appointment["appointment"]
#             doctor_info = appointment["doctor_info"]
#             patient_info = appointment["patient_info"]
#             reception_code = appointment_info.get("RECEPTION_CODE")
#             patient_phone = patient_info.get("PATIENT_PHONE")
            
#             if not reception_code:
#                 logger.error(f"Missing 'RECEPTION_CODE' in appointment: {appointment}")
#                 continue

#             if not patient_phone:
#                 logger.warning(f"Missing 'PATIENT_PHONE' in appointment: {appointment}. Skipping...")
#                 continue

#             reception_date = datetime.strptime(appointment_info["STARTTIME"], "%Y-%m-%d %H:%M:%S")

#             # Получение адреса из appointment
#             address = appointment_info.get("address")
#             # Получение имени доктора
#             doctor_name = doctor_info.get("SPECIALIST_FULLNAME", "Unknown Doctor")

#             # Проверка, существует ли запись с таким же RECEPTION_CODE
#             review = Reviews.objects.filter(RECEPTION_CODE=reception_code).first()
#             if review:
#                 logger.warning(f"Duplicate RECEPTION_CODE found: {reception_code}")
#             else:
#                 # Создание новой записи в Review
#                 review = Reviews(
#                     number=patient_phone,
#                     patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
#                     reception_date=reception_date.date(),
#                     reception_time=reception_date.time(),
#                     doctor=doctor_name,  # Сохраняем имя доктора в Review
#                     RECEPTION_CODE=reception_code,
#                     address=address,
#                 )
#                 review.save()
#                 logger.info(f"Successfully added/updated review in database for address: {address}")

#             # Добавление order_key в Status
#             order_key = order_mapping.get(reception_code)
#             if not order_key:
#                 logger.warning(f"Missing order_key for RECEPTION_CODE: {reception_code}. Skipping status save...")
#                 continue

#             status = Statuses.objects.filter(RECEPTION_CODE=reception_code).first()
#             if not status:
#                 status = Statuses(
#                     number=patient_phone,
#                     patient=f"{patient_info.get('NAME', '')} {patient_info.get('LASTNAME', '')} {patient_info.get('MIDDLENAME', '')}",
#                     status="Scheduled",
#                     RECEPTION_CODE=reception_code,
#                     call_date=timezone.now(),
#                     order_key=order_key,
#                 )
#             else:
#                 status.order_key = order_key
#             status.save()
#             logger.info(f"Successfully added/updated status in database with order_key: {order_key}")
#     except Exception as e:
#         logger.error(f"Error saving data to database: {e}")


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

        if len(batch) == 10 or (i + 1) == len(detailed_appointments):
            send_batch(batch)
            batch = []
            time.sleep(1)  # Pause for 1 second between batches

    return order_mapping  # Возвращаем словарь с соответствиями import_id и order_keyimport os
