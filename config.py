import os
from dotenv import load_dotenv
import pytz

# Загружаем .env в окружение
load_dotenv()

# Токен бота
API_TOKEN = os.getenv('API_TOKEN')
if not API_TOKEN:
    raise RuntimeError("Не задана переменная окружения API_TOKEN")

# Параметры подключения к БД
DB_CONFIG = {
    'host':     os.getenv('DB_HOST', 'localhost'),
    'database': os.getenv('DB_NAME', 'taskmaster'),
    'user':     os.getenv('DB_USER', 'postgres'),
    'password': os.getenv('DB_PASSWORD', ''),
    'port':     os.getenv('DB_PORT', '5432'),
}

# Московский часовой пояс
MOSCOW_TZ = pytz.timezone('Europe/Moscow')
