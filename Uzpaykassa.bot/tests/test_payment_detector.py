import unittest
from types import SimpleNamespace

from handlers.payment_detector import PaymentDetector


class FakeDB:
    def __init__(self, candidates=None):
        self.candidates = list(candidates or [])
        self.status_updates = []

    def get_pending_payments_by_card_and_amount(self, card_last4, amount, tolerance):
        return self.candidates

    def update_payment_status(self, payment_id, status):
        self.status_updates.append((payment_id, status))
        return True


class PaymentDetectorTests(unittest.TestCase):
    def test_parses_basic_payment_message(self):
        detector = PaymentDetector(FakeDB())
        parsed = detector.parse_payment_message("PAYMENT|50000|8012")
        self.assertEqual(parsed["amount"], 50000.0)
        self.assertEqual(parsed["card_last4"], "8012")

    def test_parses_thousands_separator(self):
        detector = PaymentDetector(FakeDB())
        parsed = detector.parse_payment_message("PAYMENT|50,000|8012")
        self.assertEqual(parsed["amount"], 50000.0)

    def test_rejects_unrelated_numbers(self):
        detector = PaymentDetector(FakeDB())
        self.assertIsNone(detector.parse_payment_message("Order 50000; code 8012"))

    def test_unique_candidate_matches(self):
        payment = SimpleNamespace(payment_id="p1")
        detector = PaymentDetector(FakeDB([payment]))
        self.assertIs(detector.find_matching_payment({"amount": 50000, "card_last4": "8012"}), payment)

    def test_ambiguous_candidates_do_not_auto_match(self):
        detector = PaymentDetector(FakeDB([SimpleNamespace(payment_id="p1"), SimpleNamespace(payment_id="p2")]))
        self.assertIsNone(detector.find_matching_payment({"amount": 50000, "card_last4": "8012"}))

    def test_process_payment_marks_paid_not_completed(self):
        db = FakeDB()
        detector = PaymentDetector(db)
        payment = SimpleNamespace(payment_id="p1")
        self.assertTrue(detector.process_payment(payment, {"amount": 50000, "card_last4": "8012"}))
        self.assertEqual(db.status_updates, [("p1", "paid")])


if __name__ == "__main__":
    unittest.main()
