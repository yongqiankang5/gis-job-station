"""招聘平台抓取器抽象接口与占位实现。"""

from abc import ABC, abstractmethod
from typing import Any


class BaseScraper(ABC):
    """所有招聘来源抓取器应实现的统一接口。"""

    source: str

    @abstractmethod
    async def fetch(self, keyword: str, city: str) -> list[dict[str, Any]]:
        """抓取指定关键词和城市的岗位原始数据。"""

        raise NotImplementedError


class PlaceholderScraper(BaseScraper):
    """用于开发阶段的空抓取器，后续可替换为真实来源实现。"""

    source = "manual"

    async def fetch(self, keyword: str, city: str) -> list[dict[str, Any]]:
        """返回空数据，明确保留真实抓取逻辑的扩展点。"""

        _ = keyword, city
        return []

