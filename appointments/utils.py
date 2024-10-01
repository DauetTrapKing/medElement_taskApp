from base64 import b64encode
from django.core.exceptions import ObjectDoesNotExist
from .models import Reviews, Statuses
from  gevent import sleep 
from appointments.openai.analysisData import analyze_transcription
from django.utils import timezone
import openai
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


def process_status_and_audio():
    try:
        logger.info("Starting process_status_and_audio task")
        api_key = os.getenv("ACS_API_KEY")
        status_url = f"https://back.crm.acsolutions.ai/api/v2/orders/public/{api_key}/get_status"
        audio_url = f"https://back.crm.acsolutions.ai/api/v2/orders/public/{api_key}/get_calls"

        # Получаем все записи из таблицы Status
        all_statuses = Statuses.objects.all()
        for status in all_statuses:
            order_key = status.order_key
            logger.info(f"Processing order_key: {order_key}")

            # Проверяем, является ли текущий статус "scheduled"
            if status.status == "scheduled":
                logger.info(f"Order key {order_key} has status 'scheduled', proceeding with updates")

                # Получаем новый статус и аудио
                new_status_name, audio_link = fetch_status_and_audio(api_key, status_url, audio_url, order_key)

                # Обновление статуса, если новый статус отличается от текущего
                if new_status_name and status.status != new_status_name:
                    logger.info(f"Updating status for order_key {order_key}")
                    status.status = new_status_name
                    status.save()

                # Если аудио ссылка найдена, скачиваем аудио и обрабатываем
                if audio_link:
                    logger.info(f"Processing audio for order_key {order_key}")
                    status.audio_link = audio_link
                    status.save()

                    # Приведение RECEPTION_CODE к строке и логирование
                    reception_code = str(status.RECEPTION_CODE).strip()
                    logger.info(f"Attempting to retrieve review with RECEPTION_CODE: '{reception_code}'")

                    # Проверка, чтобы RECEPTION_CODE не было "Unknown" или пустым
                    if reception_code and reception_code != "Unknown":
                        try:
                            review = Reviews.objects.get(RECEPTION_CODE=reception_code)
                            logger.info(f"Review found for RECEPTION_CODE {reception_code}")

                            # Обновляем аудио ссылку в Reviews
                            review.audio_link = audio_link
                            review.save()

                            # Скачиваем аудиофайл по полученной ссылке
                            save_path = f"/tmp/{order_key}.mp3"
                            downloaded_audio = download_audio(audio_link, save_path)

                            if downloaded_audio:
                                transcription = transcribe_audio(downloaded_audio)
                                if transcription:
                                    logger.info(f"Transcription successful for order_key {order_key}")

                                    # Выполняем анализ распознанного текста
                                    knowledge_base = {...}  # Ваша база данных фраз робота
                                    analysis_result = analyze_transcription(knowledge_base, transcription)

                                    if analysis_result:
                                        # Логирование анализа для проверки
                                        logger.debug(f"Analysis result: {analysis_result}")

                                        # Обновляем запись в таблице Reviews с результатами анализа
                                        review.doctor_rating = analysis_result.get("doctor_rating")
                                        review.doctor_feedback = analysis_result.get("doctor_feedback")
                                        review.clinic_rating = analysis_result.get("clinic_rating")
                                        review.clinic_feedback = analysis_result.get("clinic_feedback")
                                        # Сохраняем изменения в базе данных
                                        review.save()
                                        logger.info(f"Review updated for RECEPTION_CODE {reception_code}")
                                    else:
                                        logger.warning(f"Analysis failed for transcription of order_key {order_key}")
                                else:
                                    logger.warning(f"Transcription failed for order_key {order_key}")
                            else:
                                logger.warning(f"Failed to download audio for order_key {order_key}")

                        except Reviews.DoesNotExist:
                            logger.error(f"Review not found for RECEPTION_CODE {reception_code}")
                            continue
                    else:
                        logger.warning(f"Invalid RECEPTION_CODE: '{reception_code}' for order_key {order_key}")

            else:
                logger.info(f"Skipping order_key {order_key}, status is not 'scheduled'")

    except Exception as e:
        logger.error(f"Error in process_status_and_audio: {e}")
        return {"error": str(e)}


def fetch_status_and_audio(api_key, status_url, audio_url, order_key): 
    try:
        # Запрос на получение статуса
        logger.info(f"Fetching status for order_key: {order_key}")
        status_response = requests.get(status_url, params={"keys": order_key})

        # Проверка успешности запроса
        if status_response.status_code != 200:
            logger.error(f"Failed to fetch status for order_key {order_key}. Status code: {status_response.status_code}")
            return None, None

        try:
            response_data = status_response.json()
        except ValueError as e:
            logger.error(f"Failed to parse JSON for order_key {order_key}: {e}")
            return None, None

        # Проверяем, что это словарь и он содержит нужный ключ
        if isinstance(response_data, dict) and order_key in response_data:
            status_info = response_data[order_key].get("status_group_8", {})
            if isinstance(status_info, dict):
                new_status_name = status_info.get("name")
                logger.info(f"Status retrieved for order_key {order_key}: {new_status_name}")
            else:
                logger.warning(f"No 'status_group_8' data or invalid format for order_key {order_key}")
                new_status_name = None
        else:
            logger.warning(f"No valid status data for order_key {order_key}: {response_data}")
            new_status_name = None

        # Запрос на получение аудиозаписей
        audio_response = requests.get(audio_url, params={"keys": order_key})

        # Проверка успешности запроса
        if audio_response.status_code != 200:
            logger.error(f"Failed to fetch audio for order_key {order_key}. Status code: {audio_response.status_code}")
            return new_status_name, None

        try:
            audio_data = audio_response.json()
        except ValueError as e:
            logger.error(f"Failed to parse audio JSON for order_key {order_key}: {e}")
            return new_status_name, None

        # Проверяем, что аудиоданные — это список
        if isinstance(audio_data, list) and len(audio_data) > 0:
            last_audio_entry = audio_data[-1]
            if isinstance(last_audio_entry, dict) and last_audio_entry.get("order_key") == order_key:
                audio_link = last_audio_entry.get("link")
                if audio_link and audio_link.startswith("http"):
                    logger.info(f"Audio link retrieved for order_key {order_key}: {audio_link}")
                    return new_status_name, audio_link
                else:
                    logger.warning(f"Invalid audio link for order_key {order_key}: {audio_link}")
                    return new_status_name, None
        else:
            logger.warning(f"No audio data found or invalid format for order_key {order_key}: {audio_data}")

        return new_status_name, None

    except requests.exceptions.RequestException as req_err:
        logger.error(f"Network error while fetching status or audio for order_key {order_key}: {req_err}")
    except KeyError as key_err:
        logger.error(f"Missing expected data in API response for order_key {order_key}: {key_err}")
    except Exception as e:
        logger.error(f"Unexpected error fetching status or audio for order_key {order_key}: {e}")

    return None, None


def download_audio(audio_url, save_path):
    try:
        # Проверка и создание директории, если она не существует
        directory = os.path.dirname(save_path)
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")

        logger.info(f"Downloading audio from {audio_url}")
        response = requests.get(audio_url)
        
        if response.status_code == 200:
            with open(save_path, 'wb') as audio_file:
                audio_file.write(response.content)
            logger.info(f"Audio successfully downloaded and saved to {save_path}")
            return save_path
        else:
            logger.error(f"Failed to download audio. Status code: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error downloading audio from {audio_url}: {e}")
        return None

def transcribe_audio(audio_file_path):
    try:
        logger.info(f"Starting audio transcription for file: {audio_file_path}")
        with open(audio_file_path, 'rb') as audio_file:
            response = openai.Audio.transcribe(
                model="whisper-1",
                file=audio_file
            )
        transcription_text = response['text']
        logger.info(f"Transcription completed for file: {audio_file_path}")
        print(transcription_text)
        return transcription_text
    except Exception as e:
        logger.error(f"Error during transcription for file {audio_file_path}: {e}")
        return None


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


def process_excel_data(df):
    for _, row in df.iterrows():
        order_key = row['Order key']
        result = row['Result']
        dialog_text = row['Dialog text']
        # Проверяем, есть ли запись в базе данных
        if not YourModel.objects.filter(order_key=order_key).exists() and result != "в процессе":
            # Отправляем диалог в GPT для анализа
            gpt_response = send_to_gpt(dialog_text)

            # Сохраняем результат в базу данных
            YourModel.objects.create(order_key=order_key, gpt_response=gpt_response)


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