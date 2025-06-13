# handlers/task_handlers.py

import re
from telebot import types

class TaskHandler:
    """
    Обработчики команд и этапов диалога создания и просмотра задач.
    Имена функций:
      - send_welcome
      - new_task
      - process_task_title
      - process_task_description
      - process_task_priority
      - process_task_category
      - process_task_tags
      - process_task_deadline
      - show_tasks
      - process_task_filter
      - show_tasks_by_category
      - show_tasks_by_tag
    """

    def __init__(self, bot, db, parser, formatter, ui):
        """
        :param bot: экземпляр telebot.TeleBot
        :param db: экземпляр Database
        :param parser: экземпляр DeadlineParser
        :param formatter: экземпляр TaskFormatter
        :param ui: экземпляр BotUI
        """
        self.bot = bot
        self.db = db
        self.parser = parser
        self.formatter = formatter
        self.ui = ui

    def send_welcome(self, message):
        """
        Обработчик /start: регистрирует пользователя и приветствует.
        """
        # Регистрируем пользователя, если ещё нет
        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (message.from_user.id, message.from_user.username)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error registering user: {e}")
        finally:
            cur.close()
            conn.close()

        # Показываем главное меню и отправляем приветственное сообщение
        self.ui.show_main_menu(message.chat.id)
        self.bot.send_message(
            message.chat.id,
            "👋 Привет! Я TaskMaster Bot - твой личный помощник для управления задачами.\n\n"
            "Используй команды:\n"
            "/newtask - создать новую задачу\n"
            "/mytasks - просмотреть свои задачи\n\n"
            "Или выбери действие ниже:"
        )

    def new_task(self, message):
        """
        Обработчик /newtask: начинает диалог создания задачи.
        """
        msg = self.bot.send_message(
            message.chat.id,
            "📝 Введите название задачи:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        # Следующий шаг: process_task_title
        self.bot.register_next_step_handler(msg, self.process_task_title)

    def process_task_title(self, message):
        """
        Сохраняет заголовок задачи и спрашивает описание.
        """
        chat_id = message.chat.id
        title = message.text.strip()
        user_data = {
            'title': title,
            'user_id': message.from_user.id
        }
        msg = self.bot.send_message(
            chat_id,
            "ℹ️ Введите описание задачи (или нажмите /skip, чтобы пропустить):"
        )
        self.bot.register_next_step_handler(msg, self.process_task_description, user_data)

    def process_task_description(self, message, user_data):
        """
        Сохраняет описание или пропускает, спрашивает приоритет.
        """
        if message.text != '/skip':
            user_data['description'] = message.text.strip()

        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            types.KeyboardButton('🔴 Высокий'),
            types.KeyboardButton('🟡 Средний'),
            types.KeyboardButton('🟢 Низкий')
        )
        msg = self.bot.send_message(
            message.chat.id,
            "🚀 Выберите приоритет задачи:",
            reply_markup=markup
        )
        self.bot.register_next_step_handler(msg, self.process_task_priority, user_data)

    def process_task_priority(self, message, user_data):
        """
        Сохраняет приоритет и спрашивает категорию.
        """
        priority_map = {
            '🔴 Высокий': 'high',
            '🟡 Средний': 'medium',
            '🟢 Низкий': 'low'
        }
        user_data['priority'] = priority_map.get(message.text, 'medium')
        msg = self.bot.send_message(
            message.chat.id,
            "📂 Введите категорию задачи (например: Работа, Учеба, Дом) или /skip:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        self.bot.register_next_step_handler(msg, self.process_task_category, user_data)

    def process_task_category(self, message, user_data):
        """
        Сохраняет категорию или пропускает, спрашивает теги.
        """
        if message.text != '/skip':
            user_data['category'] = message.text.strip()
        msg = self.bot.send_message(
            message.chat.id,
            "🏷 Введите теги через запятую (например: важное, проект1) или /skip:"
        )
        self.bot.register_next_step_handler(msg, self.process_task_tags, user_data)

    def process_task_tags(self, message, user_data):
        """
        Сохраняет теги или пропускает, спрашивает дедлайн.
        """
        if message.text != '/skip':
            tags = [tag.strip() for tag in message.text.split(',') if tag.strip()]
            user_data['tags'] = tags
        msg = self.bot.send_message(
            message.chat.id,
            "⏰ Введите дедлайн задачи (например: 'сегодня в 9:00', 'через 2 дня', "
            "'завтра 18:00', '31.12.2023 23:59') или /skip:"
        )
        self.bot.register_next_step_handler(msg, self.process_task_deadline, user_data)

    def process_task_deadline(self, message, user_data):
        """
        Сохраняет дедлайн (или пропускает), сохраняет задачу в БД, показывает результат.
        """
        chat_id = message.chat.id
        # Парсим введённый дедлайн
        if message.text != '/skip':
            try:
                deadline = self.parser.parse_deadline(message.text)
                user_data['deadline'] = deadline
            except ValueError as e:
                self.bot.send_message(
                    chat_id,
                    f"❌ Ошибка: {e}\nПопробуйте ещё раз."
                )
                msg = self.bot.send_message(
                    chat_id,
                    "⏰ Введите дедлайн задачи (например: 'сегодня в 9:00', "
                    "'через 2 дня', 'завтра 18:00', '31.12.2023 23:59') или /skip:"
                )
                self.bot.register_next_step_handler(msg, self.process_task_deadline, user_data)
                return

        # Сохраняем задачу в БД
        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            # 1) Регистрируем пользователя, если ещё нет
            cur.execute(
                "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (message.from_user.id, message.from_user.username)
            )
            # 2) Вставляем задачу
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

            # 3) Извлекаем запись для форматирования
            cur.execute("SELECT * FROM tasks WHERE task_id = %s", (task_id,))
            record = cur.fetchone()
            columns = [desc[0] for desc in cur.description]
            task = dict(zip(columns, record))
            conn.commit()

            # 4) Отправляем подтверждение и главное меню
            formatted = self.formatter.format_task(task)
            markup = self.ui.create_task_actions_markup(task_id)
            self.bot.send_message(
                chat_id,
                f"✅ Задача создана!\n\n{formatted}",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            self.ui.show_main_menu(chat_id)

        except Exception as e:
            conn.rollback()
            self.bot.send_message(
                chat_id,
                f"❌ Ошибка при создании задачи: {e}"
            )
            self.ui.show_main_menu(chat_id)
        finally:
            cur.close()
            conn.close()

    def show_tasks(self, message):
        """
        Обработчик /mytasks: регистрирует пользователя в БД и предлагает фильтры.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id

        # Регистрируем пользователя, если ещё нет
        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT INTO users (user_id, username) VALUES (%s, %s) ON CONFLICT (user_id) DO NOTHING",
                (user_id, message.from_user.username)
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            print(f"Error registering user from /mytasks: {e}")
        finally:
            cur.close()
            conn.close()

        # Клавиатура фильтров
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
        markup.add(
            '🔴 Высокий приоритет',
            '🟡 Средний приоритет',
            '🟢 Низкий приоритет',
            '📅 Ближайшие дедлайны',
            '❗️ Просроченные',
            '✅ Завершенные',
            '📂 Категории',
            '🏷 Теги',
            '📋 Все задачи'
        )
        msg = self.bot.send_message(
            chat_id,
            "🔍 Выберите фильтр для отображения задач:",
            reply_markup=markup
        )
        self.bot.register_next_step_handler(msg, self.process_task_filter)

    def process_task_filter(self, message):
        """
        Обрабатывает выбранный фильтр, выводит задачи и возвращает в меню.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id

        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            text = message.text

            # Категории
            if text == '📂 Категории':
                cur.execute(
                    "SELECT DISTINCT category FROM tasks WHERE user_id=%s AND category IS NOT NULL",
                    (user_id,)
                )
                cats = [row[0] for row in cur.fetchall() if row[0]]
                if cats:
                    self.bot.send_message(
                        chat_id,
                        "Введите категорию из списка:\n" + "\n".join(cats)
                    )
                    self.bot.register_next_step_handler(message, self.show_tasks_by_category)
                else:
                    self.bot.send_message(chat_id, "Нет категорий.")
                    self.ui.show_main_menu(chat_id)
                return

            # Теги
            if text == '🏷 Теги':
                cur.execute(
                    "SELECT unnest(tags) FROM tasks WHERE user_id=%s",
                    (user_id,)
                )
                tags = sorted({row[0] for row in cur.fetchall() if row[0]})
                if tags:
                    self.bot.send_message(
                        chat_id,
                        "Введите тег из списка:\n" + "\n".join(tags)
                    )
                    self.bot.register_next_step_handler(message, self.show_tasks_by_tag)
                else:
                    self.bot.send_message(chat_id, "Нет тегов.")
                    self.ui.show_main_menu(chat_id)
                return

            # Прочие фильтры
            query = "SELECT * FROM tasks WHERE user_id = %s"
            params = [user_id]

            if text == '🔴 Высокий приоритет':
                query += " AND priority = 'high' AND status = 'active'"
            elif text == '🟡 Средний приоритет':
                query += " AND priority = 'medium' AND status = 'active'"
            elif text == '🟢 Низкий приоритет':
                query += " AND priority = 'low' AND status = 'active'"
            elif text == '📅 Ближайшие дедлайны':
                query += " AND deadline > NOW() AND status = 'active'"
            elif text == '❗️ Просроченные':
                query += " AND deadline < NOW() AND status = 'active'"
            elif text == '✅ Завершенные':
                query += " AND status = 'completed'"
            else:
                # '📋 Все задачи' или иной текст
                query += " AND status = 'active'"

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

            if not rows:
                self.bot.send_message(chat_id, "📭 Нет задач по выбранному фильтру.")
            else:
                for r in rows:
                    task = dict(zip([d[0] for d in cur.description], r))
                    formatted = self.formatter.format_task(task)
                    markup = self.ui.create_task_actions_markup(task['task_id'])
                    self.bot.send_message(
                        chat_id,
                        formatted,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )

            self.ui.show_main_menu(chat_id)
        except Exception as e:
            self.bot.send_message(chat_id, f"❌ Ошибка при загрузке задач: {e}")
            self.ui.show_main_menu(chat_id)
        finally:
            cur.close()
            conn.close()

    def show_tasks_by_category(self, message):
        """
        Обработчик ввода категории: выводит задачи этой категории.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id
        cat = message.text.strip()

        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT *
                FROM tasks
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

            if not rows:
                self.bot.send_message(chat_id, "📭 Нет задач в этой категории.")
            else:
                for r in rows:
                    task = dict(zip([d[0] for d in cur.description], r))
                    formatted = self.formatter.format_task(task)
                    markup = self.ui.create_task_actions_markup(task['task_id'])
                    self.bot.send_message(
                        chat_id,
                        formatted,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
        except Exception as e:
            self.bot.send_message(chat_id, f"❌ Ошибка: {e}")
        finally:
            cur.close()
            conn.close()

        self.ui.show_main_menu(chat_id)

    def show_tasks_by_tag(self, message):
        """
        Обработчик ввода тега: выводит задачи с этим тегом.
        """
        chat_id = message.chat.id
        user_id = message.from_user.id
        tag = message.text.strip().lstrip('#')

        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT *
                FROM tasks
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

            if not rows:
                self.bot.send_message(chat_id, "📭 Нет задач с таким тегом.")
            else:
                for r in rows:
                    task = dict(zip([d[0] for d in cur.description], r))
                    formatted = self.formatter.format_task(task)
                    markup = self.ui.create_task_actions_markup(task['task_id'])
                    self.bot.send_message(
                        chat_id,
                        formatted,
                        reply_markup=markup,
                        parse_mode='Markdown'
                    )
        except Exception as e:
            self.bot.send_message(chat_id, f"❌ Ошибка: {e}")
        finally:
            cur.close()
            conn.close()

        self.ui.show_main_menu(chat_id)
