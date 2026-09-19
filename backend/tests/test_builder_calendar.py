from datetime import date

from builder.calendar import mentions_time, notes


def test_phrases_are_worked_out_from_mid_september():
    text = notes(date(2026, 9, 14))
    assert "last month: 2026-08-01 to 2026-08-31" in text
    assert "last year: 2025-01-01 to 2025-12-31" in text
    assert "start on 2026-09-07, 2026-08-15 and 2026-06-16" in text
    assert "last summer: 2026-06-01 to 2026-08-31; next summer: 2027-06-01 to 2027-08-31" in text
    assert "the next 3 months end on 2026-12-14" in text
    assert text.endswith("2027-03-31")


def test_before_june_next_summer_is_this_year_and_last_summer_was_last_year():
    text = notes(date(2026, 2, 10))
    assert "last summer: 2025-06-01 to 2025-08-31; next summer: 2026-06-01 to 2026-08-31" in text
    assert text.endswith("2026-03-31"), "March is still ahead in February"
    assert "last month: 2026-01-01 to 2026-01-31" in text


def test_last_month_in_january_is_last_december():
    assert "last month: 2025-12-01 to 2025-12-31" in notes(date(2026, 1, 5))


def test_the_next_3_months_from_the_end_of_a_long_month_stay_in_range():
    assert "the next 3 months end on 2026-02-28" in notes(date(2025, 11, 30))


def test_a_request_that_never_says_when_is_noticed():
    assert not mentions_time("Check the water around Mumbai")
    assert not mentions_time("Show me the heat in Cairo")
    for said in ["Monitor water in Dhaka for 2024", "every day until October", "last summer", "the past 90 days", "during May"]:
        assert mentions_time(said), said
