# handlers/callback_handlers.py
import pytz
from datetime import datetime
import re
from telebot import types, apihelper

class CallbackHandler:
    """
    Обработчики inline-кнопок: завершение, удаление, перенос и редактирование задач.
    Оригинальные имена методов сохранены:
      - handle_task_action
      - complete_task
      - delete_task
      - process_reschedule_deadline
      - process_edit_title
      - process_edit_description
      - process_edit_priority
      - process_edit_category
      - process_edit_tags
      - process_edit_deadline
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

    def handle_task_action(self, call):
        """
        Ловит клик по inline-кнопкам с данными вида action_taskId.
        Разбирает действие и вызывает соответствующий метод.
        """
        action, task_id_str = call.data.split('_', 1)
        try:
            task_id = int(task_id_str)
        except ValueError:
            # Неверный формат callback_data
            self.bot.answer_callback_query(call.id, "❌ Некорректный идентификатор задачи")
            return

        # Подтверждаем получение клика
        self.bot.answer_callback_query(call.id)

        if action == 'complete':
            return self.complete_task(call, task_id)

        if action == 'delete':
            return self.delete_task(call, task_id)

        if action == 'reschedule':
            # Запрашиваем текущий дедлайн из БД
            conn = self.db.get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("SELECT deadline FROM tasks WHERE task_id = %s", (task_id,))
                row = cur.fetchone()
            except Exception as e:
                cur.close()
                conn.close()
                self.bot.send_message(call.message.chat.id, f"❌ Ошибка при получении задачи: {e}")
                return self.ui.show_main_menu(call.message.chat.id)
            cur.close()
            conn.close()

            # Проверяем наличие дедлайна
            if not row or not row[0]:
                self.bot.send_message(call.message.chat.id, "❌ Нельзя перенести: дедлайн не задан или задача не найдена.")
                return self.ui.show_main_menu(call.message.chat.id)

            # Форматируем текущий дедлайн в локальном часовом поясе для показа
            # Предполагается, что parser.timezone = Московская зона
            dl_utc = row[0]
            try:
                moscow = self.parser.timezone
            except AttributeError:
                # Если parser не хранит timezone, можно использовать formatter или config
                moscow = pytz.timezone('Europe/Moscow')
            dl_local = dl_utc.astimezone(moscow)
            formatted_dl = dl_local.strftime('%d.%m.%Y %H:%M')

            # Просим пользователя ввести новый дедлайн
            msg = self.bot.send_message(
                call.message.chat.id,
                (
                    f"🔄 *Перенос задачи {task_id}*\n"
                    f"Текущий дедлайн: `{formatted_dl}`\n\n"
                    "Введите новый дедлайн (например 'сегодня в 9:00', 'завтра 18:00', '31.12.2025 14:30'):"
                ),
                parse_mode='Markdown'
            )
            self.bot.register_next_step_handler(
                msg, self.process_reschedule_deadline, {'task_id': task_id}
            )
            return

        if action == 'edit':
            # Загружаем поля задачи для редактирования
            conn = self.db.get_db_connection()
            cur = conn.cursor()
            try:
                cur.execute("""
                    SELECT title, description, priority, category, tags, deadline
                    FROM tasks
                    WHERE task_id = %s
                """, (task_id,))
                row = cur.fetchone()
            except Exception as e:
                cur.close()
                conn.close()
                self.bot.send_message(call.message.chat.id, f"❌ Ошибка при получении задачи: {e}")
                return self.ui.show_main_menu(call.message.chat.id)
            cur.close()
            conn.close()

            if not row:
                self.bot.send_message(call.message.chat.id, "❌ Задача не найдена.")
                return self.ui.show_main_menu(call.message.chat.id)

            title, description, priority, category, tags, deadline = row

            # Шаг 1: редактирование заголовка
            msg = self.bot.send_message(
                call.message.chat.id,
                (
                    f"✏️ *Редактирование задачи {task_id}*\n\n"
                    "1️⃣ Текущий заголовок:\n"
                    f"`{title or '—'}`\n\n"
                    "Введите новый заголовок или /skip, чтобы оставить старый:"
                ),
                parse_mode='Markdown'
            )
            data = {
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
            }
            self.bot.register_next_step_handler(msg, self.process_edit_title, data)
            return

        # Для других действий (на всякий случай)
        self.ui.show_main_menu(call.message.chat.id)

    def complete_task(self, call, task_id):
        """
        Завершает задачу: обновляет статус в БД, редактирует исходное сообщение.
        Исправлена обработка ошибок редактирования, чтобы не дублировать сообщение
        при 'message is not modified'.
        """
        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE tasks SET status = 'completed', updated_at = NOW() WHERE task_id = %s RETURNING *",
                (task_id,)
            )
            updated_task = cur.fetchone()
            if not updated_task:
                # Задача не найдена
                # Уведомляем юзера одноразово через answer_callback_query
                self.bot.answer_callback_query(call.id, "❌ Задача не найдена")
                return

            # Если задача найдена, фиксируем изменения
            conn.commit()
            columns = [desc[0] for desc in cur.description]
            task_dict = dict(zip(columns, updated_task))

            formatted = self.formatter.format_task(task_dict)

            # Сначала подтверждаем callback, чтобы убрать "часики"
            try:
                # Можно указать пустое уведомление или небольшой текст
                self.bot.answer_callback_query(call.id)
            except Exception:
                # Если не получилось, просто игнорируем
                pass

            # Пробуем редактировать исходное сообщение
            try:
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"✅ Задача завершена!\n\n{formatted}",
                    parse_mode='Markdown'
                )
                self.bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=None
                )
            except apihelper.ApiException as e:
                err_text = str(e)
                # Если ошибка "message is not modified", просто пропускаем отправку нового текста
                if 'message is not modified' in err_text.lower():
                    # Ничего не делаем: текст уже такой же
                    pass
                else:
                    # В иных случаях (например, сообщение слишком старое или юзер удалил бота и т.п.)
                    # отправляем новое сообщение вместо редактирования
                    self.bot.send_message(
                        call.message.chat.id,
                        f"✅ Задача завершена!\n\n{formatted}",
                        parse_mode='Markdown'
                    )
            except Exception:
                # Любое другое исключение при редактировании — отправляем новое сообщение
                self.bot.send_message(
                    call.message.chat.id,
                    f"✅ Задача завершена!\n\n{formatted}",
                    parse_mode='Markdown'
                )


        except Exception as e:
            # Ошибка при работе с БД
            conn.rollback()
            # Если callback ещё не был подтверждён — подтвердим с текстом об ошибке
            try:
                self.bot.answer_callback_query(call.id, f"❌ Ошибка: {e}")
            except Exception:
                pass
        finally:
            cur.close()
            conn.close()
    def delete_task(self, call, task_id):
        """
        Удаляет задачу из БД и редактирует сообщение бота.
        """
        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM tasks WHERE task_id = %s RETURNING title", (task_id,))
            deleted = cur.fetchone()
            if deleted:
                conn.commit()
                title = deleted[0]
                try:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text=f"🗑 Задача '{title}' удалена",
                        reply_markup=None
                    )
                except Exception:
                    # Если редактировать не удалось, просто отправляем новое сообщение
                    self.bot.send_message(call.message.chat.id, f"🗑 Задача '{title}' удалена")
            else:
                self.bot.answer_callback_query(call.id, "❌ Задача не найдена")
        except Exception as e:
            conn.rollback()
            self.bot.answer_callback_query(call.id, f"❌ Ошибка при удалении: {e}")
        finally:
            cur.close()
            conn.close()

    def process_reschedule_deadline(self, message, user_data):
        """
        Обрабатывает ввод нового дедлайна для переноса задачи.
        user_data: {'task_id': int}
        """
        task_id = user_data.get('task_id')
        chat_id = message.chat.id
        text = message.text.strip()
        # Парсим новый дедлайн
        try:
            new_deadline = self.parser.parse_deadline(text)
        except ValueError as e:
            msg = self.bot.send_message(
                chat_id,
                f"❌ Ошибка: {e}\nПопробуйте ещё раз в формате 'сегодня в 9:00', 'завтра 18:00' или '31.12.2025 14:30':"
            )
            self.bot.register_next_step_handler(msg, self.process_reschedule_deadline, user_data)
            return

        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE tasks SET deadline = %s, updated_at = NOW() WHERE task_id = %s RETURNING *",
                (new_deadline, task_id)
            )
            row = cur.fetchone()
            if not row:
                self.bot.send_message(chat_id, "❌ Задача не найдена.")
            else:
                conn.commit()
                columns = [desc[0] for desc in cur.description]
                task = dict(zip(columns, row))
                formatted = self.formatter.format_task(task)
                markup = self.ui.create_task_actions_markup(task_id)
                self.bot.send_message(
                    chat_id,
                    f"🔄 *Дедлайн обновлён!*\n\n{formatted}",
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
        except Exception as e:
            conn.rollback()
            self.bot.send_message(chat_id, f"❌ Не удалось обновить дедлайн: {e}")
        finally:
            cur.close()
            conn.close()
        self.ui.show_main_menu(chat_id)

    def process_edit_title(self, message, data):
        """
        Этап редактирования: новый заголовок.
        data: {'task_id': int, 'old': {...}, 'new': {...}}
        """
        text = message.text.strip()
        data['new']['title'] = data['old']['title'] if text == '/skip' or not text else text

        # Шаг 2: редактирование описания
        old_desc = data['old'].get('description') or ''
        msg = self.bot.send_message(
            message.chat.id,
            (
                "2️⃣ Текущее описание:\n"
                f"`{old_desc or '—'}`\n\n"
                "Введите новое описание или /skip:"
            ),
            parse_mode='Markdown'
        )
        self.bot.register_next_step_handler(msg, self.process_edit_description, data)

    def process_edit_description(self, message, data):
        """
        Этап редактирования: новое описание.
        """
        text = message.text.strip()
        data['new']['description'] = data['old'].get('description') if text == '/skip' else text

        # Шаг 3: приоритет
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add('🔴 Высокий', '🟡 Средний', '🟢 Низкий')
        old_pr = data['old'].get('priority')
        emoji = self.formatter.get_priority_emoji(old_pr)
        msg = self.bot.send_message(
            message.chat.id,
            f"3️⃣ Текущий приоритет: {emoji}\nВыберите новый или /skip:",
            reply_markup=markup
        )
        self.bot.register_next_step_handler(msg, self.process_edit_priority, data)

    def process_edit_priority(self, message, data):
        """
        Этап редактирования: новый приоритет.
        """
        pm = {'🔴 Высокий': 'high', '🟡 Средний': 'medium', '🟢 Низкий': 'low'}
        text = message.text.strip()
        data['new']['priority'] = data['old'].get('priority') if text == '/skip' else pm.get(text, data['old'].get('priority'))

        # Шаг 4: категория
        old_cat = data['old'].get('category') or ''
        msg = self.bot.send_message(
            message.chat.id,
            f"4️⃣ Текущая категория: `{old_cat or '—'}`\nВведите новую или /skip:",
            reply_markup=types.ReplyKeyboardRemove(),
            parse_mode='Markdown'
        )
        self.bot.register_next_step_handler(msg, self.process_edit_category, data)

    def process_edit_category(self, message, data):
        """
        Этап редактирования: новая категория.
        """
        text = message.text.strip()
        data['new']['category'] = data['old'].get('category') if text == '/skip' else text

        # Шаг 5: теги
        old_tags_list = data['old'].get('tags') or []
        old_tags = ', '.join(old_tags_list) if old_tags_list else ''
        msg = self.bot.send_message(
            message.chat.id,
            (
                "5️⃣ Текущие теги:\n"
                f"`{old_tags or '—'}`\n\n"
                "Введите новые через запятую или /skip:"
            ),
            parse_mode='Markdown'
        )
        self.bot.register_next_step_handler(msg, self.process_edit_tags, data)

    def process_edit_tags(self, message, data):
        """
        Этап редактирования: новые теги.
        """
        text = message.text.strip()
        if text == '/skip':
            data['new']['tags'] = data['old'].get('tags')
        else:
            data['new']['tags'] = [t.strip() for t in text.split(',') if t.strip()]

        # Шаг 6: дедлайн
        old_dl = data['old'].get('deadline')
        if old_dl:
            try:
                moscow = self.parser.timezone
            except AttributeError:
                moscow = pytz.timezone('Europe/Moscow')
            old_str = old_dl.astimezone(moscow).strftime('%d.%m.%Y %H:%M')
        else:
            old_str = ''
        msg = self.bot.send_message(
            message.chat.id,
            (
                "6️⃣ Текущий дедлайн:\n"
                f"`{old_str or '—'}`\n\n"
                "Введите новый дедлайн или /skip:"
            ),
            parse_mode='Markdown'
        )
        self.bot.register_next_step_handler(msg, self.process_edit_deadline, data)

    def process_edit_deadline(self, message, data):
        """
        Этап редактирования: новый дедлайн и сохранение всех полей.
        """
        task_id = data.get('task_id')
        text = message.text.strip()
        if text == '/skip':
            new_dl = data['old'].get('deadline')
        else:
            try:
                new_dl = self.parser.parse_deadline(text)
            except ValueError as e:
                msg = self.bot.send_message(
                    message.chat.id,
                    f"❌ Ошибка: {e}\nПопробуйте ещё раз или /skip:"
                )
                self.bot.register_next_step_handler(msg, self.process_edit_deadline, data)
                return
        data['new']['deadline'] = new_dl

        # Обновляем запись в БД
        conn = self.db.get_db_connection()
        cur = conn.cursor()
        try:
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
                 WHERE task_id = %s
                 RETURNING *
                """,
                (
                    data['new'].get('title'),
                    data['new'].get('description'),
                    data['new'].get('priority'),
                    data['new'].get('category'),
                    data['new'].get('tags'),
                    data['new'].get('deadline'),
                    task_id
                )
            )
            row = cur.fetchone()
            if row:
                conn.commit()
                columns = [desc[0] for desc in cur.description]
                task = dict(zip(columns, row))
                formatted = self.formatter.format_task(task)
                markup = self.ui.create_task_actions_markup(task_id)
                self.bot.send_message(
                    message.chat.id,
                    "✅ Задача обновлена!\n\n" + formatted,
                    reply_markup=markup,
                    parse_mode='Markdown'
                )
            else:
                self.bot.send_message(message.chat.id, "❌ Ошибка при обновлении задачи.")
        except Exception as e:
            conn.rollback()
            self.bot.send_message(message.chat.id, f"❌ Ошибка при обновлении: {e}")
        finally:
            cur.close()
            conn.close()

        self.ui.show_main_menu(message.chat.id)
