"""循环检测模块

基于 browser-use 的 ActionLoopDetector 设计，实现动作循环检测、页面停滞检测和失败计数，
为 Agent 提供渐进式提示以改变策略，避免陷入无限循环。
"""

from __future__ import annotations

import hashlib
import json
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class PageFingerprint:
    """页面指纹，用于判断页面状态是否发生变化"""

    url: str
    element_count: int
    text_hash: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class ActionFingerprint:
    """动作指纹，用于判断动作是否重复"""

    action_type: str
    params_hash: str
    normalized_repr: str


@dataclass
class LoopDetectorConfig:
    """循环检测器配置

    Attributes:
        window_size: 滑动窗口大小，用于动作追踪
        action_repeat_thresholds: 渐进式告警阈值元组
        page_stall_threshold: 连续相同页面状态的阈值
        max_consecutive_failures: 最大连续失败次数，超过则硬停止
    """

    window_size: int = 20
    action_repeat_thresholds: tuple[int, ...] = (5, 8, 12)
    page_stall_threshold: int = 5
    max_consecutive_failures: int = 5


# 渐进式提示消息，与 action_repeat_thresholds 一一对应
_PROGRESSIVE_HINTS: dict[int, str] = {
    5: "检测到动作重复5次，请尝试不同策略",
    8: "检测到动作重复8次，请考虑换一种定位方式或操作路径",
    12: "检测到动作重复12次，请尝试完全不同的方法或报告任务无法完成",
}


class LoopDetector:
    """循环检测器

    通过记录动作指纹和页面指纹，检测 Agent 是否陷入循环或停滞，
    并提供渐进式提示帮助 LLM 改变策略。
    """

    def __init__(self, config: Optional[LoopDetectorConfig] = None) -> None:
        self._config = config or LoopDetectorConfig()
        self._action_history: deque[ActionFingerprint] = deque(maxlen=self._config.window_size)
        self._page_history: deque[PageFingerprint] = deque(maxlen=self._config.window_size)
        self._consecutive_failures: int = 0
        self._triggered_thresholds: set[int] = set()

    # ------------------------------------------------------------------
    # 记录方法
    # ------------------------------------------------------------------

    def record_action(self, action_type: str, params: dict) -> None:
        """记录一个动作，计算其指纹并存入滑动窗口

        Args:
            action_type: 动作类型，如 "click"、"input"、"scroll" 等
            params: 动作参数字典
        """
        normalized = self.normalize_action(action_type, params)
        params_hash = self._hash_params(params)
        fingerprint = ActionFingerprint(
            action_type=action_type,
            params_hash=params_hash,
            normalized_repr=normalized,
        )
        self._action_history.append(fingerprint)

    def record_page_state(self, url: str, element_count: int, page_text: str) -> None:
        """记录页面状态指纹

        Args:
            url: 当前页面 URL
            element_count: 页面可交互元素数量
            page_text: 页面文本内容，用于计算哈希
        """
        text_hash = hashlib.md5(page_text.encode("utf-8"), usedforsecurity=False).hexdigest()
        fingerprint = PageFingerprint(
            url=url,
            element_count=element_count,
            text_hash=text_hash,
        )
        self._page_history.append(fingerprint)

    def record_failure(self) -> None:
        """记录一次步骤失败"""
        self._consecutive_failures += 1

    # ------------------------------------------------------------------
    # 检测方法
    # ------------------------------------------------------------------

    def check_action_loop(self) -> Optional[str]:
        """检测动作循环

        在滑动窗口内统计归一化动作的重复次数，若达到任一阈值则返回警告消息。

        Returns:
            若检测到循环则返回警告字符串，否则返回 None
        """
        if not self._action_history:
            return None

        # 统计最近窗口内每个归一化动作的出现次数
        counter: dict[str, int] = {}
        for fp in self._action_history:
            counter[fp.normalized_repr] = counter.get(fp.normalized_repr, 0) + 1

        max_count = max(counter.values())

        # 按阈值从高到低检查，返回最严重的告警
        for threshold in sorted(self._config.action_repeat_thresholds, reverse=True):
            if max_count >= threshold:
                action_repr = max(counter, key=counter.get)
                return (
                    f"动作循环检测: 动作「{action_repr}」已重复 {max_count} 次，"
                    f"超过阈值 {threshold}"
                )

        return None

    def check_page_stall(self) -> Optional[str]:
        """检测页面停滞

        判断最近连续相同页面状态的次数是否超过阈值。

        Returns:
            若检测到停滞则返回警告字符串，否则返回 None
        """
        if len(self._page_history) < 2:
            return None

        stall_count = 1
        latest = self._page_history[-1]

        # 从倒数第二个开始向前计数连续相同页面
        for i in range(len(self._page_history) - 2, -1, -1):
            prev = self._page_history[i]
            if prev.url == latest.url and prev.text_hash == latest.text_hash:
                stall_count += 1
            else:
                break

        if stall_count >= self._config.page_stall_threshold:
            return (
                f"页面停滞检测: 页面已连续 {stall_count} 次无变化，"
                f"超过阈值 {self._config.page_stall_threshold}"
            )

        return None

    def check_failure_limit(self) -> bool:
        """检查连续失败次数是否超过硬停止限制

        Returns:
            若超过最大连续失败次数则返回 True，否则返回 False
        """
        return self._consecutive_failures >= self._config.max_consecutive_failures

    # ------------------------------------------------------------------
    # 渐进式提示
    # ------------------------------------------------------------------

    def get_loop_hints(self) -> list[str]:
        """获取渐进式提示列表，供 LLM 参考以改变策略

        根据当前滑动窗口内动作的最大重复次数，返回所有已触达阈值对应的提示。
        每个阈值仅触发一次，避免重复提示。

        Returns:
            提示字符串列表，可能为空
        """
        if not self._action_history:
            return []

        counter: dict[str, int] = {}
        for fp in self._action_history:
            counter[fp.normalized_repr] = counter.get(fp.normalized_repr, 0) + 1

        max_count = max(counter.values())
        hints: list[str] = []

        for threshold in sorted(self._config.action_repeat_thresholds):
            if max_count >= threshold and threshold not in self._triggered_thresholds:
                hint = _PROGRESSIVE_HINTS.get(threshold)
                if hint:
                    hints.append(hint)
                    self._triggered_thresholds.add(threshold)

        return hints

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------

    def normalize_action(self, action_type: str, params: dict) -> str:
        """归一化动作表示，用于循环比较

        处理策略:
        - 对 params 的键进行排序以保证确定性
        - 对搜索/输入类动作的关键词进行排序，使不同顺序的相同关键词视为同一动作
        - 忽略点击索引等易变参数，保留语义关键参数

        Args:
            action_type: 动作类型
            params: 动作参数

        Returns:
            归一化后的动作字符串表示
        """
        normalized_params: dict = {}

        for key in sorted(params.keys()):
            value = params[key]

            # 对搜索关键词类字段进行排序归一化
            if key in ("query", "search", "keywords", "text", "value") and isinstance(value, str):
                tokens = sorted(value.strip().split())
                normalized_params[key] = " ".join(tokens)
            # 忽略易变的索引参数
            elif key in ("index", "element_index", "tab_index"):
                normalized_params[key] = "*"
            else:
                normalized_params[key] = value

        # 使用排序后的 JSON 保证确定性
        params_str = json.dumps(normalized_params, sort_keys=True, ensure_ascii=False)
        return f"{action_type}:{params_str}"

    def reset(self) -> None:
        """重置检测器状态"""
        self._action_history.clear()
        self._page_history.clear()
        self._consecutive_failures = 0
        self._triggered_thresholds.clear()

    # ------------------------------------------------------------------
    # 私有方法
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_params(params: dict) -> str:
        """计算参数字典的哈希值

        Args:
            params: 参数字典

        Returns:
            MD5 十六进制摘要
        """
        raw = json.dumps(params, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(raw.encode("utf-8"), usedforsecurity=False).hexdigest()
