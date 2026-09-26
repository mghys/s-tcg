from __future__ import annotations

import json
import threading
import unittest
from http.client import HTTPConnection
from typing import Any
from unittest.mock import patch

from http.server import ThreadingHTTPServer

from ws_tcg.web import CalculatorHandler
from ws_tcg.web import serve


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), CalculatorHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def post_json(self, payload: object) -> tuple[int, dict[str, Any]]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        body = json.dumps(payload).encode("utf-8")
        connection.request(
            "POST",
            "/api/ws/lethal-calculations",
            body=body,
            headers={"Content-Type": "application/json"},
        )
        response = connection.getresponse()
        result = json.loads(response.read())
        connection.close()
        return response.status, result

    def test_api_accepts_user_formats_and_returns_exact_result(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 5,
                "deck_climax": 0,
                "waiting_count": 0,
                "waiting_climax": 0,
                "level_clock": "1-4",
                "clock_climax": 0,
                "damage_sequence": "5",
            }
        )
        self.assertEqual(status, 200)
        defeat = result["defeat_probability"]
        survival = result["survival_probability"]
        self.assertEqual(defeat["numerator"], 0)
        self.assertEqual(survival["numerator"], 1)
        self.assertTrue(any("逐张" in item for item in result["assumptions"]))

    def test_api_keeps_legacy_damage_sequence_format(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 8,
                "deck_climax": 2,
                "waiting_count": 0,
                "waiting_climax": 0,
                "level_clock": "1-4",
                "clock_climax": 0,
                "damage_sequence": "2-2-3-4",
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            result["defeat_probability"]["numerator"]
            / result["defeat_probability"]["denominator"]
            + result["survival_probability"]["numerator"]
            / result["survival_probability"]["denominator"],
            1,
        )

    def test_api_returns_clear_error_for_missing_clock_climax(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 5,
                "deck_climax": 0,
                "waiting_count": 0,
                "waiting_climax": 0,
                "level_clock": "1-4",
                "damage_sequence": "2-2-3-4",
            }
        )
        self.assertEqual(status, 400)
        self.assertEqual(result["error"]["code"], "INVALID_INPUT")
        self.assertIn("clock_climax", result["error"]["message"])

    def test_api_rejects_malformed_level_clock(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 5,
                "deck_climax": 0,
                "waiting_count": 0,
                "waiting_climax": 0,
                "level_clock": "1/4",
                "clock_climax": 0,
                "damage_sequence": "1",
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("1-4", result["error"]["message"])

    def test_api_requires_level_clock_state(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 5,
                "deck_climax": 0,
                "waiting_count": 0,
                "waiting_climax": 0,
                "clock_climax": 0,
                "damage_sequence": "1",
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("level_clock", result["error"]["message"])

    def test_api_accepts_mixed_mocha_operation_sequence(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 8,
                "deck_climax": 2,
                "waiting_count": 3,
                "waiting_climax": 1,
                "level_clock": "1-4",
                "clock_climax": 0,
                "operation_sequence": "摩卡2-3-摩卡2-3-摩卡3-3",
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            result["defeat_probability"]["numerator"]
            / result["defeat_probability"]["denominator"]
            + result["survival_probability"]["numerator"]
            / result["survival_probability"]["denominator"],
            1,
        )
        self.assertTrue(any("摩卡" in item for item in result["assumptions"]))

    def test_api_accepts_both_bottom_operation_text_formats(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 12,
                "deck_climax": 3,
                "waiting_count": 8,
                "waiting_climax": 2,
                "level_clock": "1-3",
                "clock_climax": 0,
                "operation_sequence": "掏底条件4-2-掏底计次5-3",
            }
        )
        self.assertEqual(status, 200)
        self.assertTrue(any("掏底" in item for item in result["assumptions"]))
        self.assertTrue(any("不额外重复结算" in item for item in result["assumptions"]))

    def test_api_accepts_structured_bottom_operations(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 12,
                "deck_climax": 3,
                "waiting_count": 8,
                "waiting_climax": 2,
                "level_clock": "1-3",
                "clock_climax": 0,
                "operation_sequence": [
                    {"type": "bottom_conditional", "mill": 4, "damage": 2},
                    {"type": "bottom_per_climax", "mill": 5, "damage": 3},
                ],
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            result["defeat_probability"]["numerator"]
            / result["defeat_probability"]["denominator"]
            + result["survival_probability"]["numerator"]
            / result["survival_probability"]["denominator"],
            1,
        )

    def test_api_rejects_mocha_look_above_supported_limit(self) -> None:
        status, result = self.post_json(
            {
                "deck_count": 8,
                "deck_climax": 2,
                "waiting_count": 0,
                "waiting_climax": 0,
                "level_clock": "1-0",
                "clock_climax": 0,
                "operation_sequence": "摩卡11-1",
            }
        )
        self.assertEqual(status, 400)
        self.assertIn("1–10", result["error"]["message"])

    def test_page_and_rules_endpoint_are_available(self) -> None:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request("GET", "/")
        page = connection.getresponse()
        self.assertEqual(page.status, 200)
        self.assertIn("WS 斩杀概率计算器", page.read().decode("utf-8"))
        connection.request("GET", "/api/ws/rules")
        rules = connection.getresponse()
        self.assertEqual(rules.status, 200)
        rules_data = json.loads(rules.read())
        self.assertEqual(rules_data["clock_size"], 7)
        self.assertEqual(rules_data["max_mocha_look"], 10)
        self.assertEqual(rules_data["max_bottom_mill"], 5)
        self.assertEqual(rules_data["max_bottom_conditional_damage"], 4)
        self.assertEqual(rules_data["max_bottom_per_climax_damage"], 50)
        self.assertEqual(rules_data["max_bottom_climax_hits"], 5)
        connection.close()

    def test_frozen_serve_reports_ephemeral_url_and_opens_browser(self) -> None:
        opened: list[str] = []

        def fake_serve_forever(self: ThreadingHTTPServer) -> None:
            return None

        with (
            patch(
                "ws_tcg.web.webbrowser.open_new_tab",
                side_effect=lambda url: opened.append(url) or True,
            ),
            patch.object(ThreadingHTTPServer, "serve_forever", fake_serve_forever),
            patch("builtins.print") as printed,
        ):
            serve(port=0, open_browser=True)

        self.assertEqual(len(opened), 1)
        self.assertRegex(opened[0], r"^http://127\.0\.0\.1:\d+$")
        self.assertTrue(any(opened[0] in str(call) for call in printed.call_args_list))


if __name__ == "__main__":
    unittest.main()
