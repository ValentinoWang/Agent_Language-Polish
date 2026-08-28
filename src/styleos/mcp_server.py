from __future__ import annotations

from typing import Any

from .models import FeedbackRecord
from .service import StyleOSPaths, StyleOSService


def create_server(service: StyleOSService | None = None) -> Any:
    try:
        from mcp.server.mcpserver import MCPServer
    except ImportError as exc:
        try:
            from mcp.server.fastmcp import FastMCP as MCPServer
        except ImportError:
            raise RuntimeError(
                "Install StyleOS with the MCP extra: uv tool install '.[mcp]'"
            ) from exc

    runtime = service or StyleOSService(StyleOSPaths.resolve())
    server = MCPServer("StyleOS")

    @server.tool()
    def style_distill(
        texts: list[str], profile_id: str, track: str, channel: str, audience: str
    ) -> dict[str, object]:
        card, path = runtime.distill(
            texts,
            profile_id=profile_id,
            track=track,
            channel=channel,
            audience=audience,
        )
        return {"card": card.model_dump(mode="json"), "path": str(path)}

    @server.tool()
    def style_rewrite(
        source_text: str,
        pack: str,
        mode: str = "balanced",
        provider: str = "offline",
        profile: str | None = None,
    ) -> dict[str, object]:
        report, run_dir = runtime.rewrite(
            source_text, pack=pack, mode=mode, provider=provider, profile=profile
        )
        return {"audit": report.model_dump(mode="json"), "run_dir": str(run_dir)}

    @server.tool()
    def style_profile_get(profile_id: str) -> dict[str, object]:
        return runtime.profiles.effective(profile_id).model_dump(mode="json")

    @server.tool()
    def style_feedback(
        run_id: str,
        pack: str,
        decision: str,
        edited_text: str | None = None,
        reason: str | None = None,
        source_id: str | None = None,
    ) -> dict[str, object]:
        record = FeedbackRecord(
            run_id=run_id,
            pack=pack,
            decision=decision,
            edited_text=edited_text,
            reason=reason,
            source_id=source_id,
        )
        runtime.record_feedback(record)
        return {"recorded": True, "run_id": run_id}

    return server


def main() -> None:
    create_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()
