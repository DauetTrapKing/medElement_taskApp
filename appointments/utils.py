from base64 import b64encode
from django.core.exceptions import ObjectDoesNotExist
from .models import Reviews, Statuses
from  gevent import sleep 
from django.utils import timezone
import os
import logging
import requests 


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


def send_to_telegram(reception_code):
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')  
    chat_id = os.getenv('TELEGRA_CHAT_ID')
    telegram_api_url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    try:
        # Получение данных из базы данных по RECEPTION_CODE
        review = Reviews.objects.get(RECEPTION_CODE=reception_code)
        doctor_rating = review.doctor_rating
        clinic_rating = review.clinic_rating
        doctor_name = review.doctor
        address = review.address
        audio_link = review.audio_link

        logger.debug(f"Fetched review: {review}")

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
                doctor_feedback=review.doctor_feedback or 'Отзыв отсутствует',
                clinic_rating=clinic_rating,
                clinic_feedback=review.clinic_feedback or 'Отзыв отсутствует',
                address=address or 'Адрес не указан',
                audio_link=audio_link or 'Ссылка отсутствует'
            )

            logger.debug(f"Generated message text: {text}")

            # Данные, которые мы отправляем в Telegram
            payload = {
                'chat_id': chat_id,
                'text': text,
                'parse_mode': 'Markdown'
            }

            logger.debug(f"Sending payload to Telegram: {payload}")

            # Отправка запроса с использованием JSON
            response = requests.post(telegram_api_url, json=payload)

            if response.status_code == 200:
                logger.debug("Message sent to Telegram successfully.")
            else:
                logger.error(f"Failed to send message to Telegram. Status code: {response.status_code}. Response: {response.text}")
        else:
            logger.debug("No message sent to Telegram. Ratings are higher than 3.")

    except ObjectDoesNotExist:
        logger.error(f"No review found for RECEPTION_CODE: {reception_code}")
    except Exception as e:
        logger.error(f"Error while sending message to Telegram: {str(e)}")


def send_appointments_to_api(detailed_appointments):
    print("penis")
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
                logger.info(f"Успешно отправлен пакет данных в API: order_key{batch}")
                response_data = response.json().get("data", {})

                for i, (key, value) in enumerate(response_data.items()):
                    reception_code = value.get("import_id")
                    order_key = value.get("order")
                    if reception_code and order_key:
                        order_mapping[reception_code] = order_key
                        # Правильное извлечение номера телефона и имени пациента
                        phone = batch[i]["phone"]  # Номер телефона из исходного запроса
                        full_name = batch[i]["full_name"]  # Полное имя из исходного запроса
                        # Сохранение данных в таблицу statuses
                        Statuses.objects.create(
                            status="scheduled",
                            RECEPTION_CODE=reception_code,
                            call_date=timezone.now(),  # Сохраняем текущее время
                            phone=phone,  # Используем правильный номер телефона
                            patient=full_name,  # Используем полное имя пациента
                            order_key=order_key,
                            # audio_link не включен, как и было указано
                        )
                    else:
                        logger.warning(f"Отсутствует import_id или order в ответе API: {value}")
                break  # Выход из цикла повторных попыток, если запрос успешен
            except requests.RequestException as e:
                if response.status_code == 401:
                    attempts += 1
                    logger.warning(
                        f"Произошла ошибка 401, попытка {attempts}/{max_attempts}. Повтор через 1 секунду..."
                    )
                    sleep(1)
                else:
                    logger.error(f"Ошибка при отправке пакета данных в API: {e}")
                    break  # Выход из цикла повторных попыток, если ошибка не 401

    batch = []
    for i, appointment in enumerate(detailed_appointments):
        phone = appointment["patient_info"].get("PATIENT_PHONE")
        if not phone:
            logger.warning(f"Нет номера телефона для записи: {appointment}. Пропускаем...")
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
            sleep(1)  # Пауза на 1 секунду между пакетами

    return order_mapping  # Возвращаем словарь с соответствиями import_id и order_key