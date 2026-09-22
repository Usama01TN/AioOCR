"""Engine discovery, availability tracking, and option-schema introspection.

Wraps the vendored AioOCR plugin tree without rewriting engine modules.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
import re

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ocrroute.logutil import get_logger

log = get_logger(__name__)

ENGINES_ROOT = Path(__file__).resolve().parent.parent / "engines"
CATALOG_TOML = Path(__file__).resolve().parent / "engines.toml"

_INSTALL_HINTS: dict[str, str] = {
    "pytesseract": "pip install pytesseract  # plus system package tesseract-ocr",
    "easyocr": "pip install easyocr",
    "paddleocr": "pip install paddleocr paddlepaddle",
    "torch": "pip install torch transformers",
    "transformers": "pip install transformers torch",
    "keras_ocr": "pip install keras-ocr",
    "calamari_ocr": "pip install calamari-ocr",
    "rapidocr": "pip install rapidocr-onnxruntime",
    "cv2": "pip install opencv-python-headless",
    "surya": "pip install surya-ocr",
    "mmocr": "pip install mmocr",
    "doctr": "pip install python-doctr",
}

# Known plugin class names (used when a module fails to import)
_KNOWN_PLUGINS = frozenset(
    {
        "Tesseract",
        "EasyOCR",
        "OcrSpace",
        "PaddleOcr",
        "RapidOcr",
        "MmOcr",
        "TrOcr",
        "TrOcrHandwritten",
        "GotOcr",
        "SuryaOcr",
        "KerasOcr",
        "OpenOcr",
        "PytorchOcr",
        "InfinityParser",
        "ScanDocFlow",
        "Api4AiOcr",
        "RapidApiOcr",
        "NemotronOcr",
        "NvidiaPaddleOcr",
        "BaiduOcr",
        "GoogleOcr",
        "ChatGptOcr",
        "ClaudeOcr",
        "GeminiOcr",
        "GrokOcr",
        "GroqOcr",
        "MistralOcr",
        "NanonetsOcr",
        "OpenRouterOcr",
        "PerplexityOcr",
        "QwenCloudOcr",
        "SiliconFlowOcr",
        "AimlApiOcr",
        "ApiNinjasOcr",
        "EasyOcrOrg",
        "CalamariOcr",
        "ChandraOcr",
        "DeepSeekOcr",
        "DotsOcr",
        "GlmOcrHF",
        "HunyuanOcrHf",
        "MonkeyOcrHf",
        "MonkeyOcrPro",
        "NanonetsOcr2",
        "NougatLib",
        "NougatOcr",
        "OlmOcrLib",
        "QianfanOcr",
        "Qwen2Vl2bOcr",
        "QwenVlOcr",
        "UnlimitedOcr",
        "OmniRouteOcr",
    }
)

_SKIP_CLASSES = frozenset({"SourceError", "OCRError", "OCRPlugin", "InMemoryInfer", "NoMakedirs"})


@dataclass
class EngineInfo:
    """Discovered engine metadata."""

    id: str
    name: str
    kind: str  # api | local
    module: str
    cls: type | None = None
    available: bool = False
    import_error: str | None = None
    install_hint: str | None = None
    vendor: str = ""
    requires_key: bool = False
    supports_pdf: bool = False
    supports_handwriting: bool = False
    supports_tables: bool = False
    supports_overlay: bool = True
    languages: list[str] = field(default_factory=list)
    option_schema: dict[str, Any] = field(default_factory=dict)
    cost_model: str = "local"
    unit_price: float = 0.0
    homepage: str | None = None
    docs_url: str | None = None
    quality_score: float = 0.5
    key_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "module": self.module,
            "available": self.available,
            "import_error": self.import_error,
            "install_hint": self.install_hint,
            "vendor": self.vendor,
            "requires_key": self.requires_key,
            "supports_pdf": self.supports_pdf,
            "supports_handwriting": self.supports_handwriting,
            "supports_tables": self.supports_tables,
            "supports_overlay": self.supports_overlay,
            "languages": self.languages,
            "option_schema": self.option_schema,
            "cost_model": self.cost_model,
            "unit_price": self.unit_price,
            "homepage": self.homepage,
            "docs_url": self.docs_url,
            "quality_score": self.quality_score,
            "key_url": self.key_url,
        }


def _load_overlay() -> dict[str, dict[str, Any]]:
    if not CATALOG_TOML.exists():
        return {}
    with CATALOG_TOML.open("rb") as fh:
        data = tomllib.load(fh)
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _hint_from_error(err: BaseException) -> str | None:
    msg = str(err)
    m = re.search(r"No module named ['\"]([^'\"]+)['\"]", msg)
    if m:
        mod = m.group(1).split(".")[0]
        return _INSTALL_HINTS.get(mod, f"pip install {mod}")
    for key, hint in _INSTALL_HINTS.items():
        if key in msg.lower():
            return hint
    return None


def _introspect_options(cls: type) -> dict[str, Any]:
    base_reserved = {
        "endpoint",
        "image",
        "language",
        "engine",
        "online",
        "payload",
        "api",
        "apiList",
        "proxy",
        "proxyList",
        "timeout",
        "retries",
        "model",
        "prompt",
        "lastError",
        "args",
        "kwargs",
    }
    schema: dict[str, Any] = {}
    try:
        sig = inspect.signature(cls.__init__)
        for name, param in sig.parameters.items():
            if name in ("self",) or name in base_reserved:
                continue
            entry: dict[str, Any] = {"name": name}
            if param.default is not inspect.Parameter.empty:
                entry["default"] = param.default if not callable(param.default) else None
            else:
                entry["default"] = None
            entry["type"] = "any"
            schema[name] = entry
    except (TypeError, ValueError):
        pass

    try:
        src = inspect.getsource(cls.__init__)
        for match in re.finditer(r"kwargs\.pop\(\s*['\"](\w+)['\"]", src):
            key = match.group(1)
            if key not in base_reserved and key not in schema:
                schema[key] = {"name": key, "default": None, "type": "any"}
    except (OSError, TypeError):
        pass

    doc = inspect.getdoc(cls.__init__) or inspect.getdoc(cls) or ""
    for match in re.finditer(r":param\s+(\w+):\s*(.+)", doc):
        key, desc = match.group(1), match.group(2).strip()
        if key in base_reserved:
            continue
        schema.setdefault(key, {"name": key, "default": None, "type": "any"})
        schema[key]["description"] = desc
    return schema


def _class_names_from_source(src: Path) -> list[str]:
    if not src.exists():
        return []
    text = src.read_text(encoding="utf-8", errors="replace")
    names = re.findall(r"^class\s+(\w+)\s*\(", text, re.M)
    out: list[str] = []
    for c in names:
        if c.startswith("_") or c in _SKIP_CLASSES:
            continue
        if "Error" in c and c not in _KNOWN_PLUGINS:
            continue
        if (
            c in _KNOWN_PLUGINS
            or c.endswith("Ocr")
            or c.endswith("OCR")
            or c in ("Tesseract", "InfinityParser", "ScanDocFlow")
        ):
            out.append(c)
    return out


class EngineRegistry:
    """Discover and cache OCRPlugin subclasses from the vendored tree."""

    def __init__(self) -> None:
        self._engines: dict[str, EngineInfo] = {}
        self._overlay = _load_overlay()
        self._discovered = False

    @property
    def engines(self) -> dict[str, EngineInfo]:
        if not self._discovered:
            self.discover()
        return self._engines

    def discover(self, force: bool = False) -> dict[str, EngineInfo]:
        if self._discovered and not force:
            return self._engines
        self._engines = {}
        self._overlay = _load_overlay()

        # Bootstrap dual-import path for engine modules
        try:
            import ocrroute.engines  # noqa: F401
        except Exception as exc:
            log.error("engines_pkg_import_failed", error=str(exc))

        try:
            from ocrroute.engines.ocrplugin import OCRPlugin
        except Exception as exc:
            log.error("ocrplugin_import_failed", error=str(exc))
            self._discovered = True
            return self._engines

        for sub in ("api", "local"):
            package_path = ENGINES_ROOT / sub
            if not package_path.is_dir():
                continue
            for modinfo in pkgutil.iter_modules([str(package_path)]):
                if modinfo.ispkg or modinfo.name.startswith("_"):
                    continue
                full_name = f"ocrroute.engines.{sub}.{modinfo.name}"
                self._load_module(full_name, sub, OCRPlugin)

        self._discovered = True
        log.info(
            "engines_discovered",
            count=len(self._engines),
            available=sum(1 for e in self._engines.values() if e.available),
        )
        return self._engines

    def _load_module(self, full_name: str, kind: str, base_cls: type) -> None:
        src = ENGINES_ROOT / kind / f"{full_name.rsplit('.', 1)[-1]}.py"
        try:
            # Clear stale failed modules so force-refresh can recover
            if full_name in list(__import__("sys").modules):
                # allow re-import only when previously failed; keep success cache
                pass
            module = importlib.import_module(full_name)
        except Exception as exc:
            import_error = f"{type(exc).__name__}: {exc}"
            self._record_failed_module(full_name, kind, import_error, exc, src)
            return

        found = False
        for name, obj in inspect.getmembers(module, inspect.isclass):
            try:
                if not issubclass(obj, base_cls) or obj is base_cls:
                    continue
            except TypeError:
                continue
            if obj.__module__ != module.__name__:
                continue
            self._register(name, obj, kind, full_name, available=True, import_error=None)
            found = True
        if not found:
            # Module imported but no plugin class (unusual) — still seed from source
            for name in _class_names_from_source(src):
                if name not in self._engines:
                    self._register(
                        name,
                        None,
                        kind,
                        full_name,
                        available=False,
                        import_error="No OCRPlugin subclass found in module",
                    )

    def _record_failed_module(
        self,
        full_name: str,
        kind: str,
        import_error: str,
        exc: BaseException,
        src: Path | None = None,
    ) -> None:
        if src is None:
            parts = full_name.split(".")
            src = Path(__file__).resolve().parent.parent.joinpath(*parts[1:]).with_suffix(".py")
        class_names = _class_names_from_source(src)
        if not class_names:
            mod = full_name.rsplit(".", 1)[-1]
            class_names = ["".join(p.title() for p in mod.replace("_", " ").split())]

        hint = _hint_from_error(exc)
        for name in class_names:
            self._register(
                name,
                None,
                kind,
                full_name,
                available=False,
                import_error=import_error,
                install_hint=hint,
            )

    def _register(
        self,
        name: str,
        cls: type | None,
        kind: str,
        module: str,
        *,
        available: bool,
        import_error: str | None,
        install_hint: str | None = None,
    ) -> None:
        # Prefer an already-available registration over a failed one
        existing = self._engines.get(name)
        if existing and existing.available and not available:
            return

        overlay = self._overlay.get(name, {})
        info = EngineInfo(
            id=name,
            name=str(overlay.get("name", name)),
            kind=str(overlay.get("kind", kind)),
            module=module,
            cls=cls,
            available=available,
            import_error=import_error,
            install_hint=install_hint or overlay.get("install_hint"),
            vendor=str(overlay.get("vendor", "")),
            requires_key=bool(overlay.get("requires_key", kind == "api")),
            supports_pdf=bool(overlay.get("supports_pdf", False)),
            supports_handwriting=bool(overlay.get("supports_handwriting", False)),
            supports_tables=bool(overlay.get("supports_tables", False)),
            supports_overlay=bool(overlay.get("supports_overlay", True)),
            languages=list(overlay.get("languages") or []),
            cost_model=str(
                overlay.get("cost_model", "local" if kind == "local" else "per_request")
            ),
            unit_price=float(overlay.get("unit_price", 0.0)),
            homepage=overlay.get("homepage"),
            docs_url=overlay.get("docs_url"),
            quality_score=float(overlay.get("quality_score", 0.5)),
            key_url=overlay.get("key_url"),
        )
        if cls is not None:
            info.option_schema = _introspect_options(cls)
            if not info.install_hint and not available:
                info.install_hint = _INSTALL_HINTS.get(name.lower())
        self._engines[name] = info

    def get(self, engine_id: str) -> EngineInfo | None:
        return self.engines.get(engine_id)

    def list(
        self,
        *,
        kind: str | None = None,
        available: bool | None = None,
    ) -> list[EngineInfo]:
        items = list(self.engines.values())
        if kind:
            items = [e for e in items if e.kind == kind]
        if available is not None:
            items = [e for e in items if e.available is available]
        return sorted(items, key=lambda e: (e.kind, e.name.lower()))

    def create_instance(self, engine_id: str, **kwargs: Any) -> Any:
        info = self.get(engine_id)
        if info is None:
            raise KeyError(f"Unknown engine: {engine_id}")
        if not info.available or info.cls is None:
            raise ImportError(info.import_error or f"Engine {engine_id} is not available")
        return info.cls(**kwargs)


_registry: EngineRegistry | None = None


def get_registry() -> EngineRegistry:
    global _registry
    if _registry is None:
        _registry = EngineRegistry()
    return _registry


def reset_registry() -> None:
    global _registry
    _registry = None
