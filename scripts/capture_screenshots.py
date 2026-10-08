#!/usr/bin/env python3
"""Capture fallback screenshots for the default and custom-region flows.

Run the app first:
    npm run build --prefix frontend
    python3 -m uvicorn hotspot.api:app --app-dir src --host 127.0.0.1 --port 8899

Then run:
    python3 scripts/capture_screenshots.py
"""

from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit("Cai Playwright truoc: pip install playwright")


URL = "http://localhost:8899"
OUT = Path("outputs/screenshots")
VIEWPORT = {"width": 1600, "height": 1100}


def wait_for_map(page, name: str) -> None:
    page.get_by_role("region", name=name).locator(".leaflet-container").wait_for(timeout=120_000)
    page.wait_for_timeout(2_000)


def capture(page, filename: str) -> None:
    path = OUT / filename
    page.screenshot(path=str(path), full_page=True)
    print(f"luu {path}")


def capture_result(page, filename: str) -> None:
    wait_for_map(page, "Bản đồ kết quả")
    capture(page, filename)


def draw_rectangle(page) -> None:
    map_region = page.get_by_role("region", name="Bản đồ pickup")
    map_region.locator(".leaflet-pm-icon-rectangle").click()
    box = map_region.locator(".leaflet-container").bounding_box()
    if box is None:
        raise RuntimeError("Khong doc duoc kich thuoc ban do ve vung")
    page.mouse.click(box["x"] + box["width"] * 0.46, box["y"] + box["height"] * 0.35)
    page.mouse.move(box["x"] + box["width"] * 0.63, box["y"] + box["height"] * 0.58)
    page.mouse.click(box["x"] + box["width"] * 0.63, box["y"] + box["height"] * 0.58)


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport=VIEWPORT)
        page.goto(URL, wait_until="domcontentloaded")
        page.get_by_text("Truy vấn hiện tại có").wait_for(timeout=120_000)
        wait_for_map(page, "Bản đồ pickup")
        capture(page, "01_borough_preview.png")

        page.get_by_role("button", name="Tìm vùng ưu tiên").click()
        page.get_by_role("region", name="Bản đồ kết quả").wait_for(timeout=120_000)
        capture_result(page, "02_borough_result.png")

        page.get_by_role("radio", name="Vẽ một vùng").check()
        wait_for_map(page, "Bản đồ pickup")
        draw_rectangle(page)
        page.get_by_role("button", name="Xóa vùng đã vẽ").wait_for(timeout=120_000)
        page.get_by_role("button", name="Tìm vùng ưu tiên").click()
        capture_result(page, "03_custom_region_result.png")
        browser.close()


if __name__ == "__main__":
    run()
