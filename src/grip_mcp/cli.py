"""Entry point: the grip-mcp stdio server."""


def main() -> int:
    from .server import main as server_main
    return server_main()


if __name__ == "__main__":
    raise SystemExit(main())
