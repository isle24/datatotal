import json
import unittest

from server.services import ops_agent


class FakeContext:
    """Canned read-only data so the tools can be exercised without a NAS."""

    def overview(self):
        return {
            "timestamp": 1791380000,
            "summary": {
                "wan": {"rxBps": 1024 * 1024 * 3, "txBps": 1024 * 512, "rxBytes": 1024 ** 3, "txBytes": 1024 ** 2 * 300},
                "lan": {"rxBps": 2048, "txBps": 4096, "rxBytes": 1024 ** 2, "txBytes": 1024 ** 2 * 2},
                "interfaces": {"up": 3, "total": 3},
            },
            "connectionSummary": {"wan": 17, "total": 349, "source": "conntrack"},
            "containerStatus": {"enabled": True, "count": 27},
        }

    def history(self, period):
        return {
            "period": period,
            "buckets": [
                {"label": "00:00", "wan": {"rxBytes": 10, "txBytes": 20}},
                {"label": "12:00", "wan": {"rxBytes": 5 * 1024 ** 2, "txBytes": 9 * 1024 ** 2}},
                {"label": "23:00", "wan": {"rxBytes": 1024, "txBytes": 2048}},
            ],
            "totals": {"wan": {"rxBytes": 8 * 1024 ** 2, "txBytes": 2 * 1024 ** 2},
                       "lan": {"rxBytes": 1024, "txBytes": 2048}},
        }

    def processes(self, period, limit):
        return {
            "period": period,
            "processes": [
                {"name": "qbittorrent", "pid": 101, "txBytes": 5 * 1024 ** 2, "rxBytes": 1024, "cmdline": "qbittorrent-nox"},
                {"name": "redis-server", "pid": 202, "txBytes": 1024, "rxBytes": 3 * 1024 ** 2, "cmdline": "redis-server"},
            ],
        }

    def connections(self, scope, direction, limit):
        return {
            "connections": [
                {"process": {"name": "qbittorrent", "pid": 101, "container": {"name": "qbittorrent"}},
                 "source": "192.168.3.56", "dest": "1.2.3.4", "direction": "tx",
                 "proto": "tcp", "txBytes": 1024, "rxBytes": 2048, "durationSeconds": 120},
            ],
            "pagination": {"total": 1},
        }

    def system(self):
        return {
            "cpu": {"percent": 12.5, "countLogical": 18, "loadAverage": [0.4, 0.3, 0.2]},
            "memory": {"percent": 41.0, "used": 8 * 1024 ** 3, "total": 23 * 1024 ** 3},
            "disk": {"percent": 9.2, "used": 173 * 1024 ** 3, "total": 1800 * 1024 ** 3},
            "temperatureGroups": [
                {"name": "CPU", "readings": [{"label": "CPU 封装", "current": 51.0}]},
                {"name": "NVMe 1", "readings": [{"label": "控制器", "current": 50.9}]},
            ],
            "fans": [{"name": "风扇 1", "rpm": 1200}],
            "gpu": [{"name": "Intel 核显", "utilPercent": 0.0, "driver": "i915"}],
            "npu": [{"name": "Intel NPU", "utilPercent": 0.0}],
            "vpu": [{"name": "Rockchip VPU", "utilPercent": 62.5, "decodePercent": 62.5, "encodePercent": 0.0}],
            "uptimeSeconds": 1209600,
        }

    def docker_containers(self):
        return {
            "enabled": True,
            "containers": [
                {"id": "abc123def456", "name": "qbittorrent", "image": "linuxserver/qbittorrent:latest",
                 "state": "running", "ports": [{"hostPort": 8080}], "protection": {"enabled": True}},
                {"id": "fff999aaa111", "name": "redis", "image": "redis:7",
                 "state": "restarting", "ports": [], "protection": {"enabled": False}},
            ],
        }

    def docker_stats(self, container_id):
        return {
            "stats": {
                "state": "running", "cpuPercent": 12.5, "memoryPercent": 4.2,
                "memoryUsedBytes": 256 * 1024 ** 2,
                "blkio": {"readBps": 0, "writeBps": 52 * 1024 ** 2},
                "network": {"rxBps": 1024, "txBps": 2048},
            }
        }

    def alerts(self, limit):
        return {"count": 1, "alerts": [{"createdAt": 1791380000, "ruleName": "上传告警", "severity": "warning",
                                        "message": "公网上传超过阈值", "status": "sent"}]}

    def settings(self):
        return {
            "monitor": {
                "rules": [{"name": "每日上传", "enabled": True, "metric": "daily_wan_tx_bytes"}],
                "containerRules": [{"name": "Redis 保护", "enabled": True, "action": "restart"}],
                "channels": [{"name": "webhook", "type": "webhook", "enabled": True, "url": "https://example.com/hook",
                              "token": "supersecret-token-value"}],
            },
            "runtime": {"sampleSeconds": 1, "retentionSeconds": 3600, "dockerDiscovery": True},
            "ai": {"enabled": True, "provider": "openai", "model": "gpt-4o-mini", "apiKey": "sk-abcdefghijklmnopqrstuvwxyz0123456789"},
        }


class ToolCatalogTests(unittest.TestCase):
    def test_every_tool_is_read_only(self):
        for spec in ops_agent.TOOL_SPECS:
            self.assertEqual(spec["handler"].__name__.startswith("_tool_"), True)
        catalog = ops_agent.tool_catalog()
        self.assertGreaterEqual(len(catalog), 8)
        self.assertTrue(all(entry["risk"] == ops_agent.RISK_READ for entry in catalog))
        names = {entry["name"] for entry in catalog}
        for expected in ("traffic_summary", "traffic_history", "traffic_processes", "system_status",
                         "docker_containers", "docker_container_stats", "alerts_recent", "settings_summary"):
            self.assertIn(expected, names)


class ValidateArgsTests(unittest.TestCase):
    def test_defaults_are_applied(self):
        args, error = ops_agent.validate_args("traffic_processes", {})
        self.assertEqual(error, "")
        self.assertEqual(args, {"period": "30s", "metric": "upload", "limit": 10})

    def test_enum_and_type_errors_are_rejected(self):
        self.assertIn("period", ops_agent.validate_args("traffic_history", {"period": "yesterday"})[1])
        self.assertIn("limit", ops_agent.validate_args("traffic_processes", {"limit": "many"})[1])
        self.assertIn("未知工具", ops_agent.validate_args("rm_rf", {})[1])
        self.assertIn("不支持的参数", ops_agent.validate_args("traffic_summary", {"force": True})[1])

    def test_numbers_are_clamped_and_strings_trimmed(self):
        args, _ = ops_agent.validate_args("traffic_processes", {"limit": 9999})
        self.assertEqual(args["limit"], ops_agent.MAX_LIMIT)
        args, _ = ops_agent.validate_args("traffic_processes", {"limit": -5})
        self.assertEqual(args["limit"], 1)
        args, _ = ops_agent.validate_args("docker_containers", {"filter": "  redis  "})
        self.assertEqual(args["filter"], "redis")
        self.assertIn("过长", ops_agent.validate_args("docker_containers", {"filter": "x" * 200})[1])
        self.assertIn("缺少参数", ops_agent.validate_args("docker_container_stats", {})[1])


class RedactionTests(unittest.TestCase):
    def test_secrets_never_reach_the_model(self):
        payload = {
            "channels": [{"name": "hook", "url": "https://example.com/hook", "token": "abc", "apiKey": "xyz"}],
            "nested": {"Password": "hunter2", "webhookUrl": "https://secret"},
            "ok": "visible",
        }
        cleaned = ops_agent.redact(payload)
        self.assertEqual(cleaned["channels"][0]["token"], "[redacted]")
        self.assertEqual(cleaned["channels"][0]["apiKey"], "[redacted]")
        self.assertEqual(cleaned["nested"]["Password"], "[redacted]")
        self.assertEqual(cleaned["nested"]["webhookUrl"], "[redacted]")
        self.assertEqual(cleaned["ok"], "visible")

    def test_long_values_are_truncated(self):
        cleaned = ops_agent.redact({"note": "x" * 1000, "tokenish": "a" * 64})
        self.assertLessEqual(len(cleaned["note"]), ops_agent.MAX_STRING + 1)
        self.assertEqual(cleaned["tokenish"], "[redacted]")

    def test_trim_payload_bounds_large_results(self):
        payload = {"rows": [{"index": index, "payload": "y" * 200} for index in range(200)]}
        trimmed = ops_agent.trim_payload(payload, max_chars=2000)
        self.assertLessEqual(len(json.dumps(trimmed, ensure_ascii=False)), 2400)
        self.assertTrue(trimmed.get("truncated"))


class RunToolTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeContext()

    def test_every_tool_runs_with_its_defaults(self):
        for spec in ops_agent.TOOL_SPECS:
            supplied = {name: "redis" for name, schema in spec["params"].items() if schema.get("required")}
            args, error = ops_agent.validate_args(spec["name"], supplied)
            self.assertEqual(error, "", spec["name"])
            result = ops_agent.run_tool(spec["name"], args, self.ctx)
            self.assertTrue(result["ok"], f"{spec['name']} failed: {result.get('error')}")
            self.assertTrue(result["data"], spec["name"])
            self.assertIn("durationMs", result)

    def test_process_ranking_sorts_by_the_requested_metric(self):
        result = ops_agent.run_tool("traffic_processes", {"period": "1h", "metric": "download", "limit": 5}, self.ctx)
        self.assertEqual(result["data"]["排行"][0]["进程"], "redis-server")
        result = ops_agent.run_tool("traffic_processes", {"period": "1h", "metric": "upload", "limit": 5}, self.ctx)
        self.assertEqual(result["data"]["排行"][0]["进程"], "qbittorrent")

    def test_container_lookup_reports_unknown_names(self):
        found = ops_agent.run_tool("docker_container_stats", {"container": "redis"}, self.ctx)
        self.assertEqual(found["data"]["容器"], "redis")
        self.assertEqual(found["data"]["磁盘"]["写"], "52 MB/s")
        missing = ops_agent.run_tool("docker_container_stats", {"container": "nope"}, self.ctx)
        self.assertIn("错误", missing["data"])
        self.assertIn("qbittorrent", missing["data"]["可用容器"])

    def test_settings_tool_hides_credentials(self):
        result = ops_agent.run_tool("settings_summary", {}, self.ctx)
        encoded = json.dumps(result["data"], ensure_ascii=False)
        self.assertNotIn("supersecret-token-value", encoded)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz0123456789", encoded)
        self.assertIn("每日上传", encoded)

    def test_tool_errors_are_returned_not_raised(self):
        class Broken(FakeContext):
            def overview(self):
                raise RuntimeError("collector offline")

        result = ops_agent.run_tool("traffic_summary", {}, Broken())
        self.assertFalse(result["ok"])
        self.assertIn("collector offline", result["error"])


class ParsePlanTests(unittest.TestCase):
    def test_plan_survives_code_fences_and_prose(self):
        plan, error = ops_agent.parse_plan('```json\n{"tool": "traffic_summary", "args": {}}\n```')
        self.assertEqual(error, "")
        self.assertEqual(plan["tool"], "traffic_summary")
        plan, error = ops_agent.parse_plan('好的，我来查：{"tool": "traffic_history", "args": {"period": "week"}} 完毕')
        self.assertEqual(plan["args"]["period"], "week")

    def test_unparseable_plans_are_rejected(self):
        self.assertIn("计划", ops_agent.parse_plan("我不知道")[1])
        self.assertIn("合法 JSON", ops_agent.parse_plan("{tool: traffic_summary}")[1])


class AnswerQuestionTests(unittest.TestCase):
    def setUp(self):
        self.ctx = FakeContext()
        self.settings = {"enabled": True, "model": "test-model", "provider": "openai"}

    def _chat(self, replies):
        calls = []

        def chat(settings, messages):
            calls.append(messages)
            return {"answer": replies[min(len(calls) - 1, len(replies) - 1)]}

        chat.calls = calls
        return chat

    def test_plan_then_answer_uses_two_calls_and_returns_the_data(self):
        chat = self._chat([
            '{"tool": "traffic_history", "args": {"period": "day"}, "reason": "问的是今天"}',
            "今天公网上行 2.0 MB，下行 8.0 MB。",
        ])
        result = ops_agent.answer_question("今天上传了多少流量", self.settings, self.ctx, chat=chat)
        self.assertTrue(result["ok"])
        self.assertEqual(result["calls"], 2)
        self.assertEqual(result["tool"], "traffic_history")
        self.assertEqual(result["args"]["period"], "day")
        self.assertIn("今天公网", result["answer"])
        self.assertGreater(result["tokensEstimate"], 0)
        self.assertEqual([step["step"] for step in result["trace"]], ["plan", "tool", "answer"])
        # The model never receives write tools, only the read catalogue.
        self.assertIn("只读", chat.calls[0][0]["content"])
        self.assertNotIn("restart", chat.calls[0][1]["content"])

    def test_invalid_plan_arguments_stop_before_running_anything(self):
        chat = self._chat(['{"tool": "traffic_history", "args": {"period": "yesterday"}}'])
        result = ops_agent.answer_question("昨天呢", self.settings, self.ctx, chat=chat)
        self.assertFalse(result["ok"])
        self.assertEqual(result["calls"], 1)
        self.assertIn("period", result["error"])
        self.assertEqual(len(chat.calls), 1)

    def test_irrelevant_questions_answer_directly(self):
        chat = self._chat(['{"tool": "none", "args": {}, "reason": "这个问题和监控数据无关"}'])
        result = ops_agent.answer_question("今天天气如何", self.settings, self.ctx, chat=chat)
        self.assertTrue(result["ok"])
        self.assertEqual(result["calls"], 1)
        self.assertEqual(result["tool"], "none")
        self.assertIn("无关", result["answer"])

    def test_disabled_ai_short_circuits(self):
        chat = self._chat(["{}"])
        result = ops_agent.answer_question("流量", {"enabled": False, "model": ""}, self.ctx, chat=chat)
        self.assertFalse(result["ok"])
        self.assertIn("AI 未启用", result["error"])
        self.assertEqual(len(chat.calls), 0)

    def test_empty_question_is_rejected(self):
        result = ops_agent.answer_question("   ", self.settings, self.ctx, chat=self._chat(["{}"]))
        self.assertFalse(result["ok"])
        self.assertIn("请输入问题", result["error"])

    def test_unknown_container_is_reported_to_the_user(self):
        chat = self._chat(['{"tool": "docker_container_stats", "args": {"container": "nope"}}',
                           "没有找到叫 nope 的容器，可用的是 qbittorrent 和 redis。"])
        result = ops_agent.answer_question("nope 容器占多少内存", self.settings, self.ctx, chat=chat)
        self.assertTrue(result["ok"])
        self.assertEqual(result["calls"], 2)
        self.assertIn("错误", result["data"])
        self.assertIn("没有找到", result["answer"])


if __name__ == "__main__":
    unittest.main()


class AgentApiTests(unittest.TestCase):
    """Endpoint wiring: read-only catalogue, audited query, usage summary."""

    def test_tool_catalogue_endpoint_lists_only_read_tools(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        import server.main as main

        client = TestClient(main.app)
        with patch.object(main, "DASHBOARD_PASSWORD", ""):
            response = client.get("/api/agent/tools")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["tools"])
        self.assertTrue(all(tool["risk"] == "read" for tool in body["tools"]))
        self.assertIn("usage", body)
        self.assertIn("enabled", body)

    def test_query_endpoint_returns_the_answer_trace_and_audits_it(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch

        import server.main as main

        canned = {
            "ok": True, "answer": "今天公网上行 2 MB。", "tool": "traffic_history",
            "toolLabel": "历史流量统计", "args": {"period": "day"}, "data": {"周期": "day"},
            "calls": 2, "tokensEstimate": 120, "trace": [{"step": "plan"}],
        }
        client = TestClient(main.app)
        with patch.object(main, "DASHBOARD_PASSWORD", ""), \
             patch.object(main.ops_agent, "answer_question", return_value=canned) as mocked:
            response = client.post("/api/agent/query", json={"question": "今天上传了多少"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["tool"], "traffic_history")
        self.assertIn("durationMs", body)
        self.assertIn("usage", body)
        self.assertEqual(mocked.call_args[0][0], "今天上传了多少")

    def test_audit_rows_are_persisted_and_listed(self):
        from fastapi.testclient import TestClient
        from unittest.mock import patch
        import sqlite3
        import tempfile
        from pathlib import Path

        import server.main as main

        with tempfile.TemporaryDirectory() as tmp:
            database = main.TrafficDB(Path(tmp) / "audit.db")
            database.start()
            try:
                database.record_agent_audit({
                    "createdAt": 1791380000, "question": "哪个进程上传最多", "tool": "traffic_processes",
                    "args": {"metric": "upload"}, "ok": True, "error": "",
                    "answerChars": 40, "calls": 2, "tokensEstimate": 180, "durationMs": 900,
                })
                rows = database.query_agent_audits(10)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["tool"], "traffic_processes")
                self.assertEqual(rows[0]["args"], {"metric": "upload"})
                usage = database.agent_usage_summary()
                # The sample row is stamped "today", so it counts towards the daily usage.
                self.assertEqual(usage["questions"], 1)
                self.assertEqual(usage["calls"], 2)
                self.assertEqual(usage["tokensEstimate"], 180)
                column = database.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='ops_agent_audits'"
                ).fetchone()
                self.assertIsNotNone(column)
            finally:
                database.conn.close()

    def test_client_helper_matches_the_schema(self):
        import server.main as main

        # The request model must reject empty and oversized questions before any AI call.
        from pydantic import ValidationError

        main.AgentQueryPayload(question="正常问题")
        for bad in ("", "x" * 600):
            with self.assertRaises(ValidationError):
                main.AgentQueryPayload(question=bad)


class RankingAndMappingTests(unittest.TestCase):
    """Live payloads exposed two mapping bugs and one missing tool."""

    def setUp(self):
        self.ctx = FakeContext()

    def test_container_ranking_sorts_by_disk_write(self):
        class Context(FakeContext):
            def docker_stats(self, container_id):
                write = 52 * 1024 ** 2 if container_id.startswith("fff") else 1024
                return {"stats": {"state": "running", "cpuPercent": 1.0, "memoryUsedBytes": 1024,
                                  "blkio": {"readBps": 0, "writeBps": write},
                                  "network": {"rxBps": 0, "txBps": 0}}}

        result = ops_agent.run_tool("docker_top_consumers", {"metric": "disk_write", "limit": 5}, Context())
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["排行"][0]["名称"], "redis")
        # The metric measures a rate, and the result says so explicitly.
        self.assertIn("速率", result["data"]["口径说明"])
        self.assertEqual(result["data"]["排行"][0]["磁盘写入"], "52 MB/s")
        self.assertEqual(result["data"]["已扫描容器"], 2)

    def test_container_ranking_survives_a_broken_container(self):
        class Context(FakeContext):
            def docker_stats(self, container_id):
                if container_id.startswith("fff"):
                    raise RuntimeError("docker api timeout")
                return {"stats": {"blkio": {"writeBps": 0}, "network": {}, "cpuPercent": 0}}

        result = ops_agent.run_tool("docker_top_consumers", {"metric": "cpu", "limit": 5}, Context())
        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["跳过容器"], 1)

    def test_connections_use_the_real_source_dest_shape(self):
        result = ops_agent.run_tool("traffic_connections", {"scope": "wan", "direction": "all", "limit": 5}, self.ctx)
        row = result["data"]["连接"][0]
        self.assertEqual(row["进程"], "qbittorrent")
        self.assertEqual(row["来源"], "192.168.3.56")
        self.assertEqual(row["目标"], "1.2.3.4")
        self.assertEqual(row["方向"], "tx")
        self.assertEqual(row["时长"], "2分")

    def test_process_window_defaults_to_the_live_snapshot(self):
        args, error = ops_agent.validate_args("traffic_processes", {})
        self.assertEqual(error, "")
        self.assertEqual(args["period"], "30s")
        self.assertIn("today", ops_agent.TOOL_SPECS[2]["params"]["period"]["values"])
