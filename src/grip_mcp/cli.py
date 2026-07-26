"""Entry point stub. The V1 MCP server replaces this after the table freeze."""

import sys


def main() -> int:
    sys.stderr.write(
        "grip-mcp: Milestone 0 (quality-table freeze) — the V1 MCP server is "
        "not implemented yet. See docs/DESIGN.md §13.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
