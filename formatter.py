from datetime import datetime
import pytz
from config import MOSCOW_TZ


class TaskFormatter:
    """
    Формирует текстовые представления задач:
      - format_deadline(deadline) → str
      - get_priority_emoji(priority) → str
      - format_task(task: dict) → str
    """

    def __init__(self, timezone: pytz.BaseTzInfo = MOSCOW_TZ):
        self.timezone = timezone

    def get_priority_emoji(self, priority: str) -> str:

        #Возвращает эмодзи для приоритета
        return {
            'high': '🔴',
            'medium': '🟡',
            'low': '🟢'
        }.get(priority, '')

    def format_deadline(self, deadline: datetime) -> str:
        """
        Преобразует UTC-дату дедлайна в строку вида:
          "⏰ DD.MM.YYYY HH:MM, сегодня через HH:MM"
          или "❗️ DD.MM.YYYY HH:MM, X дн. назад" и т.п.
        Если deadline is None — возвращает пустую строку.
        """
        if not deadline:
            return ""

        # Переводим в локальное время (Московское)
        dl_local = deadline.astimezone(self.timezone)
        now_local = datetime.now(pytz.utc).astimezone(self.timezone)

        date_str = dl_local.strftime('%d.%m.%Y %H:%M')
        delta = dl_local - now_local
        secs = delta.total_seconds()
        date_diff = (dl_local.date() - now_local.date()).days

        # часы и минуты в абсолютном значении
        hours = int(abs(secs) // 3600)
        minutes = int((abs(secs) % 3600) // 60)

        # сегодня
        if date_diff == 0:
            if secs >= 0:
                return f"⏰ {date_str}, сегодня через {hours:02d}:{minutes:02d}"
            else:
                return f"❗️ {date_str}, сегодня {hours:02d}:{minutes:02d} назад"

        # в будущем (завтра или позже)
        if date_diff > 0:
            rel = "завтра" if date_diff == 1 else f"через {date_diff} дн."
            return f"⏰ {date_str}, {rel}"

        # в прошлом (просрочено)
        ago = abs(date_diff)
        rel = "1 дн. назад" if ago == 1 else f"{ago} дн. назад"
        return f"❗️ {date_str}, {rel}"

    def format_task(self, task: dict) -> str:
        """
        Собирает из словаря task текст сообщения:
        эмодзи приоритета, заголовок, описание, дедлайн и теги.
        """
        emoji = self.get_priority_emoji(task.get('priority', ''))
        deadline_text = self.format_deadline(task.get('deadline'))
        tags = task.get('tags') or []
        tags_text = f"\n🏷 {' '.join('#' + t for t in tags)}" if tags else ""

        message = f"{emoji} *{task.get('title', '')}*"
        if task.get('description'):
            message += f"\n📝 {task['description']}"
        if deadline_text:
            message += f"\n{deadline_text}"
        if tags_text:
            message += tags_text

        message += "\n──────────────────"
        return message
