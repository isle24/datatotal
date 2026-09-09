import asyncio
import threading
import unittest
from unittest.mock import patch

import server.main as main


class APITests(unittest.TestCase):
    def test_slow_docker_request_does_not_block_event_loop(self):
        async def run():
            entered, release = threading.Event(), threading.Event()
            def slow(*args):
                entered.set()
                release.wait(1)
                return {"ok": True}
            with patch.object(main.collector, "docker_container_stats", side_effect=slow):
                task = asyncio.create_task(main.docker_container_stats_api("demo"))
                await asyncio.sleep(0.03)
                was_running = not task.done()
                release.set()
                await task
                self.assertTrue(was_running, "event loop was blocked until Docker finished")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
