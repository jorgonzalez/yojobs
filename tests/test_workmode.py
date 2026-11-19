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


from yojobs import filter as jobfilter
from yojobs.workmode import month_office_days, office_required

YUBO = ("Trust & Flexibility: Our hybrid model calls for only two office days a month; the rest is up to the "
        "rhythm that suits you. Cool Workplace: enjoy our amazing Parisian office and our many hybrid work options.")


class OfficeRequired(unittest.TestCase):
    def test_office_presence_counts(self):
        for text in [YUBO,
                     "You'll join us 3 days a week in the office.",
                     "We meet in our Paris office twice a week.",
                     "This is a hybrid role based in Amsterdam.",
                     "Hybrid working model: 2 days per week on-site.",
                     "Wir arbeiten in einem hybriden Arbeitsmodell mit 2 Tagen pro Woche im Büro."]:
            self.assertTrue(office_required(text), text)

    def test_optional_or_occasional_does_not(self):
        for text in ["Fully remote within Europe; we meet at quarterly offsites.",
                     "Remote or hybrid, your choice: our Berlin office is open if you like.",
                     "We get together twice a year at our company retreat.",
                     "Co-working budget, and you can visit the office if you want.",
                     "Remote-first team spread across 12 countries.",
                     "Experience with hybrid cloud environments (AWS + on-prem).",
                     ""]:
            self.assertFalse(office_required(text), text)

    def test_month_days(self):
        self.assertEqual(month_office_days("two office days a month"), "2")
        self.assertEqual(month_office_days("1-2 days per month in the office"), "1-2")
        self.assertEqual(month_office_days("20 days of vacation per month"), "")      # no office nearby


PROFILE = {"onsite_cities": ["Berlin"], "remote_regions": ["Germany", "Europe", "EMEA", "Worldwide"]}


class RemoteLabelButHybrid(unittest.TestCase):
    def remote_job(self, description, location="Europe, France"):
        return Job(source="euremotejobs", title="SRE Platform Manager", company="Yubo",
                   url="https://x", location=location, description=description, remote=True)

    def test_hybrid_elsewhere_is_out(self):
        self.assertFalse(jobfilter.place_ok(self.remote_job(YUBO), PROFILE))

    def test_hybrid_in_berlin_is_in(self):
        ad = "Our hybrid model calls for two office days a month in our Berlin office."
        self.assertTrue(jobfilter.place_ok(self.remote_job(ad), PROFILE))
        self.assertEqual(describe(self.remote_job(ad)), "hybrid · 2 office days/month")

    def test_real_remote_unchanged(self):
        self.assertTrue(jobfilter.place_ok(self.remote_job("Fully remote; quarterly offsites."), PROFILE))
