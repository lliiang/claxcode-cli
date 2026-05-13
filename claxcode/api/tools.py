"""Tool listing and invocation API."""

from fastapi import APIRouter

from claxcode.models.tool import ToolInfo, ToolInvokeRequest, ToolInvokeResponse
from claxcode.tools.registry import registry

router = APIRouter()


@router.get("", response_model=list[ToolInfo])
async def list_tools():
    return [
        ToolInfo(
            name=tool.name,
            description=tool.description,
            input_schema=tool.input_schema,
            category=tool.category,
            required_permissions=tool.required_permissions,
        )
        for tool in registry.list_tools()
    ]


@router.post("/invoke", response_model=ToolInvokeResponse)
async def invoke_tool(request: ToolInvokeRequest):
    tool = registry.get(request.name)
    if tool is None:
        return ToolInvokeResponse(
            name=request.name,
            output=f"工具 '{request.name}' 不存在",
            error=True,
        )
    try:
        output = await tool.execute(**request.arguments)
        return ToolInvokeResponse(name=tool.name, output=str(output))
    except Exception as exc:
        return ToolInvokeResponse(name=tool.name, output=str(exc), error=True)
