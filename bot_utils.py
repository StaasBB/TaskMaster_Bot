# bot_utils.py

from telebot import types


class BotUI:
    """
    Утилиты для отображения UI в Telegram: главные меню и inline-кнопки для задач.
    """

    def __init__(self, bot):
        """
        :param bot: экземпляр telebot.TeleBot
        """
        self.bot = bot

    def show_main_menu(self, chat_id):
        """
        Отображает главное меню с кнопками /newtask и /mytasks.
        """
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            types.KeyboardButton('/newtask'),
            types.KeyboardButton('/mytasks')
        )
        # Сообщение "Главное меню:" и клавиатура
        self.bot.send_message(chat_id, "Главное меню:", reply_markup=markup)

    def create_task_actions_markup(self, task_id):
        """
        Формирует InlineKeyboardMarkup с кнопками управления задачей:
          - Завершить (complete_{task_id})
          - Удалить (delete_{task_id})
          - Перенести (reschedule_{task_id})
          - Редактировать (edit_{task_id})
        """
        markup = types.InlineKeyboardMarkup()
        # Верхний ряд: Завершить и Удалить
        markup.row(
            types.InlineKeyboardButton(
                "✅ Завершить", callback_data=f"complete_{task_id}"
            ),
            types.InlineKeyboardButton(
                "🗑 Удалить", callback_data=f"delete_{task_id}"
            )
        )
        # Нижний ряд: Перенести и Редактировать
        markup.row(
            types.InlineKeyboardButton(
                "🔄 Перенести", callback_data=f"reschedule_{task_id}"
            ),
            types.InlineKeyboardButton(
                "✏️ Редактировать", callback_data=f"edit_{task_id}"
            ),
        )
        return markup
