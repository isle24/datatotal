import io
import json
import unittest
from unittest.mock import patch

from server.services import go_collector_client as client


class CollectorClientTests(unittest.TestCase):
    def test_large_valid_connection_response_is_not_truncated(self):
        payload = {"connections": [{"name": "demo", "detail": "x" * 600} for _ in range(120)]}
        with patch.object(client.urllib.request, "urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
            self.assertEqual(client.connections(), payload)

    def test_oversized_response_reports_failure(self):
        with patch.object(client, "MAX_RESPONSE_BYTES", 32, create=True), patch.object(
            client.urllib.request, "urlopen", return_value=io.BytesIO(b'{"padding":"' + b'x' * 100 + b'"}')
        ):
            self.assertIsNone(client.connections())
            self.assertIn("large", client.request_status()["error"])

    def test_snapshot_requests_share_a_short_cache(self):
        client.clear_snapshot_cache()
        with patch.object(client, "_get", return_value={"interfaces": {"eth0": {}}}) as fetch:
            self.assertEqual(client.snapshot(), client.snapshot())
            self.assertEqual(fetch.call_count, 1)
        client.clear_snapshot_cache()


if __name__ == "__main__":
    unittest.main()
