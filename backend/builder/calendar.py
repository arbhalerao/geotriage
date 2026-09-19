import calendar
import re
from datetime import date, timedelta

# words that say when, or for how long; a request with none of them hasn't said
_TIME_WORDS = re.compile(
    r"\b((19|20)\d{2}|january|february|march|april|may|june|july|august|september|october|november|december"
    r"|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|today|tomorrow|yesterday|now|daily|weekly|monthly|hourly"
    r"|every|until|till|through|since|from|during|last|next|past|ago|summer|winter|spring|autumn|monsoon"
    r"|days?|weeks?|months?|years?|hours?)\b",
    re.IGNORECASE,
)


def mentions_time(text: str) -> bool:
    return bool(_TIME_WORDS.search(text))


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def notes(today: date) -> str:
    year = today.year
    last_month_end = today.replace(day=1) - timedelta(days=1)
    last_summer = year if today >= date(year, 9, 1) else year - 1
    next_summer = year if today < date(year, 6, 1) else year + 1
    next_march = year if today < date(year, 3, 1) else year + 1
    lines = [
        f"- today: {today}",
        f"- last month: {last_month_end.replace(day=1)} to {last_month_end}",
        f"- this year so far: {year}-01-01 to {today}",
        f"- last year: {year - 1}-01-01 to {year - 1}-12-31",
        f"- the past 7, 30 and 90 days start on {today - timedelta(days=7)}, {today - timedelta(days=30)} and {today - timedelta(days=90)}",
        f"- last summer: {last_summer}-06-01 to {last_summer}-08-31; next summer: {next_summer}-06-01 to {next_summer}-08-31",
        f"- the end of the year: {year}-12-31; the next 3 months end on {_add_months(today, 3)}",
        f'- a month without a year, like "until March" or "next March", is the next one after today: {_month_end(next_march, 3)}',
    ]
    return "\n".join(lines)
