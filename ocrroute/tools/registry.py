"""Tool auto-discovery — scans builtin/ and returns [] today."""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ocrroute.tools.base import ToolPlugin

BUILTIN_PATH = Path(__file__).resolve().parent / "builtin"


@dataclass
class ToolInfo:
    id: str
    name: str
    version: str
    description: str
    cls: type | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolInfo] = {}
        self._discovered = False

    def discover(self, force: bool = False) -> dict[str, ToolInfo]:
        if self._discovered and not force:
            return self._tools
        self._tools = {}
        if not BUILTIN_PATH.is_dir():
            self._discovered = True
            return self._tools
        for modinfo in pkgutil.iter_modules([str(BUILTIN_PATH)]):
            if modinfo.ispkg or modinfo.name.startswith("_"):
                continue
            full = f"ocrroute.tools.builtin.{modinfo.name}"
            try:
                module = importlib.import_module(full)
            except Exception:
                continue
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if not issubclass(obj, ToolPlugin) or obj is ToolPlugin:
                    continue
                if obj.__module__ != module.__name__:
                    continue
                self._tools[obj.name or name] = ToolInfo(
                    id=obj.name or name,
                    name=getattr(obj, "name", name),
                    version=getattr(obj, "version", "0.0.0"),
                    description=getattr(obj, "description", ""),
                    cls=obj,
                )
        self._discovered = True
        return self._tools

    def list(self) -> list[ToolInfo]:
        return list(self.discover().values())


_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry
