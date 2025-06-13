import os
from dotenv import load_dotenv
import psycopg2


class Database:
    """
    Класс для работы с PostgreSQL:
      - get_db_connection() — возвращает новое соединение
      - init_db()           — инициализирует (создаёт) таблицы и индексы
    """

    def __init__(self):
        # Загружаем .env при создании экземпляра
        load_dotenv()

        # Параметры подключения
        self._db_config = {
            'host':     os.getenv('DB_HOST', 'localhost'),
            'database': os.getenv('DB_NAME', 'taskmaster'),
            'user':     os.getenv('DB_USER', 'postgres'),
            'password': os.getenv('DB_PASSWORD', ''),
            'port':     os.getenv('DB_PORT', '5432'),
        }

    def get_db_connection(self):
        """
        Возвращает новое соединение к базе данных.
        Вызывает исключение, если не получилось подключиться.
        """
        return psycopg2.connect(**self._db_config)

    def init_db(self):
        """
        Создаёт необходимые таблицы и индексы, если их нет.
        После выполнения соединение и курсор закрываются автоматически.
        """
        conn = self.get_db_connection()
        cur = conn.cursor()

        # Таблица пользователей
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id       BIGINT      PRIMARY KEY,
                username      VARCHAR(100),
                registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # Таблица задач
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                task_id     SERIAL       PRIMARY KEY,
                user_id     BIGINT       REFERENCES users(user_id),
                title       VARCHAR(255) NOT NULL,
                description TEXT,
                priority    VARCHAR(10)  CHECK (priority IN ('high', 'medium', 'low')) DEFAULT 'medium',
                category    VARCHAR(100),
                tags        VARCHAR(255)[],
                deadline    TIMESTAMP WITH TIME ZONE,
                status      VARCHAR(20)  CHECK (status IN ('active', 'completed', 'overdue')) DEFAULT 'active',
                created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            );
        """)

        # Индексы для ускорения выборок
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id  ON tasks(user_id);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status   ON tasks(status);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);")

        conn.commit()
        cur.close()
        conn.close()
