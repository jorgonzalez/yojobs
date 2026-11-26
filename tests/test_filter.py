"""Titles the user has applied to must pass; IC / non-platform titles must not."""
import unittest
from pathlib import Path

import yaml

from yojobs import filter as F
from yojobs.config import load_config
from yojobs.models import Job

PROFILE = load_config(Path(__file__).parent.parent / "config.example")["profiles"][0]


def passes(title, description="We run everything on Kubernetes.", location="Germany", remote=True):
    job = Job("t", title, "Acme", "https://x", location=location, description=description, remote=remote)
    return F.apply(job, PROFILE)


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
            "Head of Engineering, Infrastructure",
            "Director of Engineering - SRE",
        ]:
            self.assertTrue(passes(t), t)

    def test_not_wanted(self):
        for t in [
            "Senior DevOps Engineer",              # individual contributor
            "Staff Platform Engineer",             # individual contributor
            "Team Lead, Software Engineering",     # not platform/infra
            "Product Manager, Cloud Platform",     # excluded role
            "Account Executive Cloud & DevOps",    # excluded role
            "Director of Engineering",             # too broad without an area
            "Head of Engineering",                 # too broad without an area
            "Head of Technology",                  # too broad without an area
            "Project Manager - Infrastructure & Expansion",
            "Infrastructure Program Manager",
            "Procurement Manager, Construction and Infrastructure",
            "Head of Product – Trust Platform Area",
            "Head of Growth // AI Music Video Platform",
        ]:
            self.assertFalse(passes(t), t)

    def test_requires_kubernetes(self):
        self.assertFalse(passes("DevOps Manager", description="We use Nomad."))
        self.assertTrue(passes("DevOps Manager", description="Our stack: GKE / K8s, Terraform."))

    def test_no_description_source_is_kept_but_flagged(self):
        job = Job("startupmap", "Head of Platform", "Acme", "https://x", location="Berlin, Germany", has_description=False)
        self.assertTrue(F.apply(job, PROFILE))
        self.assertEqual(job.notes, ["Kubernetes not verified"])

    def test_description_source_without_kubernetes_still_dropped(self):
        job = Job("linkedin", "Head of Platform", "Acme", "https://x", location="Germany", description="")
        self.assertFalse(F.apply(job, PROFILE))

    def test_berlin_any_work_mode(self):
        self.assertTrue(passes("DevOps Manager", location="Berlin, Germany", remote=False))
        self.assertTrue(passes("DevOps Manager", location="Berlin, Berlin, Germany", remote=None))
        self.assertTrue(passes("DevOps Manager", location="Berlin, Germany", remote=True))

    def test_onsite_elsewhere_dropped(self):
        for loc in ["Munich, Bavaria, Germany", "Bad Friedrichshall, Baden-Württemberg, Germany",
                    "Barcelona, Catalonia, Spain", "Sofia, Bulgaria", "Cork, County Cork, Ireland"]:
            self.assertFalse(passes("DevOps Manager", location=loc, remote=False), loc)
            self.assertFalse(passes("DevOps Manager", location=loc, remote=None), loc)

    def test_remote_needs_allowed_region(self):
        self.assertTrue(passes("DevOps Manager", location="Germany", remote=True))
        self.assertTrue(passes("DevOps Manager", location="Hamburg, Germany", remote=True))  # remote within Germany
        self.assertTrue(passes("DevOps Manager", location="European Union", remote=True))
        self.assertTrue(passes("DevOps Manager", location="Worldwide", remote=True))
        self.assertTrue(passes("DevOps Manager", location="", remote=True))
        self.assertFalse(passes("DevOps Manager", location="Cork, County Cork, Ireland", remote=True))
        self.assertFalse(passes("DevOps Manager", location="Paris, Île-de-France, France", remote=True))

    def test_hybrid_tag_with_remote_location(self):
        def job(location, work_mode="hybrid", description="We run everything on Kubernetes."):
            return Job("t", "Platform Team Lead", "Acme", "https://x", location=location,
                       description=description, remote=False, work_mode=work_mode)
        self.assertTrue(F.apply(job("Remote Germany"), PROFILE))          # vivenu on Lever
        self.assertFalse(F.apply(job("Remote Germany", work_mode="onsite"), PROFILE))
        self.assertFalse(F.apply(job("Munich, Germany"), PROFILE))        # hybrid elsewhere
        self.assertFalse(F.apply(job("Remote or Hybrid - Munich"), PROFILE))
        self.assertFalse(F.apply(job("Remote - United States"), PROFILE))  # still needs a region
        self.assertFalse(F.apply(job("Remote Germany", description=(
            "We run everything on Kubernetes. You work 3 days a week from our Munich office.")), PROFILE))

    def test_location(self):
        self.assertTrue(passes("DevOps Manager", location="Europe Only"))
        self.assertFalse(passes("DevOps Manager", location="USA Only"))
        self.assertFalse(passes("DevOps Manager", location="United Kingdom"))


if __name__ == "__main__":
    unittest.main()
