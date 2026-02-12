# ukb_navigator.py
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, List

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


UKB_BASE = "https://biobank.ndph.ox.ac.uk/ukb"


@dataclass
class UKBNavigatorConfig:
    headless: bool = True
    timeout_s: float = 25.0
    max_wait_s: float = 10.0
    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )


def _field_url(field_id: int) -> str:
    return f"{UKB_BASE}/field.cgi?id={field_id}"


def _browse_url(browse_id: int) -> str:
    return f"{UKB_BASE}/browse.cgi?id={browse_id}&cd=browse"


def fetch_rendered_html(url: str, cfg: UKBNavigatorConfig, progress: List[Dict[str, str]]) -> str:
    start = time.time()
    progress.append({"step": "playwright", "message": f"Launching browser (headless={cfg.headless})"})
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=cfg.headless)
        context = browser.new_context(user_agent=cfg.user_agent)
        page = context.new_page()
        page.set_default_timeout(int(cfg.timeout_s * 1000))

        progress.append({"step": "goto", "message": f"Navigating to {url}"})
        page.goto(url, wait_until="domcontentloaded")

        # UKB is mostly server-rendered; still wait a little for late elements
        progress.append({"step": "wait", "message": f"Waiting up to {cfg.max_wait_s}s for body"})
        page.wait_for_selector("body", timeout=int(cfg.max_wait_s * 1000))

        html = page.content()

        browser.close()

    progress.append({"step": "done_fetch", "message": f"Fetched HTML in {time.time() - start:.2f}s"})
    return html


def parse_field_summary(html: str) -> Dict[str, Any]:
    """
    Extract "field page" structured info from field.cgi?id=...
    We prioritize robust text tables (not the histogram image).
    """
    soup = BeautifulSoup(html, "lxml")

    # Title (field name)
    title = soup.find("h1")
    field_title = title.get_text(strip=True) if title else None

    # Common UKB pages include key-value tables; we parse all tables as fallback
    tables = soup.find_all("table")
    kv: Dict[str, str] = {}

    for t in tables:
        rows = t.find_all("tr")
        for r in rows:
            cells = r.find_all(["th", "td"])
            if len(cells) == 2:
                k = cells[0].get_text(" ", strip=True)
                v = cells[1].get_text(" ", strip=True)
                if k and v and k not in kv:
                    kv[k] = v

    # Try to identify common fields
    # (These keys vary; we keep raw kv plus some normalized guesses.)
    def find_any(keys: List[str]) -> Optional[str]:
        for k in keys:
            for kk, vv in kv.items():
                if k.lower() in kk.lower():
                    return vv
        return None

    summary = {
        "field_title": field_title,
        "units": find_any(["unit", "units"]),
        "n_participants": find_any(["participants", "instances", "people"]),
        "n_items": find_any(["items", "fields"]),
        "raw_table_kv": kv,
    }

    return summary


def parse_browse_list(html: str) -> Dict[str, Any]:
    """
    Extract list of links + ids from browse.cgi?id=...
    """
    soup = BeautifulSoup(html, "lxml")
    links = soup.find_all("a")

    items = []
    for a in links:
        href = a.get("href") or ""
        text = a.get_text(" ", strip=True)
        # Field pages look like field.cgi?id=####
        if "field.cgi?id=" in href:
            try:
                field_id = int(href.split("field.cgi?id=")[1].split("&")[0])
            except Exception:
                continue
            items.append({"field_id": field_id, "text": text, "href": href})

    return {"count": len(items), "fields": items[:300]}  # cap


def ukb_navigate(
    extract: str,
    field_id: Optional[int] = None,
    browse_id: Optional[int] = None,
    url: Optional[str] = None,
    cfg: Optional[UKBNavigatorConfig] = None,
) -> Dict[str, Any]:
    cfg = cfg or UKBNavigatorConfig()
    progress: List[Dict[str, str]] = []
    start = time.time()

    if not url:
        if extract in ("field_summary", "field_full"):
            if field_id is None:
                raise ValueError("field_id is required for field extraction")
            url = _field_url(field_id)
        elif extract == "browse_list":
            if browse_id is None:
                raise ValueError("browse_id is required for browse extraction")
            url = _browse_url(browse_id)
        else:
            raise ValueError(f"Unknown extract mode: {extract}")

    html = fetch_rendered_html(url, cfg, progress)

    if extract in ("field_summary", "field_full"):
        data = parse_field_summary(html)
    elif extract == "browse_list":
        data = parse_browse_list(html)
    else:
        data = {}

    return {
        "status": "success",
        "elapsed_seconds": time.time() - start,
        "url_used": url,
        "extract": extract,
        "data": data,
        "progress": progress,
    }
