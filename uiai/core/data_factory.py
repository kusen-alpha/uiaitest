"""测试数据工厂 - 数据生成+隔离+清理"""
from __future__ import annotations
import json
import logging
import random
import string
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class DataFactory:
    """测试数据工厂

    功能：
    1. 随机数据生成（姓名/邮箱/手机号/地址等）
    2. 数据隔离（每个测试用独立数据空间）
    3. 数据清理（测试后自动清理）
    4. 数据快照（保存/恢复数据状态）
    """

    def __init__(self, snapshot_dir: str = "./data_snapshots"):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self._created_data: dict[str, list[dict]] = {}  # test_id -> created records

    # --- 随机数据生成 ---

    @staticmethod
    def random_string(length: int = 8, prefix: str = "") -> str:
        chars = string.ascii_lowercase + string.digits
        return prefix + "".join(random.choices(chars, k=length))

    @staticmethod
    def random_email(domain: str = "test.com") -> str:
        name = "".join(random.choices(string.ascii_lowercase, k=8))
        return f"{name}@{domain}"

    @staticmethod
    def random_phone(country: str = "cn") -> str:
        if country == "cn":
            prefixes = ["130", "131", "132", "133", "135", "136", "137", "138", "139",
                        "150", "151", "152", "155", "156", "157", "158", "159",
                        "170", "176", "177", "178", "180", "181", "182", "183", "185", "186", "187", "188", "189"]
            prefix = random.choice(prefixes)
            suffix = "".join(random.choices(string.digits, k=8))
            return prefix + suffix
        return "".join(random.choices(string.digits, k=10))

    @staticmethod
    def random_name(locale: str = "zh") -> str:
        if locale == "zh":
            surnames = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜"
            given_names = "伟芳娜秀英敏静丽强磊军洋勇艳杰娟涛超明华丹巧辉力梅鑫桂英玲"
            return random.choice(surnames) + "".join(random.choices(given_names, k=random.randint(1, 2)))
        first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
        return f"{random.choice(first_names)} {random.choice(last_names)}"

    @staticmethod
    def random_int(min_val: int = 0, max_val: int = 100) -> int:
        return random.randint(min_val, max_val)

    @staticmethod
    def random_float(min_val: float = 0.0, max_val: float = 100.0, decimals: int = 2) -> float:
        return round(random.uniform(min_val, max_val), decimals)

    @staticmethod
    def random_date(start_days_ago: int = 30, end_days_ago: int = 0) -> str:
        days = random.randint(start_days_ago, end_days_ago)
        date = datetime.now() - timedelta(days=days)
        return date.strftime("%Y-%m-%d")

    @staticmethod
    def random_choice(choices: list) -> Any:
        return random.choice(choices)

    @staticmethod
    def random_bool(true_probability: float = 0.5) -> bool:
        return random.random() < true_probability

    def generate_user(self, locale: str = "zh", **overrides) -> dict:
        """生成用户数据"""
        data = {
            "name": self.random_name(locale),
            "email": self.random_email(),
            "phone": self.random_phone("cn" if locale == "zh" else "us"),
            "age": self.random_int(18, 65),
            "gender": self.random_choice(["male", "female"]),
        }
        data.update(overrides)
        return data

    def generate_product(self, **overrides) -> dict:
        """生成商品数据"""
        categories = ["电子产品", "服装", "食品", "家居", "图书", "运动"]
        data = {
            "name": f"测试商品_{self.random_string(6)}",
            "price": self.random_float(10, 9999),
            "category": self.random_choice(categories),
            "stock": self.random_int(0, 1000),
            "description": f"这是一个测试商品，编号{self.random_string(8)}",
        }
        data.update(overrides)
        return data

    # --- 数据隔离 ---

    def begin_test(self, test_id: str) -> None:
        """开始测试，创建数据空间"""
        self._created_data[test_id] = []

    def record_created(self, test_id: str, resource_type: str, resource_id: str, data: dict | None = None) -> None:
        """记录创建的数据"""
        if test_id not in self._created_data:
            self.begin_test(test_id)
        self._created_data[test_id].append({
            "type": resource_type,
            "id": resource_id,
            "data": data,
            "created_at": datetime.now().isoformat(),
        })

    def end_test(self, test_id: str, cleanup: bool = True) -> list[dict]:
        """结束测试，返回创建的数据"""
        data = self._created_data.pop(test_id, [])
        if cleanup:
            logger.info(f"Test {test_id} created {len(data)} data records (cleanup={cleanup})")
        return data

    # --- 数据快照 ---

    def save_snapshot(self, test_id: str, data: Any, name: str = "default") -> str:
        """保存数据快照"""
        path = self.snapshot_dir / test_id / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(path)

    def load_snapshot(self, test_id: str, name: str = "default") -> Any:
        """加载数据快照"""
        path = self.snapshot_dir / test_id / f"{name}.json"
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None
