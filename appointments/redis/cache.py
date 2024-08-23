from django.conf import settings
import logging
import openai
import os
import redis

logger = logging.getLogger(__name__)
openai.api_key = os.getenv("OPENAI_API_KEY")
redis_client = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)

def save_comment_to_redis(reception_code, comment):
    try:
        redis_client.rpush(reception_code, comment)
        redis_client.expire(reception_code, 600)  # Устанавливаем время жизни ключа в 10 минут
        print(f"Saved comment for {reception_code}: {comment}")
    except Exception as e:
        logger.error(f"Error saving comment to Redis: {e}")


def get_comments_from_redis(reception_code):
    try:
        comments = redis_client.lrange(reception_code, 0, -1)
        redis_client.delete(reception_code)
        print(f"Retrieved comments for {reception_code}: {comments}")
        return comments
    except Exception as e:
        logger.error(f"Error retrieving comments from Redis: {e}")
        return []