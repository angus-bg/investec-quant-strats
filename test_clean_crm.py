import unittest

from clean_crm import enrich_record, find_strongest_match, merge_records
from clean_crm import normalize_company_name, process_user_records


class FakeResponse:
    def __init__(self, output_text):
        self.output_text = output_text


class FakeResponses:
    def __init__(self, output_text):
        self.output_text = output_text

    def create(self, **_kwargs):
        return FakeResponse(self.output_text)


class FakeClient:
    def __init__(self, output_text):
        self.responses = FakeResponses(output_text)


class CleanCrmTests(unittest.TestCase):
    def test_normalize_company_name(self):
        self.assertEqual(normalize_company_name("  Acme,  Inc.! "), "acme inc")

    def test_find_strongest_match(self):
        records = [{"Company": "Acme Inc", "Sector": "", "Short description": ""}]
        match, score = find_strongest_match("ACME INC", records)
        self.assertIs(match, records[0])
        self.assertEqual(score, 1.0)

    def test_threshold_logic_adds_low_score_company(self):
        crm = [{"Company": "Acme Inc", "Sector": "", "Short description": ""}]
        user = [{"Company": "Northwind Rail", "Sector": "Transport", "Short description": ""}]
        summary = process_user_records(crm, user, None, "test-model")
        self.assertEqual(len(crm), 2)
        self.assertEqual(summary["genuinely_new"], 1)

    def test_merge_does_not_replace_existing_values_with_blanks(self):
        existing = {"Company": "Acme Inc", "Sector": "Technology", "Short description": "Original"}
        incoming = {"Company": "Acme Inc", "Sector": "", "Short description": "Updated"}
        merge_records(existing, incoming)
        self.assertEqual(existing["Sector"], "Technology")
        self.assertEqual(existing["Short description"], "Updated")

    def test_enrichment_fills_only_blank_fields(self):
        record = {"Company": "Acme Inc", "Sector": "Technology", "Short description": ""}
        client = FakeClient('{"sector": "Finance", "short_description": "A software company."}')
        enrich_record(record, client, "test-model", [])
        self.assertEqual(record["Sector"], "Technology")
        self.assertEqual(record["Short description"], "A software company.")


if __name__ == "__main__":
    unittest.main()