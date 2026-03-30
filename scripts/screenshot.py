#!/usr/bin/env python3
"""Capture a startup screenshot of TINA and save it as docs/screenshot.svg."""

import asyncio
from pathlib import Path
from unittest.mock import patch

OUTPUT = Path("docs/screenshot.svg")


async def main() -> None:
    from tina.config.settings import AppSettings, SettingsManager
    from tina.main import VNAApp

    demo_settings = AppSettings(
        last_host="",
        last_port="inst0",
        start_freq_mhz=1.0,
        stop_freq_mhz=3000.0,
        sweep_points=401,
        filename_prefix="measurement",
        output_folder="measurement",
    )

    with patch.object(SettingsManager, "load", return_value=demo_settings):
        app = VNAApp(dev_mode=True)
        async with app.run_test(headless=True, size=(200, 52)) as pilot:
            await pilot.pause(0.5)
            svg = app.export_screenshot()

    OUTPUT.parent.mkdir(exist_ok=True)
    OUTPUT.write_text(svg)
    print(f"Screenshot saved to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
