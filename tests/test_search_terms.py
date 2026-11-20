import unittest

from yojobs.__main__ import search_terms


class SearchTerms(unittest.TestCase):
    def test_profile_order_kept(self):
        profiles = [{"all_of": ["Kubernetes|K8s|GKE|EKS|AKS|OpenShift"]}]
        self.assertEqual(search_terms(profiles), ["Kubernetes", "K8s", "GKE", "EKS", "AKS", "OpenShift"])

    def test_any_of_fallback_and_duplicates(self):
        profiles = [{"any_of": ["Kubernetes | GKE", ""]}, {"all_of": ["GKE|Terraform"]}]
        self.assertEqual(search_terms(profiles), ["Kubernetes", "GKE", "Terraform"])


if __name__ == "__main__":
    unittest.main()
