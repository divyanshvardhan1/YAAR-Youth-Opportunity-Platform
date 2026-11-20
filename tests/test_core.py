"""Built-in unittest checks for Y.A.A.R.; no third-party dependencies."""
import tempfile
import unittest
from pathlib import Path

import app


class YAARCoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.original_db = app.DB
        app.DB = Path(self.tmp.name) / 'temporary-test.db'

    def tearDown(self):
        app.DB = self.original_db
        self.tmp.cleanup()

    def test_password_hash_and_verification(self):
        stored = app.password_hash('correct-password')
        self.assertTrue(app.verify('correct-password', stored))
        self.assertFalse(app.verify('incorrect-password', stored))
        self.assertNotEqual(stored, 'correct-password')

    def test_initialization_seeds_fictional_data(self):
        app.init_db()
        with app.database() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM users').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM opportunities').fetchone()[0], 8)

    def test_recommendations_are_ranked(self):
        youth = {'skills':'teaching communication', 'interests':'education', 'location':'Noida', 'availability':'Weekend'}
        opportunities = [
            {'id':1,'title':'Weekend teaching','category':'Education','skills':'teaching communication','description':'Teach children','location':'Noida','availability':'Weekend','mode':'On-site'},
            {'id':2,'title':'Data workshop','category':'Technology','skills':'python data analysis','description':'Work on spreadsheets','location':'Delhi','availability':'Weekday','mode':'On-site'},
        ]
        matched = app.recommend(youth, opportunities)
        self.assertEqual(matched[0][0]['id'], 1)
        self.assertGreater(matched[0][1], matched[1][1])
        self.assertTrue(all(0 <= row[1] <= 100 for row in matched))

    def test_duplicate_application_blocked_by_database(self):
        app.init_db()
        with app.database() as c:
            youth_id = c.execute("SELECT id FROM users WHERE role='youth'").fetchone()[0]
            opportunity_id = c.execute('SELECT id FROM opportunities LIMIT 1').fetchone()[0]
            c.execute('INSERT INTO applications(youth_id, opportunity_id) VALUES (?,?)', (youth_id,opportunity_id))
            with self.assertRaises(app.sqlite3.IntegrityError):
                c.execute('INSERT INTO applications(youth_id, opportunity_id) VALUES (?,?)', (youth_id,opportunity_id))


if __name__=='__main__':
    unittest.main()
