"""Voxvey authentication CLI plugin for Hermes."""

from __future__ import annotations

from .cli import register_cli, voxvey_command


def register(ctx) -> None:
    ctx.register_cli_command(
        name="voxvey",
        help="Voxvey authentication helpers",
        setup_fn=register_cli,
        handler_fn=voxvey_command,
        description="Login to Voxvey using browser OAuth, device code, or API key storage.",
    )

