"""
Legacy OcrBase compatibility adapter.

Preserves the original call shape::

    OcrBase().parse(OcrSpace=[{'image': path, 'api': key}])

so existing scripts keep working. Uses the OcrRoute engine registry
instead of ``import_module('__init__')`` and sys.path mutation.
"""

from __future__ import annotations

from ocrroute.catalog.registry import get_registry
from ocrroute.engines.ocrplugin import OCRPlugin
from ocrroute.logutil import get_logger

log = get_logger(__name__)


class OcrBase:
    """
    OcrBase class (compatibility shim).
    """

    def __init__(self, *args, **kwargs):
        """
        :param args: any
        :param kwargs: any
        """
        requests = dict(kwargs)
        for p in args:
            if isinstance(p, dict):
                requests.update(p)
        self.__m_requests = requests

    def engines(self):
        """
        :return: list[str]
        """
        return [e.id for e in get_registry().list()]

    @staticmethod
    def createObject(className, **kwargs):
        """
        :param className: str
        :return: OCRPlugin instance
        """
        if className == "OCRPlugin":
            return OCRPlugin(**kwargs)
        registry = get_registry()
        return registry.create_instance(className, **kwargs)

    def parse(self, *args, **kwargs):
        """
        Cascade through requested engines; return first success.

        :return: dict (unified OCR result)
        """
        requests = dict(kwargs)
        for p in args:
            if isinstance(p, dict):
                requests.update(p)
        if not requests:
            requests = self.__m_requests
        for x in requests:
            for a in requests[x]:
                try:
                    obj = OcrBase.createObject(x, **a)
                except Exception as err:
                    log.warning("compat_create_failed", engine=x, error=str(err))
                    continue
                result = obj.parse()
                last = obj.getLastError()
                if last:
                    log.info("compat_engine_error", engine=x, error=last)
                if not obj.getLastError():
                    return result
        emptyObj = OCRPlugin()
        return emptyObj.parse()
