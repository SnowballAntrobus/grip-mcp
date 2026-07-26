"""MCP wiring (stdio) over the transport-independent service (DESIGN §6).

Thin by design: every tool delegates to GripService and returns its
envelope dict verbatim; descriptions and the server-level instructions
come from the versioned descriptions module (§6.3)."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import descriptions as D
from .service import GripService


def build_server(root=None) -> FastMCP:
    svc = GripService(root)
    mcp = FastMCP("grip-mcp", instructions=D.SERVER_INSTRUCTIONS)

    def tool(name):
        return mcp.tool(name=name, description=D.TOOL_DESCRIPTIONS[name])

    @tool("list_projects")
    def list_projects() -> dict:
        return svc.list_projects()

    @tool("set_project")
    def set_project(name: str, create: bool = False) -> dict:
        return svc.set_project(name, create)

    @tool("update_project_defaults")
    def update_project_defaults(default_tuning: str) -> dict:
        return svc.update_project_defaults(default_tuning)

    @tool("describe_workspace")
    def describe_workspace() -> dict:
        return svc.describe_workspace()

    @tool("identify")
    def identify(strings: list[int | None], tuning: str | None = None,
                 context_key: str | None = None, render: bool = False,
                 labels: str = "notes", interval_root: str = "auto",
                 theme: str = "light", orientation: str = "chart") -> dict:
        return svc.identify(strings, tuning, context_key, render, labels,
                            interval_root, theme, orientation)

    @tool("add_grip")
    def add_grip(id: str, strings: list[int | None],
                 tuning: str | None = None,
                 fingers: list[int | None] | None = None,
                 label: str | None = None, tags: list[str] | None = None,
                 chosen: str | None = None, render: bool = True) -> dict:
        return svc.add_grip(id, strings, tuning, fingers, label, tags,
                            chosen, render)

    @tool("get_grip")
    def get_grip(id: str) -> dict:
        return svc.get_grip(id)

    @tool("list_grips")
    def list_grips() -> dict:
        return svc.list_grips()

    @tool("update_grip")
    def update_grip(id: str, patch: dict) -> dict:
        return svc.update_grip(id, patch)

    @tool("rename_grip")
    def rename_grip(id: str, new_id: str) -> dict:
        return svc.rename_grip(id, new_id)

    @tool("remove_grip")
    def remove_grip(id: str, force: bool = False) -> dict:
        return svc.remove_grip(id, force)

    @tool("set_reading")
    def set_reading(id: str, chosen: str) -> dict:
        return svc.set_reading(id, chosen)

    @tool("transpose")
    def transpose(semitones: int, id: str | None = None,
                  strings: list[int | None] | None = None,
                  tuning: str | None = None, save_as: str | None = None,
                  render: bool = False) -> dict:
        return svc.transpose(semitones, id, strings, tuning, save_as, render)

    @tool("set_sequence")
    def set_sequence(name: str, grips: list[str]) -> dict:
        return svc.set_sequence(name, grips)

    @tool("list_sequences")
    def list_sequences() -> dict:
        return svc.list_sequences()

    @tool("remove_sequence")
    def remove_sequence(name: str) -> dict:
        return svc.remove_sequence(name)

    @tool("render")
    def render(ids: list[str] | None = None, sequence: str | None = None,
               labels: str = "notes", interval_root: str = "auto",
               orientation: str = "chart", theme: str = "light",
               columns: int | None = None, title: str | None = None) -> dict:
        return svc.render(ids, sequence, labels, interval_root, orientation,
                          theme, columns, title)

    @tool("define_tuning")
    def define_tuning(name: str, pitches: list[str] | None = None,
                      from_: str | None = None,
                      capo: int | None = None) -> dict:
        return svc.define_tuning(name, pitches, from_, capo)

    @tool("remove_tuning")
    def remove_tuning(name: str) -> dict:
        return svc.remove_tuning(name)

    return mcp


def main() -> int:
    build_server().run()
    return 0
