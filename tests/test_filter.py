"""Titles the user has applied to must pass; IC / non-platform titles must not."""
import unittest
from pathlib import Path

import yaml

from yojobs import filter as F
from yojobs.models import Job

PROFILE = yaml.safe_load((Path(__file__).parent.parent / "config.example.yaml").read_text())["profiles"][0]


def passes(title, description="We run everything on Kubernetes.", location="Germany"):
    return F.apply(Job("t", title, "Acme", "https://x", location=location, description=description), PROFILE)


class Titles(unittest.TestCase):
    def test_wanted(self):
        for t in [
            "DevOps Manager",
            "Engineering Manager - Cloud & Security",
            "Hands-on Engineering Manager, Infrastructure",
            "Site Reliability Engineering Manager",
            "Head of Platform Engineering",
            "Director, Site Reliability Engineering",
            "Teamleiter DevOps (m/w/d)",
        ]:
            self.assertTrue(passes(t), t)

    def test_not_wanted(self):
        for t in [
            "Senior DevOps Engineer",              # individual contributor
            "Staff Platform Engineer",             # individual contributor
            "Team Lead, Software Engineering",     # not platform/infra
            "Product Manager, Cloud Platform",     # excluded role
            "Account Executive Cloud & DevOps",    # excluded role
        ]:
            self.assertFalse(passes(t), t)

    def test_requires_kubernetes(self):
        self.assertFalse(passes("DevOps Manager", description="We use Nomad."))

    def test_location(self):
        self.assertTrue(passes("DevOps Manager", location="Europe Only"))
        self.assertFalse(passes("DevOps Manager", location="USA Only"))
        self.assertFalse(passes("DevOps Manager", location="United Kingdom"))


if __name__ == "__main__":
    unittest.main()
