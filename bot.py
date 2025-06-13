# bot.py

import re
from telebot import TeleBot
from config import API_TOKEN
from db import Database
from parser import DeadlineParser
from formatter import TaskFormatter
from bot_utils import BotUI
from handlers.task_handlers import TaskHandler
from handlers.callback_handlers import CallbackHandler


class BotApp:
    """
    Основной класс-приложение для TaskMaster Bot.
    Инкапсулирует создание TeleBot, регистрацию обработчиков и запуск бота.
    """

    def __init__(self):
        # Создаём экземпляр TeleBot
        if not API_TOKEN:
            raise RuntimeError("API_TOKEN не задан в окружении")
        self.bot = TeleBot(API_TOKEN)

        # Инициализируем зависимости
        self.db = Database()
        self.parser = DeadlineParser()
        self.formatter = TaskFormatter()
        self.ui = BotUI(self.bot)

        # Создаём обработчики
        self.task_handler = TaskHandler(self.bot, self.db, self.parser, self.formatter, self.ui)
        self.callback_handler = CallbackHandler(self.bot, self.db, self.parser, self.formatter, self.ui)

        # Регистрируем message- и callback-обработчики
        self._register_handlers()

    def _register_handlers(self):
        """
        Регистрация команд и callback-запросов.
        """
        # /start
        self.bot.register_message_handler(self.task_handler.send_welcome, commands=['start'])
        # /newtask
        self.bot.register_message_handler(self.task_handler.new_task, commands=['newtask'])
        # /mytasks
        self.bot.register_message_handler(self.task_handler.show_tasks, commands=['mytasks'])

        # Callback-запросы для inline-кнопок задач:
        @self.bot.callback_query_handler(
            func=lambda c: bool(re.match(r'^(complete|delete|reschedule|edit)_\d+$', c.data))
        )
        def on_callback(c):
            # Перенаправляем в обработчик
            self.callback_handler.handle_task_action(c)

        # Можно добавить другие хендлеры здесь по необходимости,
        # например для текстовых сообщений, если нужна глобальная обработка.

    def run(self):
        """
        Инициализация БД (если нужно) и бесконечный polling.
        """
        # Инициализируем таблицы базы данных
        try:
            self.db.init_db()
        except Exception as e:
            print(f"Ошибка при инициализации БД: {e}")
            # можно решить, завершать ли работу или продолжать?
            # Например:
            # raise

        print("Database initialized. Starting bot polling...")
        # Запускаем бот
        self.bot.infinity_polling()


# Если нужно запускать из этого модуля напрямую:
if __name__ == '__main__':
    app = BotApp()
    app.run()