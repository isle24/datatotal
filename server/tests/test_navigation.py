import sqlite3
import threading
import unittest

from server.models.navigation import NavigationEntry, NavigationRepository


class NavigationTests(unittest.TestCase):
    def setUp(self):
        self.db = type('DB', (), {'conn': sqlite3.connect(':memory:'), 'lock': threading.RLock()})()
        self.repo = NavigationRepository(self.db)

    def test_crud_and_duplicate_import_preserves_customizations(self):
        item = NavigationEntry(name='qBittorrent', url='http://nas:8080', sourceKey='docker:qb:8080')
        saved = self.repo.save(item)
        saved['name'] = 'Downloads'
        self.repo.save(NavigationEntry(**saved))
        duplicate = self.repo.save(item)
        self.assertEqual(duplicate['name'], 'Downloads')
        self.assertEqual(len(self.repo.list()), 1)
        self.assertEqual(NavigationRepository(self.db).list()[0]['id'], saved['id'])
        self.repo.delete(saved['id'])
        self.assertEqual(self.repo.list(), [])

    def test_no_upsert_for_missing_id(self):
        with self.assertRaises(KeyError):
            self.repo.save(NavigationEntry(id='missing', name='A', url='https://example.com'))

    def test_rejects_active_content_and_credentials(self):
        for url in ['javascript:alert(1)', 'file:///etc/passwd', 'https://user:pass@nas/', '//example.com', 'http://nas:bad']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                NavigationEntry(name='A', url=url)
        for icon in ['https://example.com/a.png', 'data:image/svg+xml;base64,PHN2Zz4=', 'data:image/png;base64,invalid']:
            with self.subTest(icon=icon), self.assertRaises(ValueError):
                NavigationEntry(name='A', url='https://example.com', icon=icon)

    def test_other_settings_survive(self):
        self.db.conn.execute('CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT)')
        self.db.conn.execute("INSERT INTO settings VALUES ('rules','retained')")
        self.repo.save(NavigationEntry(name='A', url='http://[::1]:8088'))
        self.assertEqual(self.db.conn.execute('SELECT value FROM settings').fetchone()[0], 'retained')

    def test_unknown_api_is_json_404_and_navigation_requires_auth(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import server.main as main
        client = TestClient(main.app)
        with patch.object(main, 'DASHBOARD_PASSWORD', 'test-only-password'):
            self.assertEqual(client.get('/api/navigation').status_code, 401)
            self.assertEqual(client.post('/api/navigation', json={'name':'Test', 'url':'http://nas'}).status_code, 401)
        with patch.object(main, 'DASHBOARD_PASSWORD', ''):
            response = client.get('/api/unknown-test-endpoint')
            self.assertEqual(response.status_code, 404)
            self.assertIn('not available', response.json()['detail'])
