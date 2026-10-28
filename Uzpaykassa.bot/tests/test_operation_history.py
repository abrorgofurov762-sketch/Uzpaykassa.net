import os
import sqlite3
import tempfile
import threading
import unittest

from database.database import Database


class OperationHistoryTests(unittest.TestCase):
    def setUp(self):
        handle, self.path = tempfile.mkstemp(suffix='.sqlite3')
        os.close(handle)
        conn = sqlite3.connect(self.path)
        conn.execute('''CREATE TABLE withdrawals (
            id INTEGER PRIMARY KEY, user_id INTEGER, bukmeker TEXT, player_id TEXT,
            card_number TEXT, code TEXT, amount REAL, status TEXT, created_at TEXT
        )''')
        conn.execute("INSERT INTO withdrawals VALUES (1, 10, 'Mostbet', 'player1', '8600123412345678', 'private-code', 50000, 'pending', '2026-10-26 10:00:00')")
        conn.execute("INSERT INTO withdrawals VALUES (2, 20, 'Mostbet', 'player2', '8600123412345678', 'private-code', 70000, 'pending', '2026-10-26 11:00:00')")
        conn.commit()
        conn.close()
        self.db = Database.__new__(Database)
        self.db.db_path = self.path
        self.db.lock = threading.Lock()

    def tearDown(self):
        try:
            os.unlink(self.path)
        except OSError:
            pass

    def test_history_is_scoped_to_user_and_newest_first(self):
        history = self.db.get_user_withdrawals(10, limit=10)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0].id, 1)
        self.assertEqual(history[0].user_id, 10)

    def test_history_limit_is_bounded(self):
        self.assertEqual(len(self.db.get_user_withdrawals(20, limit=999)), 1)


if __name__ == '__main__':
    unittest.main()
