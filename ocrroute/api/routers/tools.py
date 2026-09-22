"""Tools API — reserved empty scaffold (§12)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ocrroute.errors import ErrorCode
from ocrroute.tools.registry import get_tool_registry

router = APIRouter(prefix="/tools", tags=["tools"])


@router.get("")
async def list_tools() -> dict[str, Any]:
    """Reserved for future use. Always returns an empty tools list."""
    tools = get_tool_registry().list()
    return {
        "tools": [t.to_dict() for t in tools],
        "reserved": True,
        "message": "No tools are installed. This section is reserved for future post-processing extensions. See docs/TOOLS.md.",
    }


@router.get("/{tool_id}")
async def get_tool(tool_id: str) -> dict[str, Any]:
    raise HTTPException(
        status_code=404,
        detail={
            "error_code": ErrorCode.NOT_FOUND.value,
            "error_message": f"Tool '{tool_id}' not found. Tools are reserved for future use.",
        },
    )


@router.post("/{tool_id}/run")
async def run_tool(tool_id: str) -> dict[str, Any]:
    raise HTTPException(
        status_code=501,
        detail={
            "error_code": ErrorCode.TOOLS_RESERVED.value,
            "error_message": (
                f"Tools are reserved for future use; '{tool_id}' cannot be run. "
                "See docs/TOOLS.md."
            ),
        },
    )
