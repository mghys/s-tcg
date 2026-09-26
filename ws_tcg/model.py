"""Input and result models for the WS calculator."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Iterable


RULE_VERSION = "local-ws-rule-v1"
MODEL_VERSION = "exact-state-propagation-v5"
MAX_DECK_SIZE = 50
MAX_CLIMAXES = 8
MAX_DAMAGE_SEGMENTS = 50
MAX_DAMAGE_PER_SEGMENT = 50
MAX_OPERATIONS = 50
MAX_MOCHA_LOOK = 10
MAX_BOTTOM_MILL = 5
MAX_BOTTOM_CONDITIONAL_DAMAGE = 4


class InputError(ValueError):
    """Raised when a calculation request is inconsistent or out of range."""


@dataclass(frozen=True, slots=True)
class Damage:
    points: int


@dataclass(frozen=True, slots=True)
class Mocha:
    look: int


@dataclass(frozen=True, slots=True)
class BottomConditional:
    mill: int
    damage: int


@dataclass(frozen=True, slots=True)
class BottomPerClimax:
    mill: int
    damage: int


Operation = Damage | Mocha | BottomConditional | BottomPerClimax


@dataclass(frozen=True, slots=True)
class CalculationInput:
    deck_count: int
    deck_climax: int
    waiting_count: int
    waiting_climax: int
    level: int
    clock: int
    clock_climax: int
    damage_sequence: tuple[int, ...]
    operation_sequence: tuple[Operation, ...] | None = None

    def __post_init__(self) -> None:
        integer_fields = {
            "deck_count": self.deck_count,
            "deck_climax": self.deck_climax,
            "waiting_count": self.waiting_count,
            "waiting_climax": self.waiting_climax,
            "level": self.level,
            "clock": self.clock,
            "clock_climax": self.clock_climax,
        }
        for name, value in integer_fields.items():
            if isinstance(value, bool) or not isinstance(value, int):
                raise InputError(f"{name} 必须是整数。")
        if any(value < 0 for value in integer_fields.values()):
            raise InputError("区域数量和等级不能为负数。")
        if self.deck_count > MAX_DECK_SIZE or self.waiting_count > MAX_DECK_SIZE:
            raise InputError("牌库和弃牌区数量不能超过 50。")
        if self.deck_climax > self.deck_count:
            raise InputError("牌库高潮数不能超过牌库总数。")
        if self.waiting_climax > self.waiting_count:
            raise InputError("弃牌区高潮数不能超过弃牌区总数。")
        if self.clock > 6:
            raise InputError("当前时计必须为 0–6；达到 7 张的状态应先完成升级。")
        if self.clock_climax > self.clock:
            raise InputError("时计高潮数不能超过时计总数。")
        if self.level > MAX_DECK_SIZE:
            raise InputError("等级区数量不能超过 50。")
        if (
            self.deck_count + self.waiting_count + self.clock + self.level
            > MAX_DECK_SIZE
        ):
            raise InputError("牌库、弃牌区、时计和等级的已知卡牌总数不能超过 50。")
        if self.deck_climax + self.waiting_climax + self.clock_climax > MAX_CLIMAXES:
            raise InputError("已输入区域中的高潮总数不能超过标准构筑上限 8。")
        if not isinstance(self.damage_sequence, tuple):
            raise InputError("damage_sequence 必须是整数元组。")
        if self.operation_sequence is None:
            if not self.damage_sequence:
                raise InputError("操作序列不能为空。")
            operations: tuple[Operation, ...] = tuple(
                Damage(damage) for damage in self.damage_sequence
            )
            object.__setattr__(self, "operation_sequence", operations)
        else:
            if not isinstance(self.operation_sequence, tuple):
                raise InputError("operation_sequence 必须是操作元组。")
            if not self.operation_sequence:
                raise InputError("操作序列不能为空。")
            if self.damage_sequence:
                raise InputError("damage_sequence 与 operation_sequence 不能同时提供。")
        assert self.operation_sequence is not None
        if len(self.operation_sequence) > MAX_OPERATIONS:
            raise InputError(f"操作数不能超过 {MAX_OPERATIONS}。")
        damage_count = 0
        for index, operation in enumerate(self.operation_sequence, start=1):
            if isinstance(operation, Damage):
                damage_count += 1
                value = operation.points
                if isinstance(value, bool) or not isinstance(value, int):
                    raise InputError(f"第 {index} 个操作的伤害必须是整数。")
                if not 1 <= value <= MAX_DAMAGE_PER_SEGMENT:
                    raise InputError(
                        f"第 {index} 个操作的伤害必须在 1–{MAX_DAMAGE_PER_SEGMENT} 之间。"
                    )
            elif isinstance(operation, Mocha):
                value = operation.look
                if isinstance(value, bool) or not isinstance(value, int):
                    raise InputError(f"第 {index} 个摩卡的查看数必须是整数。")
                if not 1 <= value <= MAX_MOCHA_LOOK:
                    raise InputError(f"摩卡查看数必须在 1–{MAX_MOCHA_LOOK} 之间。")
            elif isinstance(operation, BottomConditional):
                if isinstance(operation.mill, bool) or not isinstance(
                    operation.mill, int
                ):
                    raise InputError(f"第 {index} 个掏底的张数必须是整数。")
                if not 1 <= operation.mill <= MAX_BOTTOM_MILL:
                    raise InputError(f"掏底张数必须在 1–{MAX_BOTTOM_MILL} 之间。")
                if isinstance(operation.damage, bool) or not isinstance(
                    operation.damage, int
                ):
                    raise InputError(f"第 {index} 个掏底伤害必须是整数。")
                if not 1 <= operation.damage <= MAX_BOTTOM_CONDITIONAL_DAMAGE:
                    raise InputError(
                        f"条件掏底伤害必须在 1–{MAX_BOTTOM_CONDITIONAL_DAMAGE} 之间。"
                    )
            elif isinstance(operation, BottomPerClimax):
                if isinstance(operation.mill, bool) or not isinstance(
                    operation.mill, int
                ):
                    raise InputError(f"第 {index} 个掏底的张数必须是整数。")
                if not 1 <= operation.mill <= MAX_BOTTOM_MILL:
                    raise InputError(f"掏底张数必须在 1–{MAX_BOTTOM_MILL} 之间。")
                if isinstance(operation.damage, bool) or not isinstance(
                    operation.damage, int
                ):
                    raise InputError(f"第 {index} 个掏底的每次伤害必须是整数。")
                if not 1 <= operation.damage <= MAX_DAMAGE_PER_SEGMENT:
                    raise InputError(
                        f"掏底每次伤害必须在 1–{MAX_DAMAGE_PER_SEGMENT} 之间。"
                    )
            else:
                raise InputError(f"第 {index} 个操作类型无效。")
        if damage_count > MAX_DAMAGE_SEGMENTS:
            raise InputError(f"伤害段数不能超过 {MAX_DAMAGE_SEGMENTS}。")

    @classmethod
    def from_values(
        cls,
        *,
        deck_count: int,
        deck_climax: int,
        waiting_count: int,
        waiting_climax: int,
        level: int,
        clock: int,
        clock_climax: int,
        damage_sequence: Iterable[int] = (),
        operation_sequence: Iterable[Operation] | None = None,
    ) -> "CalculationInput":
        operations = (
            tuple(operation_sequence) if operation_sequence is not None else None
        )
        return cls(
            deck_count=deck_count,
            deck_climax=deck_climax,
            waiting_count=waiting_count,
            waiting_climax=waiting_climax,
            level=level,
            clock=clock,
            clock_climax=clock_climax,
            damage_sequence=tuple(damage_sequence),
            operation_sequence=operations,
        )

    @property
    def operations(self) -> tuple[Operation, ...]:
        assert self.operation_sequence is not None
        return self.operation_sequence


@dataclass(frozen=True, slots=True)
class CalculationResult:
    level_defeat: Fraction
    refresh_defeat: Fraction
    survival: Fraction
    rule_version: str = RULE_VERSION
    model_version: str = MODEL_VERSION
    upgrade_strategy: str = "防守方最优生存"
    refresh_clock_assumption: str = "刷新点入时计后立即检查升级，再继续当前伤害"
    mocha_strategy: str = (
        "进攻方看牌后选择 0 至 x 张送入弃牌区并安排剩余牌顶顺序，以最大化败北概率"
    )
    bottom_assumption: str = "掏底遇到空牌库时正常刷新，刷新点放入时计作为规则要求的 1 点伤害（不额外重复结算），随后继续掏底；高潮计次模式每张掏出的高潮造成一次伤害，触发次数不超过掏底张数（最多 5 次）"

    @property
    def defeat(self) -> Fraction:
        return self.level_defeat + self.refresh_defeat

    def __post_init__(self) -> None:
        if self.level_defeat + self.refresh_defeat + self.survival != 1:
            raise ValueError("结果概率质量不守恒。")
