# coding=utf-8
"""
ToolPlugin: abstract base for future post-processing extensions.

Mirrors the OCRPlugin philosophy so a later feature can be added without
touching the gateway. No concrete subclass is provided in this release.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ToolPlugin(ABC):
    """
    Abstract post-processing tool.

    Class attributes:
      name, version, description, input_kinds, output_kinds, option_schema
    """

    name: str = "ToolPlugin"
    version: str = "0.0.0"
    description: str = ""
    input_kinds: list[str] = []
    output_kinds: list[str] = []
    option_schema: dict[str, Any] = {}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.__m_lastError = kwargs.pop("lastError", "")

    @abstractmethod
    def run(self, run_result: dict, **options: Any) -> dict:
        """
        Transform a unified OCR result (or envelope).

        :param run_result: dict
        :return: dict
        """
        raise NotImplementedError

    def getLastError(self) -> str:
        return self.__m_lastError

    def setLastError(self, error: str) -> None:
        self.__m_lastError = error

    lastError = property(fget=getLastError, fset=setLastError)
