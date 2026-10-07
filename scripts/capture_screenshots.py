#!/usr/bin/env python3
"""Capture fallback screenshots for the default and custom-region flows.

Run the app first:
    streamlit run app.py --server.port 8899 --server.headless true

Then run:
    python3 scripts/capture_screenshots.py
"""

import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("Cai Playwright truoc: pip install playwright")


URL = "http://localhost:8899"
OUT = Path("outputs/screenshots")
VIEWPORT = {"width": 1600, "height": 1100}


def wait_for_map(page, seconds: int = 8) -> None:
    page.wait_for_selector("iframe.stCustomComponentV1", timeout=120_000)
    time.sleep(seconds)


def capture(page, filename: str) -> None:
    path = OUT / filename
    page.screenshot(path=str(path), full_page=True)
    print(f"luu {path}")


def draw_rectangle(page) -> None:
    iframe = page.locator("iframe.stCustomComponentV1").first
    iframe.wait_for(state="visible", timeout=120_000)
    frame = iframe.content_frame
    frame.locator("a.leaflet-draw-draw-rectangle").click()
    box = iframe.bounding_box()
    if box is None:
        raise RuntimeError("Khong doc duoc kich thuoc ban do ve vung")
    page.mouse.move(box["x"] + box["width"] * 0.46, box["y"] + box["height"] * 0.35)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] * 0.63, box["y"] + box["height"] * 0.58)
    page.mouse.up()
    time.sleep(8)


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(URL, wait_until="domcontentloaded")
        page.wait_for_selector("button:has-text('Tìm vùng ưu tiên')", timeout=120_000)
        wait_for_map(page)
        capture(page, "01_borough_preview.png")

        page.click("button:has-text('Tìm vùng ưu tiên')")
        page.wait_for_selector("text=Top 3 vùng ưu tiên", timeout=120_000)
        wait_for_map(page)
        capture(page, "02_borough_result.png")

        page.get_by_text("Vẽ một vùng", exact=True).click()
        wait_for_map(page)
        draw_rectangle(page)
        page.wait_for_selector("text=Truy vấn hiện tại có", timeout=120_000)
        page.click("button:has-text('Tìm vùng ưu tiên')")
        page.wait_for_selector("text=Top 3 vùng ưu tiên", timeout=120_000)
        wait_for_map(page, seconds=12)
        capture(page, "03_custom_region_result.png")
        browser.close()


if __name__ == "__main__":
    run()
