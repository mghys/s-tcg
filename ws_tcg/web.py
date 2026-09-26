"""Minimal standard-library web application for the WS calculator."""

from __future__ import annotations

import json
import re
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .engine import calculate
from .model import (
    MODEL_VERSION,
    RULE_VERSION,
    BottomConditional,
    BottomPerClimax,
    CalculationInput,
    Damage,
    InputError,
    MAX_DAMAGE_PER_SEGMENT,
    Mocha,
    Operation,
)


ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "frontend" / "index.html"


def _parse_damage(value: Any) -> tuple[int, ...]:
    if isinstance(value, str):
        parts = value.replace("，", "-").replace(",", "-").split("-")
        if not parts or any(not part.strip() for part in parts):
            raise InputError("伤害序列格式错误，请输入如 2-2-3-4。")
        try:
            return tuple(int(part.strip()) for part in parts)
        except ValueError as exc:
            raise InputError("伤害序列必须由整数构成，例如 2-2-3-4。") from exc
    if isinstance(value, list):
        return tuple(value)
    raise InputError("伤害序列必须是字符串或整数数组。")


def _parse_operations(value: Any) -> tuple[Operation, ...]:
    if isinstance(value, str):
        normalized = re.sub(r"\s", "", value).replace("，", "-").replace(",", "-")
        token_pattern = r"(?:掏底(?:条件|计次)\d+-\d+|摩卡\d+|\d+)"
        if not re.fullmatch(rf"{token_pattern}(?:-{token_pattern})*", normalized):
            raise InputError(
                "操作序列格式错误；可输入如 2-摩卡2-掏底条件4-2-掏底计次5-3。"
            )
        tokens = re.findall(token_pattern, normalized)
        operations: list[Operation] = []
        for token in tokens:
            token = token.strip()
            conditional = re.fullmatch(r"掏底条件(\d+)-(\d+)", token)
            per_climax = re.fullmatch(r"掏底计次(\d+)-(\d+)", token)
            if conditional:
                operations.append(
                    BottomConditional(
                        int(conditional.group(1)), int(conditional.group(2))
                    )
                )
            elif per_climax:
                operations.append(
                    BottomPerClimax(int(per_climax.group(1)), int(per_climax.group(2)))
                )
            elif re.fullmatch(r"摩卡\d+", token):
                operations.append(Mocha(int(token[2:])))
            elif re.fullmatch(r"\d+", token):
                operations.append(Damage(int(token)))
            else:
                raise InputError(
                    f"无法识别操作“{token}”，请输入伤害、摩卡x、掏底条件x-y 或掏底计次x-z。"
                )
        return tuple(operations)
    if isinstance(value, list):
        operations: list[Operation] = []
        for index, item in enumerate(value, start=1):
            if isinstance(item, int) and not isinstance(item, bool):
                operations.append(Damage(item))
            elif isinstance(item, dict) and item.get("type") == "damage":
                points = item.get("points")
                if isinstance(points, bool) or not isinstance(points, int):
                    raise InputError(f"第 {index} 个伤害操作的 points 必须是整数。")
                operations.append(Damage(points))
            elif isinstance(item, dict) and item.get("type") == "mocha":
                look = item.get("look")
                if isinstance(look, bool) or not isinstance(look, int):
                    raise InputError(f"第 {index} 个摩卡操作的 look 必须是整数。")
                operations.append(Mocha(look))
            elif isinstance(item, dict) and item.get("type") in (
                "bottom_conditional",
                "bottom_per_climax",
            ):
                mill = item.get("mill")
                damage = item.get("damage")
                if isinstance(mill, bool) or not isinstance(mill, int):
                    raise InputError(f"第 {index} 个掏底操作的 mill 必须是整数。")
                if isinstance(damage, bool) or not isinstance(damage, int):
                    raise InputError(f"第 {index} 个掏底操作的 damage 必须是整数。")
                if item["type"] == "bottom_conditional":
                    operations.append(BottomConditional(mill, damage))
                else:
                    operations.append(BottomPerClimax(mill, damage))
            else:
                raise InputError(f"第 {index} 个操作格式无效。")
        return tuple(operations)
    raise InputError("操作序列必须是文本或操作数组。")


def _parse_level_clock(data: dict[str, Any]) -> tuple[int, int]:
    if "level_clock" not in data:
        if "level" not in data or "clock" not in data:
            raise InputError("必须提供 level_clock，或同时提供 level 和 clock。")
        return data["level"], data["clock"]
    value = data["level_clock"]
    if not isinstance(value, str):
        raise InputError("等级-时计状态请按 1-4 格式输入。")
    parts = value.strip().split("-")
    if len(parts) != 2:
        raise InputError("等级-时计状态请按 1-4 格式输入。")
    try:
        return int(parts[0]), int(parts[1])
    except ValueError as exc:
        raise InputError("等级-时计状态必须由两个整数构成，例如 1-4。") from exc


def _request_from_json(data: Any) -> CalculationInput:
    if not isinstance(data, dict):
        raise InputError("请求内容必须是 JSON 对象。")
    try:
        level, clock = _parse_level_clock(data)
        if "operation_sequence" in data:
            operations = _parse_operations(data["operation_sequence"])
            return CalculationInput.from_values(
                deck_count=data["deck_count"],
                deck_climax=data["deck_climax"],
                waiting_count=data["waiting_count"],
                waiting_climax=data["waiting_climax"],
                level=level,
                clock=clock,
                clock_climax=data["clock_climax"],
                operation_sequence=operations,
            )
        sequence_value = data.get("damage_sequence", data.get("operation_text"))
        if sequence_value is None:
            raise InputError("缺少必填字段：operation_sequence")
        operations = _parse_operations(sequence_value)
        return CalculationInput.from_values(
            deck_count=data["deck_count"],
            deck_climax=data["deck_climax"],
            waiting_count=data["waiting_count"],
            waiting_climax=data["waiting_climax"],
            level=level,
            clock=clock,
            clock_climax=data["clock_climax"],
            operation_sequence=operations,
        )
    except KeyError as exc:
        raise InputError(f"缺少必填字段：{exc.args[0]}") from exc


def _serialize(result: Any) -> dict[str, Any]:
    def fraction(value: Any) -> dict[str, Any]:
        return {
            "numerator": value.numerator,
            "denominator": value.denominator,
            "decimal": float(value),
            "percent": f"{float(value) * 100:.6f}%",
        }

    return {
        "defeat_probability": fraction(result.defeat),
        "level_defeat_probability": fraction(result.level_defeat),
        "refresh_defeat_probability": fraction(result.refresh_defeat),
        "survival_probability": fraction(result.survival),
        "rule_version": result.rule_version,
        "model_version": result.model_version,
        "upgrade_strategy": result.upgrade_strategy,
        "assumptions": [
            "每次洗牌后按高潮/普通剩余数量精确抽取。",
            "命中后的伤害牌逐张进入时计；每张后立即检查升级。",
            result.refresh_clock_assumption,
            "等级区选择按防守方最优生存策略。",
            result.mocha_strategy,
            "摩卡查看不触发刷新；不足查看数时查看剩余全部牌。",
            result.bottom_assumption,
            "掏底已送弃牌会立即进入弃牌区并参与途中刷新；刷新洗回的牌可再次从牌底掏出。刷新点入时计就是规则要求的 1 点伤害，不额外重复结算。",
            "高潮计次掏底即使某次 z 点伤害被取消，仍继续处理剩余高潮次数。",
            "包含等级达到 4 与无法刷新两种败北。",
        ],
    }


class CalculatorHandler(BaseHTTPRequestHandler):
    server_version = "WSCalculator/1.0"

    def _send(self, status: int, payload: Any, content_type: str) -> None:
        encoded = payload if isinstance(payload, bytes) else payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API name
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(500, "页面文件不存在。", "text/plain; charset=utf-8")
            return
        if path == "/api/ws/rules":
            payload = {
                "rule_version": RULE_VERSION,
                "model_version": MODEL_VERSION,
                "max_deck_size": 50,
                "max_climaxes": 8,
                "max_mocha_look": 10,
                "max_bottom_mill": 5,
                "max_bottom_conditional_damage": 4,
                "max_bottom_per_climax_damage": MAX_DAMAGE_PER_SEGMENT,
                "max_bottom_climax_hits": 5,
                "bottom_modes": ["bottom_conditional", "bottom_per_climax"],
                "operation_types": [
                    "damage",
                    "mocha",
                    "bottom_conditional",
                    "bottom_per_climax",
                ],
                "clock_size": 7,
                "defeat_level": 4,
            }
            self._send(
                200,
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )
            return
        self._send(404, "Not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API name
        if urlparse(self.path).path != "/api/ws/lethal-calculations":
            self._send(404, b"Not found", "text/plain; charset=utf-8")
            return
        try:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise InputError("请求长度格式无效。") from exc
            if length <= 0 or length > 32_768:
                raise InputError("请求内容不能为空，且不能超过 32 KB。")
            data = json.loads(self.rfile.read(length))
            request = _request_from_json(data)
            response = _serialize(calculate(request))
        except (InputError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            message = (
                str(exc)
                if isinstance(exc, (InputError, json.JSONDecodeError))
                else "请求必须是 UTF-8 编码的 JSON。"
            )
            self._send(
                400,
                json.dumps(
                    {"error": {"code": "INVALID_INPUT", "message": message}},
                    ensure_ascii=False,
                ).encode(),
                "application/json; charset=utf-8",
            )
            return
        self._send(
            200,
            json.dumps(response, ensure_ascii=False).encode(),
            "application/json; charset=utf-8",
        )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def serve(
    host: str = "127.0.0.1", port: int = 8000, *, open_browser: bool = False
) -> None:
    server = ThreadingHTTPServer((host, port), CalculatorHandler)
    actual_host, actual_port = server.server_address[:2]
    if not isinstance(actual_host, str):
        actual_host = str(actual_host)
    url_host = f"[{actual_host}]" if ":" in actual_host else actual_host
    url = f"http://{url_host}:{actual_port}"
    if open_browser:
        browser_opened = False
        try:
            browser_opened = webbrowser.open_new_tab(url)
        except webbrowser.Error:
            pass
        print(f"WS 斩杀概率计算器运行于 {url}", flush=True)
        print(
            "浏览器已打开。" if browser_opened else "请复制上述地址到浏览器打开。",
            flush=True,
        )
        print("按 Ctrl+C 或关闭此窗口即可停止服务。", flush=True)
    else:
        print(f"WS 斩杀概率计算器运行于 {url}", flush=True)
        print("关闭此窗口即可停止服务。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n服务已停止。")
    finally:
        server.server_close()
