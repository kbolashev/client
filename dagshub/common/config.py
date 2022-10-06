import appdirs
import os

HOST_KEY = "DAGSHUB_CLIENT_HOST"
DEFAULT_HOST = "dagshub.com"
CLIENT_ID_KEY = "DAGSHUB_CLIENT_ID"
DEFAULT_CLIENT_ID = "32b60ba385aa7cecf24046d8195a71c07dd345d9657977863b52e7748e0f0f28"
TOKENS_CACHE_LOCATION_KEY = "DAGSHUB_CLIENT_TOKENS_CACHE"
DEFAULT_TOKENS_CACHE_LOCATION = os.path.join(
    appdirs.user_cache_dir("dagshub"), "tokens"
)
TOKENS_CACHE_SCHEMA_VERSION = "1"
DAGSHUB_USER_TOKEN_KEY = "DAGSHUB_USER_TOKEN"

hostname = os.environ.get(HOST_KEY, DEFAULT_HOST)
host = f"https://{hostname}"
client_id = os.environ.get(CLIENT_ID_KEY, DEFAULT_CLIENT_ID)
cache_location = os.environ.get(
    TOKENS_CACHE_LOCATION_KEY, DEFAULT_TOKENS_CACHE_LOCATION
)
token = os.environ.get(DAGSHUB_USER_TOKEN_KEY)
