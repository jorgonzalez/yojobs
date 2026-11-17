import unittest

from yojobs.models import Job
from yojobs.workmode import describe, office_days


def job(description="", **kw):
    return Job(source="x", title=kw.pop("title", "Engineering Manager"), company="C", url="u",
               location=kw.pop("location", "Berlin"), description=description, **kw)


class OfficeDays(unittest.TestCase):
    def test_english(self):
        self.assertEqual(office_days("We work 3 days a week in the office."), "3")
        self.assertEqual(office_days("Hybrid: 2-3 days per week in our Berlin office"), "2-3")
        self.assertEqual(office_days("you'll join us in the office two days a week"), "2")
        self.assertEqual(office_days("3 office days per week, the rest remote"), "3")
        self.assertEqual(office_days("in the office twice a week"), "2")

    def test_german(self):
        self.assertEqual(office_days("2 Tage pro Woche im Büro"), "2")
        self.assertEqual(office_days("an drei Tagen pro Woche vor Ort in Berlin"), "3")
        self.assertEqual(office_days("1-2 Bürotage pro Woche"), "1-2")

    def test_not_office_days(self):
        self.assertEqual(office_days("30 days vacation, office in Berlin"), "")
        self.assertEqual(office_days("5 days of onboarding in the office"), "")
        self.assertEqual(office_days("2 days per week from home, rest in the office"), "")
        self.assertEqual(office_days("We have a nice office. 25 Tage Urlaub."), "")


class Describe(unittest.TestCase):
    def test_source_mode_wins(self):
        self.assertEqual(describe(job(work_mode="Hybrid", remote=False)), "hybrid")
        self.assertEqual(describe(job(work_mode="OnSite", remote=False)), "on-site")

    def test_from_text(self):
        self.assertEqual(describe(job("Hybrid role, 2 days per week in the office.")),
                         "hybrid · 2 office days/week")
        self.assertEqual(describe(job("Hybrides Arbeiten möglich")), "hybrid")
        self.assertEqual(describe(job("This is an on-site position in Berlin.")), "on-site")
        self.assertEqual(describe(job("Join us in the office one day a week")), "hybrid · 1 office day/week")

    def test_days_override_generic_label(self):
        self.assertEqual(describe(job("3 days per week in our Berlin office", work_mode="onsite", remote=False)),
                         "hybrid · 3 office days/week")
        self.assertEqual(describe(job("5 days a week in the office", work_mode="hybrid", remote=False)),
                         "on-site · 5 office days/week")

    def test_unknown(self):
        self.assertEqual(describe(job("Great team, Kubernetes, GCP.")), "")


if __name__ == "__main__":
    unittest.main()
