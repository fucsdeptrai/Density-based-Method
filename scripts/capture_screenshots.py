"""Chup man hinh app Streamlit cho fallback khi demo bi loi.

Chay app truoc:
    streamlit run app.py --server.port 8899 --server.headless true

Roi chay:
    python scripts/capture_screenshots.py

Dung Chrome da cai san tren may (channel='chrome'), nen KHONG can
`playwright install chromium` — tranh viec tai ~150 MB.
"""

import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    raise SystemExit(
        "Can cai playwright truoc:  pip install playwright\n"
        "(khong can chay 'playwright install' — script dung Chrome san co)"
    )

URL = "http://localhost:8899"
OUT = Path("outputs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

# (ten file, thay doi tren sidebar truoc khi bam Phan tich)
# Chi so slider: 0 gio bat dau, 1 gio ket thuc, 2 eps, 3 MinPts, 4 bandwidth, 5 nguong
SCENARIOS = [
    ("01_default", {}),
    ("02_eps_50", {"eps": "50"}),
    ("03_minpts_30", {"minpts": "30"}),
]


def set_slider(page, label, value):
    """Keo slider Streamlit theo DOM cua no (data-testid='stSlider')."""
    slider = (
        page.locator("section[data-testid='stSidebar'] div[data-testid='stSlider']")
        .filter(has=page.locator(f"text={label}"))
        .first
    )
    slider.scroll_into_view_if_needed()
    slider.locator("div[data-testid='stSliderThumbValue']").inner_text()  # dam bao da render
    slider.evaluate(
        """(el, v) => {
            const input = el.querySelector('input');
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, v);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )
    time.sleep(1.5)


def set_slider_by_index(page, index: int, value: str):
    slider = page.locator("section[data-testid='stSidebar'] div[data-testid='stSlider']").nth(index)
    slider.scroll_into_view_if_needed()
    slider.evaluate(
        """(el, v) => {
            const input = el.querySelector('input');
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, v);
            input.dispatchEvent(new Event('input', {bubbles: true}));
            input.dispatchEvent(new Event('change', {bubbles: true}));
        }""",
        value,
    )
    time.sleep(1.5)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1100})

        for name, changes in SCENARIOS:
            page.goto(URL)
            page.wait_for_selector("text=Phân tích hotspot", timeout=60000)
            time.sleep(3)

            # Thu tu slider trong sidebar: 0 gio bat dau, 1 gio ket thuc,
            # 2 eps, 3 MinPts, 4 bandwidth, 5 nguong vung nong
            if "eps" in changes:
                set_slider_by_index(page, 2, changes["eps"])
            if "minpts" in changes:
                set_slider_by_index(page, 3, changes["minpts"])

            page.click("button:has-text('Phân tích hotspot')")

            # Ban do nhung trong iframe cua streamlit-folium, khong phai
            # phan tu DOM cua trang chinh.
            try:
                page.wait_for_selector("iframe.stCustomComponentV1", timeout=120000)
            except Exception as exc:
                print(f"  {name}: BAN DO CHUA VE ({type(exc).__name__})")
            time.sleep(9)
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=True)
            print(f"  luu {OUT / name}.png")

            frame = page.locator("iframe.stCustomComponentV1").first
            if frame.count():
                frame.screenshot(path=str(OUT / f"{name}_map.png"))
                print(f"  luu {OUT / name}_map.png")

        browser.close()
    print("Xong.")


if __name__ == "__main__":
    run()