from base64 import b64encode
from urllib.parse import urlencode
from datetime import datetime, timedelta
from appointments.utils import make_url, get_headers
from gevent import sleep
import os
import requests
import logging
import time
import pytz
import redis

logger = logging.getLogger(__name__)

REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_DB = 0
redis_client = redis.Redis(host="localhost", port=6379, db=0)

BASE_URL = "https://api.medelement.com"
def fetch_json(url, headers, params=None):
    try:
        encoded_params = urlencode(params) if params else ""
        logger.info(
            f"Fetching JSON from {url} with params: {encoded_params} and headers: {headers}"
        )
        response = requests.post(url, headers=headers, data=encoded_params)
        response.raise_for_status()
        logger.info(f"Response status: {response.status_code}")
        
        try:
            json_data = response.json()
            return json_data
        except ValueError as ve:
            logger.error(f"Error decoding JSON: {ve}, response text: {response.text}")
            return None
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err}")
        return {"error": "http", "status_code": response.status_code}
    except Exception as err:
        logger.error(f"Other error occurred: {err}")
        return None


def find_appointments(username, password, address):
    tz = pytz.timezone("Asia/Qyzylorda")
    now = datetime.now(tz)
    today = now.strftime("%d.%m.%Y")
    tomorrow = (now + timedelta(days=1)).strftime("%d.%m.%Y")
    
    # Формируем ключ для хранения skip значений
    redis_skip_key = f"appointments_skip_{username}_{today}"

    # Проверка существования ключа для текущего дня
    if not redis_client.exists(redis_skip_key):
        # Если ключа для текущего дня не существует, обнуляем skip
        logger.info(f"New day detected. Deleting all previous skip values.")
        keys = redis_client.keys("appointments_skip_*")
        for key in keys:
            redis_client.delete(key)
            logger.info(f"Successfully deleted skip value for key: {key}")

        # Инициализируем skip как 0 для нового дня
        skip = 0
        logger.info(f"Initializing skip value to 0 for {username} on {today}.")
        
        # Сохраняем ключ в Redis
        redis_client.set(redis_skip_key, skip, ex=86400)
        logger.info(f"Set Redis key: {redis_skip_key} with initial skip value: {skip}")
    else:
        # Используем существующее значение skip
        skip = max(0, int(redis_client.get(redis_skip_key) or 0) - 300)
        skip = max(0, skip)  # Гарантируем, что skip >= 0
        logger.info(f"Redis key exists. Starting with skip value: {skip} for date: {today}")
    
    url = make_url(BASE_URL, "/v2/doctor/reception/search")
    data = []
    two_hours_ago = now - timedelta(hours=2)

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
        
        if not json_data:
            logger.warning(f"No data found for username: {username} or fetch failed.")
            break

        if "receptions" not in json_data:
            logger.warning(f"'receptions' key not found in response: {json_data}")
            break

        for reception in json_data["receptions"]:
            reception_time = tz.localize(
                datetime.strptime(reception["ENDTIME"], "%Y-%m-%d %H:%M:%S")
            )
            if two_hours_ago <= reception_time <= now:
                reception["address"] = address  # Устанавливаем адрес в reception
                data.append(reception)

        if len(json_data["receptions"]) < 50:
            break

        skip += 50
        redis_client.set(redis_skip_key, skip, ex=86400)  # Сохраняем новое значение skip
        logger.info(f"Updated Redis key: {redis_skip_key} with new skip value: {skip}")
        sleep(1)

    logger.info(f"Found {len(data)} appointments for address: {address}")
    return data


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
                sleep(1)
                params["skip"] = skip
                headers = get_headers(username, password)
                json_data = fetch_json(url, headers, params=params)
                if not json_data or "receptions" not in json_data:
                    break

                for reception in json_data["receptions"]:
                    reception_time = tz.localize(
                        datetime.strptime(reception["ENDTIME"], "%Y-%m-%d %H:%M:%S")
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
                sleep(10)
            elif "429" in str(e):
                attempts += 1
                logger.warning(
                    f"429 error occurred, attempt {attempts}/{max_attempts}. Retrying in 60 seconds..."
                )
                sleep(60)
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

            # Получаем первый номер телефона и очищаем его от нецифровых символов
            phone = patient_data.get("PATIENT_PHONE_1")
            patient_phone = "".join(filter(str.isdigit, phone)) if phone else None
            if patient_phone:
                patient_phone = f"+7{patient_phone}"
            # Формируем результативный словарь
            patient_info = {
                "NAME": patient_data.get("NAME"),
                "LASTNAME": patient_data.get("LASTNAME"),
                "PATIENT_PHONE": patient_phone,
            }

            # Если отчество существует, добавляем его в словарь
            middlename = patient_data.get("MIDDLENAME")
            if middlename:
                patient_info["MIDDLENAME"] = middlename

            return patient_info

        except requests.RequestException as e:
            if "429" in str(e):
                attempts += 1
                logger.warning(
                    f"429 ошибка, попытка {attempts}/{max_attempts}. Повтор через 60 секунд..."
                )
                sleep(60)
            else:
                logger.error(f"Ошибка при получении информации о пациенте: {e}")
                return None
    logger.error("Достигнуто максимальное количество попыток. Завершаем задачу.")
    return None
