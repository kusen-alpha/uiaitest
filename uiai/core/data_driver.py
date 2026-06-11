"""数据驱动 - CSV/JSON/YAML参数化测试"""
from __future__ import annotations
import csv
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

logger = logging.getLogger(__name__)


@dataclass
class DataVariant:
    """数据变体"""
    name: str
    data: dict[str, Any]
    tags: list[str] = field(default_factory=list)


class DataDriver:
    """数据驱动引擎

    支持从CSV/JSON/YAML文件加载测试数据，
    生成参数化测试变体。
    """

    @staticmethod
    def from_csv(path: str | Path, name_field: str = "name", tags_field: str = "tags") -> list[DataVariant]:
        """从CSV文件加载测试数据"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")

        variants = []
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                name = row.pop(name_field, f"variant_{i}")
                tags_str = row.pop(tags_field, "")
                tags = [t.strip() for t in tags_str.split(",") if t.strip()] if tags_str else []
                # 尝试类型转换
                converted = {}
                for k, v in row.items():
                    converted[k] = DataDriver._convert_type(v)
                variants.append(DataVariant(name=name, data=converted, tags=tags))

        logger.info(f"Loaded {len(variants)} variants from CSV: {path}")
        return variants

    @staticmethod
    def from_json(path: str | Path) -> list[DataVariant]:
        """从JSON文件加载测试数据"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"JSON file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            variants = []
            for i, item in enumerate(data):
                name = item.pop("name", f"variant_{i}")
                tags = item.pop("tags", [])
                variants.append(DataVariant(name=name, data=item, tags=tags))
            return variants
        elif isinstance(data, dict):
            if "variants" in data:
                variants = []
                for i, item in enumerate(data["variants"]):
                    name = item.pop("name", f"variant_{i}")
                    tags = item.pop("tags", [])
                    variants.append(DataVariant(name=name, data=item, tags=tags))
                return variants
            else:
                name = data.pop("name", "default")
                tags = data.pop("tags", [])
                return [DataVariant(name=name, data=data, tags=tags)]
        else:
            raise ValueError(f"Unsupported JSON structure in {path}")

    @staticmethod
    def from_yaml(path: str | Path) -> list[DataVariant]:
        """从YAML文件加载测试数据"""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"YAML file not found: {path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if isinstance(data, list):
            variants = []
            for i, item in enumerate(data):
                if isinstance(item, dict):
                    name = item.pop("name", f"variant_{i}")
                    tags = item.pop("tags", [])
                    variants.append(DataVariant(name=name, data=item, tags=tags))
            return variants
        elif isinstance(data, dict):
            if "variants" in data:
                variants = []
                for i, item in enumerate(data["variants"]):
                    name = item.pop("name", f"variant_{i}")
                    tags = item.pop("tags", [])
                    variants.append(DataVariant(name=name, data=item, tags=tags))
                return variants
            else:
                name = data.pop("name", "default")
                tags = data.pop("tags", [])
                return [DataVariant(name=name, data=data, tags=tags)]
        return []

    @staticmethod
    def from_dict(data: dict[str, list[Any]]) -> list[DataVariant]:
        """从字典生成笛卡尔积变体

        Example:
            DataDriver.from_dict({
                "browser": ["chromium", "firefox"],
                "viewport": ["mobile", "desktop"],
            })
            # 生成 2x2 = 4 个变体
        """
        import itertools
        keys = list(data.keys())
        values = list(data.values())
        variants = []
        for i, combo in enumerate(itertools.product(*values)):
            variant_data = dict(zip(keys, combo))
            name = "_".join(f"{k}_{v}" for k, v in variant_data.items())
            variants.append(DataVariant(name=name, data=variant_data))
        return variants

    @staticmethod
    def _convert_type(value: str) -> Any:
        """尝试将字符串转为合适的类型"""
        if value.lower() in ("true", "yes"):
            return True
        if value.lower() in ("false", "no"):
            return False
        if value.lower() in ("null", "none", ""):
            return None
        try:
            return int(value)
        except ValueError:
            pass
        try:
            return float(value)
        except ValueError:
            pass
        return value
