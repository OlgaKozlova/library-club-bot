from datetime import datetime


def get_poll_month_name() -> str:
    """
    Определяет название месяца для опроса.
    С 1 по 15 число - текущий месяц, с 16 по конец месяца - следующий месяц.
    Возвращает название месяца в родительном падеже на русском языке.
    """
    month_names = {
        1: "января", 2: "февраля", 3: "марта", 4: "апреля",
        5: "мая", 6: "июня", 7: "июля", 8: "августа",
        9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
    }
    
    now = datetime.now()
    current_day = now.day
    current_month = now.month
    
    # Если день >= 16, берем следующий месяц
    if current_day >= 16:
        next_month = current_month + 1
        # Если следующий месяц больше 12, переходим на январь (месяц 1)
        if next_month > 12:
            next_month = 1
        month_name = month_names.get(next_month, "месяца")
    else:
        # Если день < 16, берем текущий месяц
        month_name = month_names.get(current_month, "месяца")
    
    return month_name


def get_poll_month_year_key() -> str:
    """
    Ключ для истории по месяцу/году.
    С 1 по 15 число - текущий месяц, с 16 по конец месяца - следующий месяц.
    Формат: "12_2026" (без ведущего нуля у месяца).
    """
    now = datetime.now()
    day = now.day
    month = now.month
    year = now.year

    if day >= 16:
        month += 1
        if month > 12:
            month = 1
            year += 1

    return f"{month}_{year}"
