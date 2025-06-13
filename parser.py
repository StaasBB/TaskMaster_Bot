import os
import dotenv
import re
from datetime import datetime, timedelta

import pytz

from config import MOSCOW_TZ


class DeadlineParser:
    """
    Преобразует текстовый ввод пользователя в UTC-время дедлайна.
    Поддерживаемые варианты:
      1) 'через N часов M минут'
      2) 'через N минут'
      3) 'через N дней [в HH:MM]'
      4) 'сегодня [в HH:MM]'
      5) 'завтра [в HH:MM]'
      6) 'DD.MM.YYYY[ HH:MM]'
      7) 'D месяц [в HH:MM]'
    """

    def __init__(self, timezone: pytz.BaseTzInfo = MOSCOW_TZ):
        self.timezone = timezone

    def parse_deadline(self, text: str) -> datetime:
        moscow = self.timezone
        now = datetime.now(moscow)
        text = text.lower().strip()

        def local_dt(year, month, day, hour=23, minute=59):
            naive = datetime(year, month, day, hour, minute)
            return moscow.localize(naive).astimezone(pytz.utc)

        # 1) 'через N часов [M минут]'
        match = re.match(
            r'через\s+(\d+)\s*(?:час|часа|часов)'
            r'(?:\s+(\d+)\s*(?:минута|минуты|минут|минуту))?$',
            text
        )
        if match:
            hours = int(match.group(1))
            minutes = int(match.group(2)) if match.group(2) else 0
            return (now + timedelta(hours=hours, minutes=minutes)) \
                .astimezone(pytz.utc)

        # 2) 'через N минут'
        match = re.match(
            r'через\s+(\d+)\s*(?:минута|минуты|минут|минуту)$',
            text
        )
        if match:
            minutes = int(match.group(1))
            return (now + timedelta(minutes=minutes)) \
                .astimezone(pytz.utc)

        # 3) 'через N дней [в HH:MM]'
        time_pt = r'(?:\s*(?:в)?\s*(\d{1,2}):(\d{2}))?'
        match = re.match(
            rf'через\s+(\d+)\s*(?:день|дня|дней){time_pt}$',
            text
        )
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
        match = re.match(
            rf'(\d{{1,2}})\.(\d{{1,2}})\.(\d{{2,4}}){time_pt}$',
            text
        )
        if match:
            d, m, y = map(int, match.groups()[:3])
            y += 2000 if y < 100 else 0
            hour = int(match.group(4)) if match.group(4) else 23
            minute = int(match.group(5)) if match.group(5) else 59
            return local_dt(y, m, d, hour, minute)

        # 7) 'D месяц [в HH:MM]'
        match = re.match(rf'(\d{{1,2}})\s+([а-яё]+){time_pt}$', text)
        if match:
            day = int(match.group(1))
            month_str = match.group(2)
            month_names = [
                "января", "февраля", "марта", "апреля", "мая", "июня",
                "июля", "августа", "сентября", "октября", "ноября", "декабря"
            ]
            try:
                month = month_names.index(month_str) + 1
            except ValueError:
                raise ValueError("Неверное название месяца")
            hour = int(match.group(3)) if match.group(3) else 23
            minute = int(match.group(4)) if match.group(4) else 59
            return local_dt(now.year, month, day, hour, minute)

        # Если ни один шаблон не подошёл
        raise ValueError("Неверный формат даты.")
