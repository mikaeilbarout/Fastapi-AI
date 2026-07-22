import json
from redis.asyncio import Redis
from config import settings

redis_client = Redis.from_url(settings.redis_url, decode_responses=True)

HISTORY_TTL_SECONDS = 3600
MAX_HISTORY_LEN = 20


def _key(user_id: str) -> str:
    return f"chat:history:{user_id}"


async def add_message(user_id: str, role: str, content: str) -> None:
    key = _key(user_id)
    await redis_client.rpush(key, json.dumps({"role": role, "content": content}))
    await redis_client.ltrim(key, -MAX_HISTORY_LEN, -1)
    await redis_client.expire(key, HISTORY_TTL_SECONDS)


async def get_history(user_id: str) -> list[dict]:
    key = _key(user_id)
    raw = await redis_client.lrange(key, 0, -1)
    return [json.loads(item) for item in raw]