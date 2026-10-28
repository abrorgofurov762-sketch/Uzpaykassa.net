import os
import sqlite3
import tempfile
import threading
import unittest

from database.database import Database
from database.models import Payment
from unittest.mock import patch


class DatabaseTransitionTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(handle)
        conn = sqlite3.connect(self.path)
        conn.execute('CREATE TABLE payments (payment_id TEXT PRIMARY KEY, status TEXT, updated_at TEXT)')
        conn.execute("INSERT INTO payments(payment_id, status) VALUES ('p-1', 'pending')")
        conn.execute('CREATE TABLE withdrawals (id INTEGER PRIMARY KEY, status TEXT)')
        conn.execute("INSERT INTO withdrawals(id, status) VALUES (1, 'pending')")
        conn.commit()
        conn.close()
        self.db = Database.__new__(Database)
        self.db.db_path = self.path
        self.db.lock = threading.Lock()
        self.db.has_updated_at = True

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_payment_transition_only_claims_pending_once(self):
        self.assertTrue(self.db.transition_payment_status('p-1', 'pending', 'processing'))
        self.assertFalse(self.db.transition_payment_status('p-1', 'pending', 'processing'))
        conn = sqlite3.connect(self.path)
        status = conn.execute("SELECT status FROM payments WHERE payment_id='p-1'").fetchone()[0]
        conn.close()
        self.assertEqual(status, 'processing')

    def test_missing_payment_does_not_transition(self):
        self.assertFalse(self.db.transition_payment_status('missing', 'pending', 'processing'))

    def test_withdrawal_confirmation_only_succeeds_once(self):
        self.assertTrue(self.db.update_withdrawal_status(1, 'completed', expected_status='pending'))
        self.assertFalse(self.db.update_withdrawal_status(1, 'completed', expected_status='pending'))
        self.assertFalse(self.db.update_withdrawal_status(999, 'completed', expected_status='pending'))

    def test_rejects_unknown_status(self):
        self.assertFalse(self.db.update_withdrawal_status(1, 'paid'))
        self.assertFalse(self.db.transition_payment_status('p-1', 'pending', 'made_up'))
        self.assertFalse(self.db.update_payment_status('p-1', 'made_up'))

    def test_terminal_withdrawal_cannot_be_reopened(self):
        self.assertTrue(self.db.update_withdrawal_status(1, 'completed', expected_status='pending'))
        self.assertFalse(self.db.update_withdrawal_status(1, 'pending'))
        self.assertFalse(self.db.update_withdrawal_status(1, 'approved', expected_status='completed'))

    def test_payment_keeps_bank_amount_separate_from_bookmaker_amount(self):
        handle, path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(handle)
        try:
            with patch('database.database.DATABASE_PATH', path):
                db = Database()
            payment = Payment(
                user_id=101, bukmeker='Mostbet', player_id='774', amount=50007,
                payment_id='mb-1', card_last4='8012', deposit_amount=50000,
            )
            self.assertTrue(db.add_payment(payment))
            loaded = db.get_payment_by_id('mb-1')
            self.assertEqual(loaded.amount, 50007)
            self.assertEqual(loaded.deposit_amount, 50000)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    def test_approval_requires_pending_state(self):
        self.assertTrue(self.db.update_withdrawal_status(1, 'approved', expected_status='pending'))
        self.assertFalse(self.db.update_withdrawal_status(1, 'approved', expected_status='pending'))
        self.assertFalse(self.db.update_withdrawal_status(1, 'completed', expected_status='completed'))


if __name__ == '__main__':
    unittest.main()
