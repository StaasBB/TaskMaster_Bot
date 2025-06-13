import os  # для работы с переменными окружения и файловой системой
import re  # модуль для работы с регулярными выражениями (не используется напрямую, но оставлен для потенциальных проверок)

from datetime import datetime, timedelta  # для работы с датой и временем
import pytz  # управление часовыми поясами

import telebot  # библиотека для работы с Telegram Bot API
from telebot import types  # модуль с типами для создания кнопок и разметки

import psycopg2  # библиотека для работы с PostgreSQL
from dotenv import load_dotenv  # загрузка переменных окружения из .env файла

# Загрузка переменных окружения из файла .env в окружение процесса
load_dotenv()

# Инициализация бота: получение токена из переменных окружения
API_TOKEN = os.getenv('API_TOKEN')
bot = telebot.TeleBot(API_TOKEN)  # создание экземпляра бота


# Функция для получения нового соединения с базой данных PostgreSQL
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),        # адрес хоста БД
        database=os.getenv('DB_NAME', 'taskmaster'),   # имя базы данных
        user=os.getenv('DB_USER', 'postgres'),         # пользователь БД
        password=os.getenv('DB_PASSWORD', ''),         # пароль
        port=os.getenv('DB_PORT', '5432')              # порт
    )


# Инициализация базы данных: создание необходимых таблиц и индексов
def init_db():
    conn = get_db_connection()  # открываем соединение
    cur = conn.cursor()        # создаем курсор для выполнения SQL

    # Создаем таблицу пользователей, если она не существует
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id      BIGINT      PRIMARY KEY,
            username     VARCHAR(100),
            registered_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
    )

    # Создаем таблицу задач, если она не существует
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id    SERIAL       PRIMARY KEY,
            user_id    BIGINT       REFERENCES users(user_id),
            title      VARCHAR(255) NOT NULL,
            description TEXT,
            priority   VARCHAR(10)  CHECK (priority IN ('high', 'medium', 'low')) DEFAULT 'medium',
            category   VARCHAR(100),
            tags       VARCHAR(255)[],
            deadline   TIMESTAMP WITH TIME ZONE,
            status     VARCHAR(20)  CHECK (status IN ('active', 'completed', 'overdue')) DEFAULT 'active',
            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        );
        """
    )

    # Добавляем индексы для ускорения поиска по наиболее частым полям
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id   ON tasks(user_id);")  # индекс на user_id
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_status    ON tasks(status);")   # индекс на status
    cur.execute("CREATE INDEX IF NOT EXISTS idx_tasks_deadline  ON tasks(deadline);") # индекс на deadline

    conn.commit()  # сохраняем изменения
    cur.close()     # закрываем курсор
    conn.close()    # закрываем соединение


# Функция для отображения главного меню пользователю
def show_main_menu(chat_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)  # создаем клавиатуру снизу
    # добавляем кнопки для создания новой задачи и просмотра существующих
    markup.add(types.KeyboardButton('/newtask'), types.KeyboardButton('/mytasks'))
    bot.send_message(chat_id, "Главное меню:", reply_markup=markup)  # отправляем сообщение с клавиатурой

#парсер даты
def parse_deadline(text):
    """
    Преобразует текстовый ввод пользователя в UTC-время дедлайна.
    Поддерживаются варианты:
      1) 'через N часов M минут'
      2) 'через N минут'
      3) 'через N дней [в HH:MM]'
      4) 'сегодня [в HH:MM]'
      5) 'завтра [в HH:MM]'
      6) 'DD.MM.YYYY[ HH:MM]'
      7) 'D месяц [в HH:MM]'
    """
    moscow = pytz.timezone('Europe/Moscow')
    now = datetime.now(moscow)
    text = text.lower().strip()

    def local_dt(year, month, day, hour=23, minute=59):
        # Создаём datetime в московской зоне и конвертируем в UTC
        naive = datetime(year, month, day, hour, minute)
        return moscow.localize(naive).astimezone(pytz.utc)

    # 1) 'через N часов [M минут]'
    match = re.match(
        r'через\s+(\d+)\s*(?:час|часа|часов)'
        r'(?:\s+(\d+)\s*(?:минута|минуты|минут|минуту))?$', text
    )
    if match:
        hours = int(match.group(1))
        minutes = int(match.group(2)) if match.group(2) else 0
        return (now + timedelta(hours=hours, minutes=minutes)).astimezone(pytz.utc)

    # 2) 'через N минут'
    match = re.match(r'через\s+(\d+)\s*(?:минута|минуты|минут|минуту)$', text)
    if match:
        minutes = int(match.group(1))
        return (now + timedelta(minutes=minutes)).astimezone(pytz.utc)

    # 3) 'через N дней [в HH:MM]'
    time_pt = r'(?:\s*(?:в)?\s*(\d{1,2}):(\d{2}))?'
    match = re.match(rf'через\s+(\d+)\s*(?:день|дня|дней){time_pt}$', text)
    if match:
        days = int(match.group(1))
        hour = int(match.group(2)) if match.group(2) else 23
        minute = int(match.group(3)) if match.group(3) else 59
        future = now + timedelta(days=days)
        return local_dt(future.year, future.month, future.day, hour, minute)

    # 4) 'сегодня [в HH:MM]'
    match = re.match(rf'сегодня{time_pt}$', text)
    if match:
        hour = int(match.group(1)) if match.group(1) else 23
        minute = int(match.group(2)) if match.group(2) else 59
        return local_dt(now.year, now.month, now.day, hour, minute)

    # 5) 'завтра [в HH:MM]'
    match = re.match(rf'завтра{time_pt}$', text)
    if match:
        hour = int(match.group(1)) if match.group(1) else 23
        minute = int(match.group(2)) if match.group(2) else 59
        tm = now + timedelta(days=1)
        return local_dt(tm.year, tm.month, tm.day, hour, minute)

    # 6) 'DD.MM.YYYY[ HH:MM]'
    match = re.match(rf'(\d{{1,2}})\.(\d{{1,2}})\.(\d{{2,4}}){time_pt}$', text)
    if match:
        d, m, y = map(int, match.groups()[:3])
        y += 2000 if y < 100 else 0  # годы 00–99 трактуем как 2000–2099
        hour = int(match.group(4)) if match.group(4) else 23
        minute = int(match.group(5)) if match.group(5) else 59
        return local_dt(y, m, d, hour, minute)

    # 7) 'D месяц [в HH:MM]'
    match = re.match(rf'(\d{{1,2}})\s+([а-яё]+){time_pt}$', text)
    if match:
        day = int(match.group(1))
        month_str = match.group(2)
        month_names = [
            "января","февраля","марта","апреля","мая","июня",
            "июля","августа","сентября","октября","ноября","декабря"
        ]
        try:
            month = month_names.index(month_str) + 1
        except ValueError:
            raise ValueError("Неверное название месяца")
        hour = int(match.group(3)) if match.group(3) else 23
        minute = int(match.group(4)) if match.group(4) else 59
        return local_dt(now.year, month, day, hour, minute)

    # Если ни один шаблон не подошёл, кидаем исключение
    raise ValueError("Неверный формат даты.")

# Преобразование дедлайна в строку с датой, временем и относительным временем
def format_deadline(deadline):
    """Всегда выводит дату+время и относительный маркер."""
    if not deadline:
        return ""  # если дедлайн не задан, возвращаем пустую строку

    # Переводим время в московский часовой пояс для отображения
    moscow = pytz.timezone('Europe/Moscow')
    dl_local = deadline.astimezone(moscow)
    now_local = datetime.now(pytz.utc).astimezone(moscow)

    date_str = dl_local.strftime('%d.%m.%Y %H:%M')  # форматируем дату и время
    delta = dl_local - now_local
    secs = delta.total_seconds()

    # Разница в полных днях между датами
    date_diff = (dl_local.date() - now_local.date()).days

    # часы и минуты из абсолютного количества секунд
    hours = int(abs(secs) // 3600)
    minutes = int((abs(secs) % 3600) // 60)

    # дедлайн сегодня
    if date_diff == 0:
        if secs >= 0:
            return f"⏰ {date_str}, сегодня через {hours:02d}:{minutes:02d}"
        else:
            return f"❗️ {date_str}, сегодня {hours:02d}:{minutes:02d} назад"

    # дедлайн в будущем (завтра или позже)
    if date_diff > 0:
        rel = "завтра" if date_diff == 1 else f"через {date_diff} дн."
        return f"⏰ {date_str}, {rel}"

    # дедлайн просрочен (день назад или раньше)
    ago = abs(date_diff)
    rel = "1 дн. назад" if ago == 1 else f"{ago} дн. назад"
    return f"❗️ {date_str}, {rel}"


# Функция для получения смайлика в зависимости от приоритета задачи
def get_priority_emoji(priority):
    # словарь соответствия приоритета и эмодзи
    return {'high':'🔴','medium':'🟡','low':'🟢'}.get(priority, '')


# Формируем текстовое представление задачи для отправки пользователю
def format_task(task):
    emoji = get_priority_emoji(task['priority'])  # берем эмодзи для приоритета
    deadline_text = format_deadline(task['deadline'])  # форматируем дедлайн
    # если есть теги, преобразуем их в строку вида #тег
    tags_text = f"\n🏷 {' '.join(['#' + tag for tag in task['tags']])}" if task['tags'] else ""

    # собираем основное сообщение
    message = f"{emoji} *{task['title']}*"
    if task['description']:
        message += f"\n📝 {task['description']}"
    if deadline_text:
        message += f"\n{deadline_text}"
    if tags_text:
        message += tags_text

    message += "\n──────────────────"  # разделитель
    return message


# Формируем inline-кнопки для управления задачей (завершить, удалить и т.д.)
def create_task_actions_markup(task_id):
    markup = types.InlineKeyboardMarkup()
    # верхний ряд кнопок: Завершить и Удалить
    markup.row(
        types.InlineKeyboardButton("✅ Завершить", callback_data=f"complete_{task_id}"),
        types.InlineKeyboardButton("🗑 Удалить",   callback_data=f"delete_{task_id}")
    )
    # нижний ряд кнопок: Перенести и Редактировать
    markup.row(
        types.InlineKeyboardButton("🔄 Перенести", callback_data=f"reschedule_{task_id}"),
        types.InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{task_id}"),
    )
    return markup


# Обработчик команды /start: регистрация пользователя и приветствие
@bot.message_handler(commands=['start'])
def send_welcome(message):
    conn = get_db_connection()  # подключаемся к БД
    cur = conn.cursor()        # создаем курсор

    try:
        # пытаемся вставить пользователя (ON CONFLICT — если уже есть, ничего не делаем)
        cur.execute(
            "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
            (message.from_user.id, message.from_user.username)
        )
        conn.commit()  # сохраняем изменения
    except Exception as e:
        conn.rollback()  # откатываем транзакцию при ошибке
        print(f"Error registering user: {e}")
    finally:
        cur.close()    # закрываем курсор
        conn.close()   # закрываем соединение

    # показываем главное меню и отправляем приветственное сообщение
    show_main_menu(message.chat.id)
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я TaskMaster Bot - твой личный помощник для управления задачами.\n\n"
        "Используй команды:\n"
        "/newtask - создать новую задачу\n"
        "/mytasks - просмотреть свои задачи\n\n"
        "Или выбери действие ниже:"
    )
@bot.message_handler(commands=['newtask'])
def new_task(message):
    # Обработчик команды /newtask: запускает диалог создания новой задачи
    # Отправляем пользователю сообщение с просьбой ввести название задачи
    msg = bot.send_message(
        message.chat.id,
        "📝 Введите название задачи:",
        reply_markup=types.ReplyKeyboardRemove()  # убираем любую кастомную клавиатуру
    )
    # Регистрируем следующий шаг — после ввода названия будет вызвана функция process_task_title
    bot.register_next_step_handler(msg, process_task_title)


def process_task_title(message):
    # Сохраняем chat_id и текст, введённый пользователем, как заголовок задачи
    chat_id = message.chat.id
    title = message.text
    user_data = {
        'title': title,
        'user_id': message.from_user.id  # сохраняем ID пользователя для вставки в БД
    }

    # Просим ввести описание задачи или нажать /skip для пропуска
    msg = bot.send_message(
        chat_id,
        "ℹ️ Введите описание задачи (или нажмите /skip, чтобы пропустить):"
    )
    # Переходим к обработчику описания и передаём накопленные user_data
    bot.register_next_step_handler(msg, process_task_description, user_data)


def process_task_description(message, user_data):
    # Если пользователь не ввёл /skip, сохраняем описание
    if message.text != '/skip':
        user_data['description'] = message.text

    # Предлагаем выбрать приоритет задачи с помощью кнопок
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton('🔴 Высокий'),
        types.KeyboardButton('🟡 Средний'),
        types.KeyboardButton('🟢 Низкий')
    )

    msg = bot.send_message(
        message.chat.id,
        "🚀 Выберите приоритет задачи:",
        reply_markup=markup
    )
    # Регистрируем следующий шаг — выбор приоритета
    bot.register_next_step_handler(msg, process_task_priority, user_data)


def process_task_priority(message, user_data):
    # Преобразуем русский текст кнопки в значение для БД
    priority_map = {
        '🔴 Высокий': 'high',
        '🟡 Средний': 'medium',
        '🟢 Низкий': 'low'
    }
    user_data['priority'] = priority_map.get(message.text, 'medium')  # по умолчанию medium

    # Убираем клавиатуру после выбора приоритета
    markup = types.ReplyKeyboardRemove()
    msg = bot.send_message(
        message.chat.id,
        "📂 Введите категорию задачи (например: Работа, Учеба, Дом) или /skip:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_task_category, user_data)


def process_task_category(message, user_data):
    # Если не пропущено, сохраняем категорию
    if message.text != '/skip':
        user_data['category'] = message.text

    # Попросим ввести теги через запятую или /skip
    msg = bot.send_message(
        message.chat.id,
        "🏷 Введите теги через запятую (например: важное, проект1) или /skip:"
    )
    bot.register_next_step_handler(msg, process_task_tags, user_data)


def process_task_tags(message, user_data):
    # Если пользователь ввёл не /skip, разбиваем строку на список тегов
    if message.text != '/skip':
        tags = [
            tag.strip()
            for tag in message.text.split(',')
            if tag.strip()
        ]
        user_data['tags'] = tags

    # Попросим ввести дедлайн или /skip
    msg = bot.send_message(
        message.chat.id,
        "⏰ Введите дедлайн задачи (например: 'через 2 дня', 'завтра 18:00', '31.12.2023 23:59') или /skip:"
    )
    bot.register_next_step_handler(msg, process_task_deadline, user_data)


def process_task_deadline(message, user_data):
    # Если пользователь не пропустил ввод, пытаемся распарсить дедлайн
    if message.text != '/skip':
        try:
            deadline = parse_deadline(message.text)
            user_data['deadline'] = deadline
        except ValueError as e:
            # При ошибке формата — сообщаем и повторяем запрос
            bot.send_message(
                message.chat.id,
                f"❌ Ошибка: {e}\nПопробуйте ещё раз."
            )
            msg = bot.send_message(
                message.chat.id,
                "⏰ Введите дедлайн задачи (например: 'через 2 дня', 'завтра 18:00', '31.12.2023 23:59') или /skip:"
            )
            bot.register_next_step_handler(msg, process_task_deadline, user_data)
            return

    # Подключаемся к базе и сохраняем задачу
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # 1) Регистрируем пользователя, если его ещё нет в таблице users
        cur.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (message.from_user.id, message.from_user.username)
        )

        # 2) Вставляем новую задачу в таблицу tasks
        cur.execute(
            """
            INSERT INTO tasks
                (user_id, title, description, priority, category, tags, deadline, status)
            VALUES
                (%s, %s, %s, %s, %s, %s, %s, 'active')
            RETURNING task_id
            """,
            (
                user_data['user_id'],
                user_data['title'],
                user_data.get('description'),
                user_data.get('priority', 'medium'),
                user_data.get('category'),
                user_data.get('tags'),
                user_data.get('deadline')
            )
        )
        task_id = cur.fetchone()[0]

        # 3) Извлекаем сохранённую запись, чтобы отформатировать её для пользователя
        cur.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
        record = cur.fetchone()
        columns = [desc[0] for desc in cur.description]
        task = dict(zip(columns, record))
        conn.commit()

        # 4) Отправляем подтверждение и показываем главное меню
        formatted = format_task(task)
        markup = create_task_actions_markup(task_id)
        bot.send_message(
            message.chat.id,
            f"✅ Задача создана!\n\n{formatted}",
            reply_markup=markup,
            parse_mode='Markdown'
        )
        show_main_menu(message.chat.id)

    except Exception as e:
        conn.rollback()
        bot.send_message(
            message.chat.id,
            f"❌ Ошибка при создании задачи: {e}"
        )
        show_main_menu(message.chat.id)
    finally:
        cur.close()
        conn.close()



@bot.message_handler(commands=['mytasks'])
def show_tasks(message):
    # Обработчик команды /mytasks: показывает меню фильтров задач
    # Гарантируем, что пользователь зарегистрирован в БД, даже если он не нажимал /start ранее
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO users (user_id, username)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (message.from_user.id, message.from_user.username)
        )
        conn.commit()
    except Exception as e:
        # При ошибке регистрации откатываем транзакцию и логируем
        conn.rollback()
        print(f"Error registering user from /mytasks: {e}")
    finally:
        cur.close()
        conn.close()

    # Формируем клавиатуру с вариантами фильтрации задач
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(
        '🔴 Высокий приоритет',   # Only high-priority active tasks
        '🟡 Средний приоритет',   # Only medium-priority active tasks
        '🟢 Низкий приоритет',    # Only low-priority active tasks
        '📅 Ближайшие дедлайны',    # Active tasks with upcoming deadlines
        '❗️ Просроченные',         # Active tasks past deadline
        '✅ Завершенные',          # Completed tasks
        '📂 Категории',            # Tasks by category (will ask category next)
        '🏷 Теги',                 # Tasks by tag (will ask tag next)
        '📋 Все задачи'            # All active tasks
    )
    msg = bot.send_message(
        message.chat.id,
        "🔍 Выберите фильтр для отображения задач:",
        reply_markup=markup
    )
    # Переходим к выбору фильтра
    bot.register_next_step_handler(msg, process_task_filter)


def process_task_filter(message):
    # Обрабатываем выбранный фильтр и выводим соответствующие задачи
    filter_type = message.text
    user_id = message.from_user.id

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Если пользователь выбрал «Категории», запрашиваем список и следующий ввод категории
        if filter_type == '📂 Категории':
            cur.execute(
                "SELECT DISTINCT category FROM tasks WHERE user_id=%s AND category IS NOT NULL",
                (user_id,)
            )
            cats = [row[0] for row in cur.fetchall()]
            bot.send_message(
                message.chat.id,
                "Введите категорию из списка:\n" + "\n".join(cats)
            )
            bot.register_next_step_handler(message, show_tasks_by_category)
            return

        # Если выбрал «Теги», аналогично запрашиваем список и ждем ввода
        if filter_type == '🏷 Теги':
            cur.execute(
                "SELECT unnest(tags) FROM tasks WHERE user_id=%s",
                (user_id,)
            )
            tags = sorted({row[0] for row in cur.fetchall() if row[0]})
            bot.send_message(
                message.chat.id,
                "Введите тег из списка:\n" + "\n".join(tags)
            )
            bot.register_next_step_handler(message, show_tasks_by_tag)
            return

        # Для остальных фильтров формируем общий SQL-запрос
        query = "SELECT * FROM tasks WHERE user_id = %s"
        params = [user_id]

        # Добавляем условия в зависимости от фильтра
        if filter_type == '🔴 Высокий приоритет':
            query += " AND priority = 'high' AND status = 'active'"
        elif filter_type == '🟡 Средний приоритет':
            query += " AND priority = 'medium' AND status = 'active'"
        elif filter_type == '🟢 Низкий приоритет':
            query += " AND priority = 'low' AND status = 'active'"
        elif filter_type == '📅 Ближайшие дедлайны':
            query += " AND deadline > NOW() AND status = 'active'"
        elif filter_type == '❗️ Просроченные':
            query += " AND deadline < NOW() AND status = 'active'"
        elif filter_type == '✅ Завершенные':
            query += " AND status = 'completed'"
        else:
            # '📋 Все задачи'
            query += " AND status = 'active'"

        # Сортируем: сначала по приоритету (high → medium → low), затем по дедлайну (ранние вверху)
        query += """
            ORDER BY
              CASE priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
              END,
              deadline ASC
        """

        cur.execute(query, params)
        rows = cur.fetchall()

        # Если нет задач — сообщаем об этом, иначе выводим каждую
        if not rows:
            bot.send_message(message.chat.id, "📭 Нет задач по выбранному фильтру.")
        else:
            for r in rows:
                task = dict(zip([d[0] for d in cur.description], r))
                bot.send_message(
                    message.chat.id,
                    format_task(task),
                    reply_markup=create_task_actions_markup(task['task_id']),
                    parse_mode='Markdown'
                )

        # После показа возвращаем пользователя в главное меню
        show_main_menu(message.chat.id)

    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка при загрузке задач: {e}")
        show_main_menu(message.chat.id)
    finally:
        cur.close()
        conn.close()


def show_tasks_by_category(message):
    # Обработчик, когда пользователь ввел конкретную категорию
    cat = message.text
    user_id = message.from_user.id

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Выбираем задачи для данной категории
        cur.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = %s AND category = %s
            ORDER BY
              CASE priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
              END,
              deadline ASC
            """,
            (user_id, cat)
        )
        rows = cur.fetchall()

        # Выводим задачи или сообщение об их отсутствии
        if not rows:
            bot.send_message(message.chat.id, "📭 Нет задач в этой категории.")
        else:
            for r in rows:
                task = dict(zip([d[0] for d in cur.description], r))
                bot.send_message(
                    message.chat.id,
                    format_task(task),
                    reply_markup=create_task_actions_markup(task['task_id']),
                    parse_mode='Markdown'
                )
    finally:
        cur.close()
        conn.close()

    show_main_menu(message.chat.id)


def show_tasks_by_tag(message):
    # Обработчик, когда пользователь ввел конкретный тег
    tag = message.text.strip('#')  # убираем возможный символ '#'
    user_id = message.from_user.id

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Выбираем задачи, где тег входит в массив tags
        cur.execute(
            """
            SELECT * FROM tasks
            WHERE user_id = %s AND %s = ANY(tags)
            ORDER BY
              CASE priority
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                WHEN 'low' THEN 3
              END,
              deadline ASC
            """,
            (user_id, tag)
        )
        rows = cur.fetchall()

        # Выводим задачи или уведомление об отсутствии
        if not rows:
            bot.send_message(message.chat.id, "📭 Нет задач с таким тегом.")
        else:
            for r in rows:
                task = dict(zip([d[0] for d in cur.description], r))
                bot.send_message(
                    message.chat.id,
                    format_task(task),
                    reply_markup=create_task_actions_markup(task['task_id']),
                    parse_mode='Markdown'
                )
    finally:
        cur.close()
        conn.close()

    show_main_menu(message.chat.id)

@bot.callback_query_handler(
    # Ловим клики по inline-кнопкам с данными вида action_taskId
    func=lambda call: bool(re.match(r'^(complete|delete|reschedule|edit|remind)_\d+$', call.data))
)
def handle_task_action(call):
    # Разбираем действие (complete/delete/…) и ID задачи из callback_data
    action, task_id_str = call.data.split('_', 1)
    task_id = int(task_id_str)
    # Подтверждаем получение клика, чтобы у пользователя исчез "часики"
    bot.answer_callback_query(call.id)

    if action == 'complete':
        return complete_task(call, task_id)

    if action == 'delete':
        return delete_task(call, task_id)

    if action == 'reschedule':
        # Запрашиваем текущий дедлайн из БД
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT deadline FROM tasks WHERE task_id = %s", (task_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        # Если дедлайн не задан или задача не найдена — сообщаем об ошибке
        if not row or not row[0]:
            bot.send_message(call.message.chat.id, "❌ Нельзя перенести: дедлайн не задан или задача не найдена.")
            return show_main_menu(call.message.chat.id)

        # Переводим дедлайн в московское время для наглядности
        moscow = pytz.timezone('Europe/Moscow')
        dl_local = row[0].astimezone(moscow)
        formatted_dl = dl_local.strftime('%d.%m.%Y %H:%M')

        # Просим пользователя ввести новый дедлайн
        msg = bot.send_message(
            call.message.chat.id,
            (
                f"🔄 *Перенос задачи {task_id}*\n"
                f"Текущий дедлайн: `{formatted_dl}`\n\n"
                "Введите новый дедлайн (например `завтра 18:00`, `31.12.2025 14:30`):"
            ),
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_reschedule_deadline, {'task_id': task_id})
        return

    if action == 'edit':
        # Загружаем все поля задачи, чтобы предложить поэтапное редактирование
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            SELECT title, description, priority, category, tags, deadline
            FROM tasks
            WHERE task_id = %s
            """, (task_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            bot.send_message(call.message.chat.id, "❌ Задача не найдена.")
            return show_main_menu(call.message.chat.id)

        # Распаковываем текущие значения
        title, description, priority, category, tags, deadline = row

        # Шаг 1: редактируем заголовок (или /skip для сохранения старого)
        msg = bot.send_message(
            call.message.chat.id,
            (
                f"✏️ *Редактирование задачи {task_id}*\n\n"
                "1️⃣ Текущий заголовок:\n"
                f"`{title or '—'}`\n\n"
                "Введите новый заголовок или /skip, чтобы оставить старый:"
            ),
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_edit_title, {
            'task_id': task_id,
            'old': {
                'title': title,
                'description': description,
                'priority': priority,
                'category': category,
                'tags': tags,
                'deadline': deadline
            },
            'new': {}
        })
        return


def process_reschedule_deadline(message, user_data):
    task_id = user_data['task_id']
    chat_id = message.chat.id

    # Попытка распарсить новый дедлайн
    try:
        new_deadline = parse_deadline(message.text)
    except ValueError as e:
        # При ошибке формата просим ввести ещё раз
        msg = bot.send_message(
            chat_id,
            f"❌ Ошибка: {e}\nПопробуйте ещё раз в формате `завтра 18:00` или `31.12.2025 14:30`:"
        )
        bot.register_next_step_handler(msg, process_reschedule_deadline, user_data)
        return

    # Обновляем дедлайн в БД
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            UPDATE tasks
               SET deadline = %s,
                   updated_at = NOW()
             WHERE task_id = %s
             RETURNING *
            """,
            (new_deadline, task_id)
        )
        row = cur.fetchone()
        if not row:
            bot.send_message(chat_id, "❌ Задача не найдена.")
        else:
            conn.commit()
            task = dict(zip([d[0] for d in cur.description], row))
            bot.send_message(
                chat_id,
                f"🔄 *Дедлайн обновлён!*\n\n{format_task(task)}",
                reply_markup=create_task_actions_markup(task_id),
                parse_mode='Markdown'
            )
    except Exception as e:
        conn.rollback()
        bot.send_message(chat_id, f"❌ Не удалось обновить дедлайн: {e}")
    finally:
        cur.close()
        conn.close()
    show_main_menu(chat_id)


def process_edit_title(message, data):
    # Если введено /skip или пусто — оставляем старый заголовок, иначе сохраняем новый
    text = message.text.strip()
    data['new']['title'] = data['old']['title'] if text == '/skip' or not text else text

    # Шаг 2: редактируем описание
    old_desc = data['old']['description'] or ''
    msg = bot.send_message(
        message.chat.id,
        (
            "2️⃣ Текущее описание:\n"
            f"`{old_desc or '—'}`\n\n"
            "Введите новое описание или /skip:"
        ),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_edit_description, data)


def process_edit_description(message, data):
    # Аналогично для описания: /skip — сохраняем старое
    text = message.text.strip()
    data['new']['description'] = data['old']['description'] if text == '/skip' else text

    # Шаг 3: приоритет — показываем кнопки
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add('🔴 Высокий', '🟡 Средний', '🟢 Низкий')
    old_pr = data['old']['priority']
    msg = bot.send_message(
        message.chat.id,
        f"3️⃣ Текущий приоритет: {get_priority_emoji(old_pr)}\nВыберите новый или /skip:",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_edit_priority, data)


def process_edit_priority(message, data):
    # Выбор нового приоритета или сохранение старого
    pm = {'🔴 Высокий':'high', '🟡 Средний':'medium', '🟢 Низкий':'low'}
    text = message.text.strip()
    data['new']['priority'] = data['old']['priority'] if text == '/skip' else pm.get(text, data['old']['priority'])

    # Шаг 4: категория
    old_cat = data['old']['category'] or ''
    msg = bot.send_message(
        message.chat.id,
        f"4️⃣ Текущая категория: `{old_cat or '—'}`\nВведите новую или /skip:",
        reply_markup=types.ReplyKeyboardRemove(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_edit_category, data)


def process_edit_category(message, data):
    # Обработка нового текста категории
    text = message.text.strip()
    data['new']['category'] = data['old']['category'] if text == '/skip' else text

    # Шаг 5: теги
    old_tags = ', '.join(data['old']['tags'] or []) or ''
    msg = bot.send_message(
        message.chat.id,
        (
            "5️⃣ Текущие теги:\n"
            f"`{old_tags or '—'}`\n\n"
            "Введите новые через запятую или /skip:"
        ),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_edit_tags, data)


def process_edit_tags(message, data):
    # Разбор строки тегов или сохранение старых
    text = message.text.strip()
    data['new']['tags'] = data['old']['tags'] if text == '/skip' else [t.strip() for t in text.split(',') if t.strip()]

    # Шаг 6: дедлайн — показываем текущий и просим новый
    old_dl = data['old']['deadline']
    if old_dl:
        moscow = pytz.timezone('Europe/Moscow')
        old_str = old_dl.astimezone(moscow).strftime('%d.%m.%Y %H:%M')
    else:
        old_str = ''
    msg = bot.send_message(
        message.chat.id,
        (
            "6️⃣ Текущий дедлайн:\n"
            f"`{old_str or '—'}`\n\n"
            "Введите новый дедлайн или /skip:"
        ),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_edit_deadline, data)


def process_edit_deadline(message, data):
    task_id = data['task_id']
    text = message.text.strip()
    # Если /skip — оставляем старый, иначе пытаемся распарсить
    if text == '/skip':
        new_dl = data['old']['deadline']
    else:
        try:
            new_dl = parse_deadline(text)
        except ValueError as e:
            msg = bot.send_message(
                message.chat.id,
                f"❌ Ошибка: {e}\nПопробуйте ещё раз или /skip:"
            )
            return bot.register_next_step_handler(msg, process_edit_deadline, data)
    data['new']['deadline'] = new_dl

    # Шаг 7: обновляем запись в БД сразу всеми полями
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE tasks
           SET title       = %s,
               description = %s,
               priority    = %s,
               category    = %s,
               tags        = %s,
               deadline    = %s,
               updated_at  = NOW()
         WHERE task_id    = %s
         RETURNING *
        """,
        (
            data['new']['title'],
            data['new']['description'],
            data['new']['priority'],
            data['new']['category'],
            data['new']['tags'],
            data['new']['deadline'],
            task_id
        )
    )
    row = cur.fetchone()
    conn.commit()
    cur.close(); conn.close()

    if not row:
        bot.send_message(message.chat.id, "❌ Ошибка при обновлении задачи.")
    else:
        task = dict(zip([d[0] for d in cur.description], row))
        bot.send_message(
            message.chat.id,
            "✅ Задача обновлена!\n\n" + format_task(task),
            reply_markup=create_task_actions_markup(task_id),
            parse_mode='Markdown'
        )

    show_main_menu(message.chat.id)

def complete_task(call, task_id):
    # Устанавливаем соединение с БД
    conn = get_db_connection()
    # Пример проверки соединения (можно удалить в продакшне)
    if conn:
        print("connected")
    # Создаём курсор для выполнения SQL-команд
    cur = conn.cursor()

    try:
        # Обновляем статус задачи на 'completed' и время обновления
        cur.execute(
            "UPDATE tasks "
            "SET status = 'completed', updated_at = NOW() "
            "WHERE task_id = %s "
            "RETURNING *",
            (task_id,)
        )
        # Получаем обновлённую запись задачи
        updated_task = cur.fetchone()

        if updated_task:
            # Если задача найдена — сохраняем изменения в БД
            conn.commit()
            # Формируем словарь из кортежа и описаний колонок
            task_dict = dict(zip([desc[0] for desc in cur.description], updated_task))

            # Редактируем текст уже отправленного сообщения: показываем, что задача завершена
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"✅ Задача завершена!\n\n{format_task(task_dict)}",
                parse_mode='Markdown'
            )
            # Убираем inline-кнопки — больше не нужно взаимодействовать с задачей
            bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=None
            )
            # Возвращаем пользователя в главное меню
            show_main_menu(call.message.chat.id)
        else:
            # Если запись не найдена — уведомляем пользователя
            bot.answer_callback_query(call.id, "❌ Задача не найдена")

    except Exception as e:
        # При ошибке откатываем транзакцию и показываем сообщение об ошибке
        conn.rollback()
        bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
    finally:
        # Всегда закрываем курсор и соединение
        cur.close()
        conn.close()


def delete_task(call, task_id):
    # Подключаемся к БД
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Удаляем задачу по её ID и возвращаем её заголовок
        cur.execute(
            "DELETE FROM tasks WHERE task_id = %s RETURNING title",
            (task_id,)
        )
        deleted_title = cur.fetchone()

        if deleted_title:
            # Фактически удалили — фиксируем изменения
            conn.commit()
            # Редактируем сообщение, чтобы показать, что задача удалена
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"🗑 Задача '{deleted_title[0]}' удалена",
                reply_markup=None  # удаляем кнопки после удаления
            )
        else:
            # Если ничего не вернулось — задача не найдена
            bot.answer_callback_query(call.id, "❌ Задача не найдена")

    except Exception as e:
        # При ошибке откатываем и уведомляем
        conn.rollback()
        bot.answer_callback_query(call.id, f"❌ Ошибка при удалении: {e}")
    finally:
        # Закрываем ресурсы
        cur.close()
        conn.close()


if __name__ == '__main__':
    # При прямом запуске скрипта сначала инициализируем структуру БД
    print("Initializing database...")
    init_db()
    print("Database initialized.")
    # Затем запускаем бот в режиме бесконечного поллинга
    print("Starting bot...")
    bot.infinity_polling()
