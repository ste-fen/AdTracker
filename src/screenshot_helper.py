import asyncio
import io
import os
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def _ensure_windows_proactor_event_loop_policy():
    """Playwright needs subprocess support, which requires Proactor on Windows."""
    if os.name != "nt":
        return

    current_policy = asyncio.get_event_loop_policy()
    if isinstance(current_policy, asyncio.WindowsProactorEventLoopPolicy):
        return

    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def _with_access_token(snapshot_url, access_token):
    """Append or replace the access_token query parameter in a snapshot URL."""
    parsed = urlparse(snapshot_url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["access_token"] = access_token
    return urlunparse(parsed._replace(query=urlencode(query)))


def _sanitize_ad_id(ad_id):
    """Create a filesystem-safe id while preserving the original id as much as possible."""
    cleaned = "".join(ch for ch in str(ad_id) if ch.isalnum() or ch in ("-", "_"))
    return cleaned or str(ad_id)


def _dismiss_cookie_banner(page):
    """Try to accept Facebook cookies so the ad preview is not obscured."""
    cookie_selectors = [
        "[data-cookiebanner='accept_button']",
        "[data-testid='cookie-policy-manage-dialog-accept-button']",
        "button[title='Alle Cookies erlauben']",
        "button[title='Allow all cookies']",
    ]
    cookie_texts = [
        "Alle Cookies erlauben",
        "Allow all cookies",
        "Alle akzeptieren",
        "Accept all",
    ]

    # 1. Wait briefly for the banner to appear (lazy-loaded)
    for selector in cookie_selectors:
        try:
            btn = page.locator(selector)
            btn.wait_for(state="visible", timeout=3000)
            btn.click(timeout=2000)
            page.wait_for_load_state("networkidle", timeout=5000)
            return
        except Exception:
            pass

    # 2. Text-based fallback
    for text in cookie_texts:
        try:
            btn = page.get_by_role("button", name=text, exact=False)
            if btn.count() > 0:
                btn.first.click(timeout=2000)
                page.wait_for_load_state("networkidle", timeout=5000)
                return
        except Exception:
            pass


def generate_meta_screenshot_archive(ads, access_token, timeout_ms=35000):
    """
    Create screenshots for Meta ads and return an in-memory zip.

    Returns:
        tuple[bytes | None, int, int]
        - zip bytes (None when no screenshots were created)
        - created screenshot count
        - attempted screenshot count
    """
    if not ads:
        return None, 0, 0
    if not access_token:
        raise ValueError("META_ACCESS_TOKEN is required for snapshot screenshots.")

    _ensure_windows_proactor_event_loop_policy()

    attempted = 0
    created_paths = []

    with tempfile.TemporaryDirectory(prefix="meta_ad_screenshots_") as temp_dir:
        output_dir = Path(temp_dir)

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(viewport={"width": 1000, "height": 1000})

                for ad in ads:
                    ad_id = ad.get("id")
                    snapshot_url = ad.get("ad_snapshot_url")
                    if not ad_id or not snapshot_url:
                        continue

                    attempted += 1
                    safe_id = _sanitize_ad_id(ad_id)
                    target_path = output_dir / f"{safe_id}.png"
                    page = context.new_page()
                    try:
                        target_url = _with_access_token(snapshot_url, access_token)
                        page.goto(target_url, wait_until="networkidle", timeout=timeout_ms)
                        _dismiss_cookie_banner(page)
                        page.screenshot(path=str(target_path), full_page=True)
                        created_paths.append(target_path)
                    except PlaywrightTimeoutError:
                        print(f"Screenshot timeout for ad id {ad_id}")
                    except Exception as exc:
                        print(f"Screenshot failed for ad id {ad_id}: {exc}")
                    finally:
                        page.close()

                context.close()
                browser.close()
        except NotImplementedError as exc:
            raise RuntimeError(
                "Playwright konnte unter Windows keinen Subprozess starten. "
                "Bitte pruefe, dass du in einer normalen lokalen Python-Umgebung laeufst "
                "und installiere Browser mit: playwright install chromium"
            ) from exc

        if not created_paths:
            return None, 0, attempted

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            for image_path in created_paths:
                archive.write(image_path, arcname=os.path.basename(image_path))

        return zip_buffer.getvalue(), len(created_paths), attempted