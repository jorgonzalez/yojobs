import unittest

from yojobs import filter as jf
from yojobs.language import ad_language, requires
from yojobs.models import Job

DE = ("Wir suchen eine Teamleitung DevOps für unser Team in Berlin. Du bist verantwortlich für den Betrieb "
      "unserer Plattform auf Kubernetes und arbeitest eng mit den Entwicklungsteams zusammen. Was du mitbringst: "
      "mehrjährige Erfahrung mit Kubernetes, Führungserfahrung und Freude an der Arbeit im Team. Wir bieten dir "
      "ein modernes Arbeitsumfeld, flexible Arbeitszeiten und die Möglichkeit, unsere Infrastruktur mitzugestalten.")
EN = ("We are looking for an Engineering Manager for our platform team in Berlin. You will lead a team of "
      "engineers who run our Kubernetes infrastructure and work closely with the product teams. What you bring: "
      "several years of experience with Kubernetes, leadership experience and a passion for building teams. We "
      "offer a modern work environment, flexible hours and the chance to shape our infrastructure.")


class AdLanguage(unittest.TestCase):
    def test_detects(self):
        self.assertEqual(ad_language(DE), "de")
        self.assertEqual(ad_language(EN), "en")

    def test_bilingual_and_short_are_unclear(self):
        self.assertEqual(ad_language(DE + " " + EN), "")
        self.assertEqual(ad_language("Teamleiter DevOps (m/w/d)"), "")


class Requires(unittest.TestCase):
    def test_required(self):
        for text in ["Fluent German and English are required.",
                     "You speak German (C1) and English.",
                     "Excellent written and spoken German",
                     "Sehr gute Deutschkenntnisse in Wort und Schrift (C1)",
                     "Verhandlungssicheres Deutsch und Englisch",
                     "You are German-speaking"]:
            self.assertTrue(requires(text, "German"), text)

    def test_not_required(self):
        for text in ["Fluent German is a plus.",
                     "German skills are nice to have but not required.",
                     "Deutschkenntnisse (C1) sind von Vorteil",
                     "Fluent English required. We are based in Germany.",
                     EN]:
            self.assertFalse(requires(text, "German"), text)


class Profile(unittest.TestCase):
    PROFILE = {"groups": {"role": ["Manager", "Teamleitung"], "area": ["DevOps", "Platform"]},
               "match_in": ["title"], "onsite_cities": ["Berlin"]}

    def job(self, title, description):
        return Job(source="x", title=title, company="C", url="u", location="Berlin", description=description)

    def test_skip_german_ads(self):
        p = dict(self.PROFILE, skip_ad_languages=["de"])
        self.assertFalse(jf.apply(self.job("Teamleitung DevOps", DE), p))
        self.assertTrue(jf.apply(self.job("Engineering Manager Platform", EN), p))
        self.assertTrue(jf.apply(self.job("Teamleitung DevOps", ""), p))   # no description: kept
        self.assertTrue(jf.apply(self.job("Teamleitung DevOps", DE), self.PROFILE))  # option off

    def test_skip_if_requires(self):
        p = dict(self.PROFILE, skip_if_requires=["German"])
        self.assertFalse(jf.apply(self.job("Engineering Manager Platform", EN + " Fluent German required."), p))
        self.assertTrue(jf.apply(self.job("Engineering Manager Platform", EN + " German is a plus."), p))


if __name__ == "__main__":
    unittest.main()
