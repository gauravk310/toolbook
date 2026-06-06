"""
generate_web_report.py
======================
Passive webpage analyser that produces a multi-section SPA report.

Output structure
----------------
<output_dir>/
    index.html          ← sidebar shell (SPA loader)
    assets/
        shared.css      ← common styles
    sections/
        summary.html
        siteinfo.html
        security.html
        seo.html
        performance.html
        accessibility.html
        technologies.html
        dns.html
        screenshots.html
        charts.html

Usage
-----
    python generate_web_report.py https://example.com
    python generate_web_report.py https://example.com --out ./my_reports

Dependencies (pip install)
--------------------------
    requests beautifulsoup4 lxml dnspython

Optional (screenshots)
-----------------------
    pip install playwright Pillow && playwright install chromium
"""

import webbrowser
import os
import re
import ssl
import json
import time
import socket
import base64
import logging
import datetime
import urllib.parse
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

# ── optional deps ──────────────────────────────────────────────────────────────
try:
    # pyrefly: ignore [missing-import]
    import dns.resolver as dns_resolver

    HAS_DNS = True
except ImportError:
    HAS_DNS = False

try:
    from playwright.sync_api import sync_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

try:
    from PIL import Image

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("web_report")


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════


def _score_color(score: int) -> str:
    if score >= 80:
        return "#00e676"
    if score >= 60:
        return "#ffab00"
    if score >= 40:
        return "#ff7043"
    return "#ff3d57"


def _score_label(score: int) -> str:
    if score >= 80:
        return "Good"
    if score >= 60:
        return "Needs Work"
    if score >= 40:
        return "Poor"
    return "Critical"


def _bool_badge(val: bool, t="✓ Yes", f="✗ No") -> str:
    cls = "badge-good" if val else "badge-bad"
    return f'<span class="badge {cls}">{"✓ Yes" if val else "✗ No"}</span>'


def _sev_badge(sev: str) -> str:
    m = {
        "critical": "badge-critical",
        "high": "badge-high",
        "medium": "badge-medium",
        "low": "badge-low",
    }
    return f'<span class="badge {m.get(sev, "badge-low")}">{sev.capitalize()}</span>'


def _status_badge(code: int) -> str:
    cls = (
        "badge-good"
        if 200 <= code < 300
        else ("badge-warn" if 300 <= code < 400 else "badge-bad")
    )
    return f'<span class="badge {cls}">{code}</span>'


def _score_badge(score: int) -> str:
    cls = (
        "badge-good" if score >= 80 else ("badge-warn" if score >= 60 else "badge-bad")
    )
    return f'<span class="badge {cls}">Score: {score}/100</span>'


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SCAN ENGINE
# ══════════════════════════════════════════════════════════════════════════════


def run_scan(url: str, delay: int = 0) -> dict[str, Any]:
    """Run all passive checks and return a single data dictionary."""

    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; WebAnalyzer/2.0)",
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
        }
    )

    def _get(target, timeout=10, allow_redirects=True):
        try:
            return session.get(
                target, timeout=timeout, allow_redirects=allow_redirects, verify=False
            )
        except Exception as e:
            log.debug("GET %s failed: %s", target, e)
            return None

    # ── 1. Fetch ───────────────────────────────────────────────────────────────
    log.info("Fetching %s …", url)
    if delay > 0:
        log.info("Waiting %d seconds before fetching...", delay)
        time.sleep(delay)
    t0 = time.monotonic()
    resp = _get(url)
    if resp is None:
        raise RuntimeError(f"Cannot reach {url}")

    ttfb = round((time.monotonic() - t0) * 1000, 1)
    html = resp.text
    soup = BeautifulSoup(html, "lxml")
    headers = dict(resp.headers)
    final_url = resp.url
    status_code = resp.status_code
    page_size_kb = round(len(resp.content) / 1024, 1)
    redirect_chain = [r.url for r in resp.history] + [final_url]
    parsed = urllib.parse.urlparse(final_url)
    domain = parsed.netloc
    scheme = parsed.scheme
    html_lower = html.lower()

    def _resolve(host):
        try:
            return socket.gethostbyname(host.split(":")[0])
        except Exception:
            return "N/A"

    ip = _resolve(domain)
    robots = _get(f"{scheme}://{domain}/robots.txt")
    sitemap = _get(f"{scheme}://{domain}/sitemap.xml")
    has_robots = bool(robots and robots.status_code == 200)
    has_sitemap = bool(sitemap and sitemap.status_code == 200)
    fav_tag = soup.find("link", rel=lambda r: r and "icon" in " ".join(r).lower())

    # ── 2. Security ────────────────────────────────────────────────────────────
    log.info("Security checks …")
    sec_issues, sec = [], {}
    is_https = scheme == "https"
    sec["https"] = is_https
    if not is_https:
        sec_issues.append(
            {
                "severity": "critical",
                "issue": "HTTPS not enabled",
                "detail": "Site served over HTTP.",
            }
        )

    # SSL
    ssl_info = {}
    if is_https:
        try:
            ctx = ssl.create_default_context()
            host_clean = domain.split(":")[0]
            with ctx.wrap_socket(socket.socket(), server_hostname=host_clean) as s:
                s.settimeout(5)
                s.connect((host_clean, 443))
                cert = s.getpeercert()
                not_after = datetime.datetime.strptime(
                    cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
                )
                days_left = (not_after - datetime.datetime.utcnow()).days
                ssl_info = {
                    "issuer": dict(x[0] for x in cert.get("issuer", [])).get(
                        "organizationName", "?"
                    ),
                    "subject": dict(x[0] for x in cert.get("subject", [])).get(
                        "commonName", "?"
                    ),
                    "not_after": cert["notAfter"],
                    "not_before": cert.get("notBefore", "?"),
                    "tls_version": s.version(),
                    "days_left": days_left,
                    "valid": days_left > 0,
                }
                if days_left < 30:
                    sec_issues.append(
                        {
                            "severity": "high",
                            "issue": f"SSL cert expires in {days_left} days",
                            "detail": cert["notAfter"],
                        }
                    )
        except Exception as e:
            ssl_info = {"error": str(e)}
            sec_issues.append(
                {"severity": "medium", "issue": "SSL check failed", "detail": str(e)}
            )
    sec["ssl"] = ssl_info

    # Security headers
    _hdrs = {
        "Strict-Transport-Security": ("hsts", "high", "HSTS header missing"),
        "Content-Security-Policy": ("csp", "high", "CSP header missing"),
        "X-Frame-Options": ("xframe", "medium", "X-Frame-Options missing"),
        "Referrer-Policy": ("ref", "low", "Referrer-Policy missing"),
        "Permissions-Policy": ("perms", "low", "Permissions-Policy missing"),
        "X-Content-Type-Options": ("xcto", "medium", "X-Content-Type-Options missing"),
        "X-XSS-Protection": ("xxss", "low", "X-XSS-Protection missing"),
    }
    for h, (key, sev, msg) in _hdrs.items():
        present = h in headers
        sec[key] = present
        if not present:
            sec_issues.append(
                {"severity": sev, "issue": msg, "detail": f"Add '{h}' header."}
            )

    # Cookies
    cookies_info = []
    for c in resp.cookies:
        info = {
            "name": c.name,
            "secure": c.secure,
            "httponly": "httponly" in str(c._rest).lower(),
            "samesite": c._rest.get("SameSite", "Not Set"),
        }
        cookies_info.append(info)
        if not c.secure and is_https:
            sec_issues.append(
                {
                    "severity": "medium",
                    "issue": f"Cookie '{c.name}' lacks Secure flag",
                    "detail": "",
                }
            )
    sec["cookies"] = cookies_info

    # Info disclosure
    disco = {
        h: headers[h]
        for h in ["X-Powered-By", "X-AspNet-Version", "X-Generator"]
        if h in headers
    }
    sec["disclosure"] = disco
    for h, v in disco.items():
        sec_issues.append(
            {
                "severity": "low",
                "issue": f"Info disclosure: {h}: {_esc(v)}",
                "detail": "Remove or obfuscate.",
            }
        )

    # CORS
    cors = headers.get("Access-Control-Allow-Origin", "Not Set")
    sec["cors"] = cors
    if cors == "*":
        sec_issues.append(
            {
                "severity": "medium",
                "issue": "Wildcard CORS (Access-Control-Allow-Origin: *)",
                "detail": "Restrict to specific origins.",
            }
        )

    # Sensitive paths
    _paths = [
        "/.env",
        "/.git/HEAD",
        "/admin",
        "/login",
        "/backup",
        "/phpinfo.php",
        "/wp-admin",
        "/config.php",
    ]
    exposed = []
    for p in _paths:
        r = _get(f"{scheme}://{domain}{p}", timeout=5)
        if r and r.status_code in (200, 403):
            exposed.append({"path": p, "status": r.status_code})
            if r.status_code == 200:
                sec_issues.append(
                    {
                        "severity": "high",
                        "issue": f"Sensitive path exposed: {p}",
                        "detail": f"HTTP {r.status_code}",
                    }
                )
    sec["exposed_paths"] = exposed

    weights = {"critical": 25, "high": 15, "medium": 8, "low": 3}
    penalty = sum(weights.get(i["severity"], 0) for i in sec_issues)
    security_score = max(0, 100 - penalty)
    risk_level = (
        "Critical"
        if security_score < 40
        else (
            "High"
            if security_score < 60
            else (
                "Medium"
                if security_score < 75
                else "Low" if security_score < 90 else "Minimal"
            )
        )
    )

    # ── 3. SEO ─────────────────────────────────────────────────────────────────
    log.info("SEO …")
    seo_issues, seo = [], {}

    title = (
        (soup.find("title") or {}).get_text(strip=True) if soup.find("title") else ""
    )
    seo["title"] = title
    seo["title_len"] = len(title)
    if not title:
        seo_issues.append("Missing <title> tag")
    elif len(title) < 30:
        seo_issues.append("Title too short (< 30 chars)")
    elif len(title) > 60:
        seo_issues.append("Title too long (> 60 chars)")

    md = soup.find("meta", attrs={"name": "description"})
    meta_desc = md.get("content", "") if md else ""
    seo["meta_desc"] = meta_desc
    seo["meta_desc_len"] = len(meta_desc)
    if not meta_desc:
        seo_issues.append("Missing meta description")
    elif len(meta_desc) > 160:
        seo_issues.append("Meta description too long (> 160 chars)")

    headings = {
        t: [h.get_text(strip=True) for h in soup.find_all(t)]
        for t in ["h1", "h2", "h3", "h4", "h5", "h6"]
    }
    seo["headings"] = headings
    if not headings["h1"]:
        seo_issues.append("No H1 heading found")
    elif len(headings["h1"]) > 1:
        seo_issues.append(f"Multiple H1 tags ({len(headings['h1'])})")

    canonical = soup.find("link", rel="canonical")
    seo["canonical"] = canonical["href"] if canonical and canonical.get("href") else ""
    if not seo["canonical"]:
        seo_issues.append("No canonical URL")

    og = {
        t.get("property", ""): t.get("content", "")
        for t in soup.find_all("meta", property=re.compile(r"^og:"))
    }
    tw = {
        t.get("name", ""): t.get("content", "")
        for t in soup.find_all("meta", attrs={"name": re.compile(r"^twitter:")})
    }
    seo["og"] = og
    seo["twitter"] = tw
    if not og:
        seo_issues.append("No OpenGraph tags")
    if not tw:
        seo_issues.append("No Twitter Card tags")

    schema = soup.find_all("script", type="application/ld+json")
    seo["structured_data"] = len(schema)

    all_links = soup.find_all("a", href=True)
    int_links, ext_links = [], []
    for a in all_links:
        h = a["href"]
        if h.startswith("http"):
            (int_links if domain in h else ext_links).append(h)
        elif h.startswith("/") or not h.startswith(("#", "mailto:", "tel:")):
            int_links.append(h)
    seo["internal_links"] = len(int_links)
    seo["external_links"] = len(ext_links)

    imgs = soup.find_all("img")
    missing_alts = [i for i in imgs if not i.get("alt")]
    seo["images_total"] = len(imgs)
    seo["images_no_alt"] = len(missing_alts)
    if missing_alts:
        seo_issues.append(f"{len(missing_alts)} image(s) missing alt text")

    vp = soup.find("meta", attrs={"name": "viewport"})
    seo["viewport"] = bool(vp)
    if not vp:
        seo_issues.append("No viewport meta tag")
    seo["has_robots"] = has_robots
    seo["has_sitemap"] = has_sitemap
    if not has_robots:
        seo_issues.append("robots.txt not found")
    if not has_sitemap:
        seo_issues.append("sitemap.xml not found")

    seo_score = max(0, 100 - len(seo_issues) * 8)

    # ── 4. Performance ─────────────────────────────────────────────────────────
    log.info("Performance …")
    perf_issues = []
    enc_hdr = headers.get("Content-Encoding", "")
    compressed = enc_hdr in ("gzip", "br", "deflate")
    cache_ctrl = headers.get("Cache-Control", "")
    etag = headers.get("ETag", "")
    if not compressed:
        perf_issues.append("Compression (gzip/br) not enabled")
    if not cache_ctrl and not etag:
        perf_issues.append("No caching headers found")
    if page_size_kb > 3000:
        perf_issues.append(f"Large page size ({page_size_kb} KB)")
    if ttfb > 800:
        perf_issues.append(f"High TTFB ({ttfb} ms)")

    scripts = soup.find_all("script", src=True)
    css_tags = soup.find_all("link", rel="stylesheet")
    perf = {
        "ttfb": ttfb,
        "page_size_kb": page_size_kb,
        "compressed": compressed,
        "cache_control": cache_ctrl,
        "etag": etag,
        "encoding": enc_hdr,
        "scripts": len(scripts),
        "css": len(css_tags),
        "images": len(imgs),
        "last_modified": headers.get("Last-Modified", ""),
    }
    perf_score = max(
        0,
        min(
            100,
            100
            - len(perf_issues) * 12
            - max(0, ttfb - 200) // 100
            - max(0, page_size_kb - 500) // 200,
        ),
    )

    # ── 5. Accessibility ───────────────────────────────────────────────────────
    log.info("Accessibility …")
    a11y_issues = []
    if missing_alts:
        a11y_issues.append(f"{len(missing_alts)} image(s) without alt text")

    inputs = soup.find_all("input")
    unlabeled = [
        i
        for i in inputs
        if i.get("type", "text") not in ("hidden", "submit", "button", "image")
        and not i.get("aria-label")
        and not i.get("aria-labelledby")
        and not soup.find("label", attrs={"for": i.get("id", "__none__")})
    ]
    if unlabeled:
        a11y_issues.append(f"{len(unlabeled)} form input(s) without labels")

    hlevels = [int(h.name[1]) for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    if hlevels and any(
        hlevels[i + 1] - hlevels[i] > 1 for i in range(len(hlevels) - 1)
    ):
        a11y_issues.append("Heading hierarchy skipped (e.g. H1 → H3)")

    lang_attr = bool(soup.find("html", lang=True))
    if not lang_attr:
        a11y_issues.append("HTML lang attribute missing")

    empty_btns = [
        b
        for b in soup.find_all("button")
        if not b.get_text(strip=True) and not b.get("aria-label")
    ]
    if empty_btns:
        a11y_issues.append(f"{len(empty_btns)} empty button(s) without aria-label")

    a11y = {
        "lang": lang_attr,
        "aria_labels": len(soup.find_all(attrs={"aria-label": True})),
        "roles": len(soup.find_all(attrs={"role": True})),
        "unlabeled_inputs": len(unlabeled),
        "empty_buttons": len(empty_btns),
        "missing_alts": len(missing_alts),
    }
    a11y_score = max(0, 100 - len(a11y_issues) * 12)

    # ── 6. Technologies ────────────────────────────────────────────────────────
    log.info("Technology detection …")
    techs = []
    hdrs_l = {k.lower(): v.lower() for k, v in headers.items()}
    srv = headers.get("Server", "").lower()
    xpb = headers.get("X-Powered-By", "").lower()

    if "cloudflare" in srv or "cf-ray" in hdrs_l:
        techs.append({"name": "Cloudflare", "cat": "CDN", "via": "header"})
    if "nginx" in srv:
        techs.append({"name": "Nginx", "cat": "Web Server", "via": "header"})
    if "apache" in srv:
        techs.append({"name": "Apache", "cat": "Web Server", "via": "header"})
    if "php" in xpb or "php" in srv:
        techs.append({"name": "PHP", "cat": "Language", "via": "header"})
    if "express" in xpb:
        techs.append({"name": "Express", "cat": "Framework", "via": "header"})
    if "node" in xpb:
        techs.append({"name": "Node.js", "cat": "Runtime", "via": "header"})

    _patterns = [
        ("React", [r"__reactfiber", r"react\.production"]),
        ("Next.js", [r"__next", r"_next/"]),
        ("Vue.js", [r"vue\.js", r"__vue__"]),
        ("Angular", [r"ng-version", r"angular\.min"]),
        ("jQuery", [r"jquery\.min\.js", r"jquery-\d"]),
        ("Bootstrap", [r"bootstrap\.min\.css", r"bootstrap\.min\.js"]),
        ("Tailwind", [r"tailwindcss", r"tailwind\.css"]),
        ("WordPress", [r"/wp-content/", r"/wp-includes/"]),
        ("Shopify", [r"cdn\.shopify\.com"]),
        ("Gatsby", [r"___gatsby", r"gatsby"]),
        ("Nuxt.js", [r"__nuxt"]),
        ("Svelte", [r"__svelte"]),
    ]
    existing = {t["name"] for t in techs}
    for name, pats in _patterns:
        if name not in existing:
            for p in pats:
                if re.search(p, html_lower):
                    techs.append({"name": name, "cat": "Frontend", "via": "html"})
                    break

    # ── 7. DNS ─────────────────────────────────────────────────────────────────
    log.info("DNS …")
    dns_records = {}
    if HAS_DNS:
        for rtype in ("A", "MX", "TXT", "NS", "CNAME"):
            try:
                dns_records[rtype] = [
                    str(r) for r in dns_resolver.resolve(domain.split(":")[0], rtype)
                ]
            except Exception:
                dns_records[rtype] = []
    else:
        dns_records["note"] = "dnspython not installed"

    cdn_map = {
        "Cloudflare": ["cf-ray", "cf-cache-status"],
        "AWS CloudFront": ["x-amz-cf-id", "x-cache"],
        "Fastly": ["x-served-by", "x-cache-hits"],
        "Akamai": ["x-check-cacheable"],
        "Azure CDN": ["x-msedge-ref"],
    }
    detected_cdn = "None"
    for cdn, sigs in cdn_map.items():
        if any(s in hdrs_l for s in sigs):
            detected_cdn = cdn
            break
    dns_records["cdn"] = detected_cdn

    # ── 8. Screenshots ─────────────────────────────────────────────────────────
    desktop_b64 = mobile_b64 = ""
    if HAS_PLAYWRIGHT:
        log.info("Capturing screenshots …")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(viewport={"width": 1280, "height": 800})
                pg = ctx.new_page()
                pg.goto(final_url, timeout=20000, wait_until="networkidle")
                if delay > 0:
                    pg.wait_for_timeout(delay * 1000)
                d_png = pg.screenshot(full_page=True)
                ctx.close()
                ctx2 = browser.new_context(**p.devices["iPhone 12"])
                pg2 = ctx2.new_page()
                pg2.goto(final_url, timeout=20000, wait_until="networkidle")
                if delay > 0:
                    pg2.wait_for_timeout(delay * 1000)
                m_png = pg2.screenshot(full_page=True)
                ctx2.close()
                browser.close()

            def _b64(data):
                if HAS_PIL:
                    img = Image.open(BytesIO(data))
                    if img.width > 1200:
                        ratio = 1200 / img.width
                        img = img.resize((1200, int(img.height * ratio)), Image.LANCZOS)
                    buf = BytesIO()
                    img.save(buf, "PNG", optimize=True)
                    data = buf.getvalue()
                return base64.b64encode(data).decode()

            desktop_b64 = _b64(d_png)
            mobile_b64 = _b64(m_png)
        except Exception as e:
            log.warning("Screenshot failed: %s", e)
    else:
        log.info("Playwright not installed — screenshots skipped.")

    # ── 9. Aggregate ───────────────────────────────────────────────────────────
    overall_score = round((security_score + seo_score + perf_score + a11y_score) / 4)
    scan_time = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    return {
        "url": url,
        "final_url": final_url,
        "domain": domain,
        "ip": ip,
        "scheme": scheme,
        "status_code": status_code,
        "server": headers.get("Server", "Unknown"),
        "content_type": headers.get("Content-Type", "Unknown"),
        "encoding": resp.encoding or "Unknown",
        "page_size_kb": page_size_kb,
        "ttfb": ttfb,
        "redirect_chain": redirect_chain,
        "has_robots": has_robots,
        "has_sitemap": has_sitemap,
        "fav": fav_tag is not None,
        "headers": headers,
        # scores
        "security_score": security_score,
        "seo_score": seo_score,
        "perf_score": perf_score,
        "a11y_score": a11y_score,
        "overall_score": overall_score,
        "risk_level": risk_level,
        # analysis data
        "sec": sec,
        "sec_issues": sec_issues,
        "seo": seo,
        "seo_issues": seo_issues,
        "perf": perf,
        "perf_issues": perf_issues,
        "a11y": a11y,
        "a11y_issues": a11y_issues,
        "techs": techs,
        "dns": dns_records,
        "desktop_b64": desktop_b64,
        "mobile_b64": mobile_b64,
        "scan_time": scan_time,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED CSS
# ══════════════════════════════════════════════════════════════════════════════

SHARED_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&display=swap');
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#080b10;--surface:#0e1319;--surface2:#141b24;
  --border:#1e2a38;--border2:#263040;--text:#d4dfe8;--muted:#4e6070;
  --accent:#00d4ff;--accent2:#7c5cfc;--good:#00e676;--warn:#ffab00;--danger:#ff3d57;
  --mono:'JetBrains Mono',monospace;--sans:'Syne',sans-serif;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:var(--sans);min-height:100vh;padding:32px 36px;animation:fadeIn .25s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.page-header{margin-bottom:28px;padding-bottom:20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:14px}
.page-header-icon{width:44px;height:44px;background:linear-gradient(135deg,rgba(0,212,255,.15),rgba(124,92,252,.15));border:1px solid var(--border2);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:22px;flex-shrink:0}
.page-header h1{font-size:20px;font-weight:800;color:var(--text)}
.page-header .sub{font-size:12px;color:var(--muted);margin-top:2px;font-family:var(--mono)}
.score-badge{margin-left:auto;display:flex;flex-direction:column;align-items:flex-end}
.score-num{font-size:32px;font-weight:800;line-height:1;font-family:var(--mono)}
.score-lbl{font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.1em;font-family:var(--mono)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;margin-bottom:20px}
.card-header{padding:14px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.card-title{font-size:12px;font-weight:700;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-family:var(--mono)}
.card-body{padding:20px}
.grid-2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.stat-card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:18px;position:relative;overflow:hidden}
.stat-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--accent-color,var(--accent))}
.stat-val{font-size:28px;font-weight:800;font-family:var(--mono);color:var(--accent-color,var(--accent));line-height:1}
.stat-label{font-size:11px;color:var(--muted);margin-top:6px;text-transform:uppercase;letter-spacing:.08em;font-family:var(--mono)}
.table-wrap{overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:13px}
thead th{padding:10px 14px;background:var(--surface2);font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);font-family:var(--mono);border-bottom:1px solid var(--border);text-align:left;white-space:nowrap}
tbody td{padding:11px 14px;border-bottom:1px solid var(--border);vertical-align:middle;line-height:1.5}
tbody tr:last-child td{border-bottom:none}
tbody tr:hover td{background:var(--surface2)}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 9px;border-radius:6px;font-size:11px;font-weight:700;font-family:var(--mono);white-space:nowrap}
.badge-good{background:rgba(0,230,118,.12);color:#00e676;border:1px solid rgba(0,230,118,.25)}
.badge-bad{background:rgba(255,61,87,.12);color:#ff6b82;border:1px solid rgba(255,61,87,.25)}
.badge-warn{background:rgba(255,171,0,.12);color:#ffab00;border:1px solid rgba(255,171,0,.25)}
.badge-critical{background:rgba(255,61,87,.2);color:#ff3d57;border:1px solid rgba(255,61,87,.5)}
.badge-high{background:rgba(255,100,50,.12);color:#ff7043;border:1px solid rgba(255,100,50,.3)}
.badge-medium{background:rgba(255,171,0,.12);color:#ffab00;border:1px solid rgba(255,171,0,.3)}
.badge-low{background:rgba(0,212,255,.1);color:#00d4ff;border:1px solid rgba(0,212,255,.2)}
.badge-info{background:rgba(124,92,252,.12);color:#a78bfa;border:1px solid rgba(124,92,252,.25)}
.tech-tag{display:inline-block;background:var(--surface2);border:1px solid var(--border2);color:var(--accent2);border-radius:6px;padding:4px 10px;font-size:12px;font-weight:600;margin:3px;font-family:var(--mono)}
.info-row{display:flex;gap:16px;align-items:flex-start;padding:10px 0;border-bottom:1px solid var(--border);font-size:13px}
.info-row:last-child{border-bottom:none}
.info-key{color:var(--muted);min-width:160px;flex-shrink:0;font-size:11px;font-family:var(--mono);padding-top:2px}
.info-val{color:var(--text);word-break:break-all}
code{background:var(--surface2);border:1px solid var(--border2);padding:1px 6px;border-radius:4px;font-size:12px;font-family:var(--mono);color:var(--accent)}
.issue-list{list-style:none}
.issue-list li{display:flex;align-items:flex-start;gap:10px;padding:10px 0;border-bottom:1px solid var(--border);font-size:13px;line-height:1.5}
.issue-list li:last-child{border-bottom:none}
.issue-list li .icon{flex-shrink:0;font-size:14px}
.progress-wrap{background:var(--surface2);border-radius:99px;height:5px;overflow:hidden;margin-top:8px}
.progress-bar{height:100%;border-radius:99px;background:var(--accent-color,var(--accent));transition:width 1s cubic-bezier(.4,0,.2,1)}
.alert{border-radius:10px;padding:14px 18px;margin-bottom:20px;display:flex;align-items:flex-start;gap:14px;border:1px solid}
.alert-icon{font-size:20px;flex-shrink:0}
.alert-title{font-size:13px;font-weight:700}
.alert-sub{font-size:12px;color:var(--muted);margin-top:2px;font-family:var(--mono)}
.alert-critical{background:rgba(255,61,87,.08);border-color:rgba(255,61,87,.3)}
.alert-high{background:rgba(255,112,67,.08);border-color:rgba(255,112,67,.3)}
.alert-medium{background:rgba(255,171,0,.08);border-color:rgba(255,171,0,.3)}
.alert-good{background:rgba(0,230,118,.08);border-color:rgba(0,230,118,.3)}
.section-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;color:var(--muted);font-family:var(--mono);margin:22px 0 10px}
.section-label:first-child{margin-top:0}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg)}
::-webkit-scrollbar-thumb{background:var(--border2);border-radius:99px}
"""

CHARTJS = '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>'


def _section_shell(
    title: str, extra_css: str = "", extra_head: str = ""
) -> tuple[str, str]:
    """Return (open_html, close_html) for a section page."""
    open_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{_esc(title)}</title>
{extra_head}
<style>{SHARED_CSS}{extra_css}</style>
</head>
<body>
"""
    return open_html, "\n</body>\n</html>\n"


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION BUILDERS
# ══════════════════════════════════════════════════════════════════════════════


def build_summary(d: dict) -> str:
    sc = d["security_score"]
    seo = d["seo_score"]
    pc = d["perf_score"]
    ac = d["a11y_score"]
    ov = d["overall_score"]
    risk = d["risk_level"]
    all_issues = (
        len(d["sec_issues"])
        + len(d["seo_issues"])
        + len(d["perf_issues"])
        + len(d["a11y_issues"])
    )

    risk_alert_map = {
        "Critical": (
            "alert-critical",
            "🚨",
            "Critical Risk — Immediate Action Required",
        ),
        "High": ("alert-high", "⚠️", "High Risk — Action Recommended"),
        "Medium": ("alert-medium", "⚡", "Medium Risk — Review Recommended"),
        "Low": ("alert-good", "✅", "Low Risk — Good Standing"),
        "Minimal": ("alert-good", "✅", "Minimal Risk — Excellent"),
    }
    ac_cls, ac_icon, ac_title = risk_alert_map.get(
        risk, ("alert-medium", "⚡", "Review Recommended")
    )

    css = """
.ov-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin-bottom:20px}
.ov-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;text-align:center;position:relative;overflow:hidden;transition:transform .2s,border-color .2s}
.ov-card:hover{transform:translateY(-2px);border-color:var(--border2)}
.ov-card::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;background:var(--cc,var(--accent))}
.ov-score{font-size:44px;font-weight:800;font-family:var(--mono);color:var(--cc,var(--accent));line-height:1}
.ov-name{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.1em;margin-top:4px;font-family:var(--mono)}
.ov-label{font-size:12px;font-weight:700;margin-bottom:6px;color:var(--text)}
.chart-area{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.chart-box{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}
.chart-box canvas{max-height:260px}
.score-line{display:flex;align-items:center;gap:14px;font-size:13px;margin-bottom:10px}
.score-line .sname{width:120px;flex-shrink:0;font-family:var(--mono);font-size:11px;color:var(--muted)}
.score-line .bwrap{flex:1;height:20px;background:var(--surface2);border-radius:6px;overflow:hidden}
.score-line .bfill{height:100%;border-radius:6px;display:flex;align-items:center;padding:0 8px;font-size:11px;font-weight:700;color:#fff;font-family:var(--mono)}
.score-line .bnum{width:36px;text-align:right;font-family:var(--mono);font-weight:700;font-size:13px}
"""
    scores = [
        ("Security", sc, len(d["sec_issues"])),
        ("SEO", seo, len(d["seo_issues"])),
        ("Performance", pc, len(d["perf_issues"])),
        ("Accessibility", ac, len(d["a11y_issues"])),
    ]
    cards_html = ""
    for name, score, issues in scores:
        cc = _score_color(score)
        cards_html += f"""<div class="ov-card" style="--cc:{cc}">
  <div class="ov-label">{name}</div>
  <div class="ov-score">{score}</div>
  <div class="ov-name">{_score_label(score)}</div>
  <div class="progress-wrap"><div class="progress-bar" style="width:{score}%;background:{cc}"></div></div>
  <div style="font-size:10px;color:var(--muted);margin-top:6px;font-family:var(--mono)">{issues} issues</div>
</div>"""

    score_bars = ""
    for name, score, _ in [
        ("Security", sc, 0),
        ("SEO", seo, 0),
        ("Performance", pc, 0),
        ("Accessibility", ac, 0),
        ("Overall", ov, 0),
    ]:
        cc = _score_color(score)
        score_bars += f"""<div class="score-line">
  <div class="sname">{name}</div>
  <div class="bwrap"><div class="bfill" style="width:{score}%;background:{cc}">{score}</div></div>
  <div class="bnum" style="color:{cc}">{score}</div>
</div>"""

    chart_data = json.dumps(
        {
            "labels": ["Security", "SEO", "Performance", "Accessibility"],
            "scores": [sc, seo, pc, ac],
            "issues": [
                len(d["sec_issues"]),
                len(d["seo_issues"]),
                len(d["perf_issues"]),
                len(d["a11y_issues"]),
            ],
        }
    )

    open_h, close_h = _section_shell("Summary", css, CHARTJS)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">📊</div>
  <div><h1>Executive Summary</h1><div class="sub">{_esc(d["domain"])} &mdash; {_esc(d["scan_time"])}</div></div>
  <div class="score-badge">
    <div class="score-num" style="color:{_score_color(ov)}">{ov}</div>
    <div class="score-lbl" style="color:{_score_color(ov)}">Overall</div>
  </div>
</div>

<div class="alert {ac_cls}">
  <div class="alert-icon">{ac_icon}</div>
  <div>
    <div class="alert-title">{ac_title}</div>
    <div class="alert-sub">Overall score: {ov}/100 &bull; {all_issues} issues found across all categories</div>
  </div>
</div>

<div class="ov-grid">{cards_html}</div>

<div class="chart-area">
  <div class="chart-box">
    <div class="card-title" style="margin-bottom:14px">Score Radar</div>
    <canvas id="radarChart"></canvas>
  </div>
  <div class="chart-box">
    <div class="card-title" style="margin-bottom:14px">Score Bars</div>
    {score_bars}
  </div>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Scan Metadata</div></div>
  <div class="card-body">
    <div class="grid-2">
      <div>
        <div class="info-row"><div class="info-key">Domain</div><div class="info-val"><code>{_esc(d["domain"])}</code></div></div>
        <div class="info-row"><div class="info-key">IP Address</div><div class="info-val"><code>{_esc(d["ip"])}</code></div></div>
        <div class="info-row"><div class="info-key">HTTP Status</div><div class="info-val">{_status_badge(d["status_code"])}</div></div>
        <div class="info-row"><div class="info-key">Scan Time</div><div class="info-val"><code>{_esc(d["scan_time"])}</code></div></div>
      </div>
      <div>
        <div class="info-row"><div class="info-key">Total Issues</div><div class="info-val"><span class="badge badge-warn">{all_issues} found</span></div></div>
        <div class="info-row"><div class="info-key">Risk Level</div><div class="info-val"><span class="badge badge-{"good" if risk in ("Low", "Minimal") else "medium" if risk == "Medium" else "high"}">{risk}</span></div></div>
        <div class="info-row"><div class="info-key">CDN</div><div class="info-val"><span class="tech-tag">{_esc(d["dns"].get("cdn", "None"))}</span></div></div>
        <div class="info-row"><div class="info-key">SSL/TLS</div><div class="info-val">{_bool_badge(d["sec"].get("https", False))}</div></div>
      </div>
    </div>
  </div>
</div>

<script>
const cd = {chart_data};
const F = {{family:'JetBrains Mono',size:11}};
const G = '#1e2a38'; const T = '#4e6070';
const COLORS = cd.scores.map(s => s>=80?'#00e676':s>=60?'#ffab00':s>=40?'#ff7043':'#ff3d57');
new Chart(document.getElementById('radarChart'),{{
  type:'radar',
  data:{{labels:cd.labels,datasets:[{{label:'Score',data:cd.scores,
    backgroundColor:'rgba(0,212,255,0.1)',borderColor:'#00d4ff',
    pointBackgroundColor:COLORS,pointBorderColor:'#fff',pointRadius:5,borderWidth:2}}]}},
  options:{{responsive:true,scales:{{r:{{min:0,max:100,
    ticks:{{stepSize:25,color:T,backdropColor:'transparent',font:F}},
    grid:{{color:G}},angleLines:{{color:G}},
    pointLabels:{{color:'#d4dfe8',font:{{...F,size:12,weight:'700'}}}}
  }}}},plugins:{{legend:{{display:false}}}}}}
}});
</script>
""" + close_h


def build_siteinfo(d: dict) -> str:
    css = """
.rchain{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:12px 0;font-size:12px;font-family:var(--mono)}
.rstep{background:var(--surface2);border:1px solid var(--border2);border-radius:6px;padding:4px 10px;color:var(--accent)}
.rfinal{background:rgba(0,230,118,.1);border-color:rgba(0,230,118,.3);color:var(--good)}
.rarrow{color:var(--muted);font-size:14px}
"""
    chain = " ".join(
        f'<div class="rstep {"rfinal" if i == len(d["redirect_chain"]) - 1 else ""}">{_esc(u)}</div>'
        + ("" if i == len(d["redirect_chain"]) - 1 else '<div class="rarrow">→</div>')
        for i, u in enumerate(d["redirect_chain"])
    )
    hdr_rows = "".join(
        f"<tr><td><code>{_esc(k)}</code></td><td>{_esc(v)}</td></tr>"
        for k, v in sorted(d["headers"].items())
    )
    open_h, close_h = _section_shell("Site Information", css)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">🌐</div>
  <div><h1>Site Information</h1><div class="sub">General metadata &amp; server configuration</div></div>
</div>

<div class="grid-3" style="margin-bottom:20px">
  <div class="stat-card" style="--accent-color:#00d4ff"><div class="stat-val">{d["status_code"]}</div><div class="stat-label">HTTP Status</div></div>
  <div class="stat-card" style="--accent-color:#00e676"><div class="stat-val">{d["page_size_kb"]} KB</div><div class="stat-label">Page Size</div></div>
  <div class="stat-card" style="--accent-color:{"#00e676" if d["ttfb"] < 400 else "#ffab00" if d["ttfb"] < 800 else "#ff3d57"}">
    <div class="stat-val">{d["ttfb"]} ms</div><div class="stat-label">TTFB</div></div>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Server Details</div></div>
  <div class="card-body"><div class="grid-2">
    <div>
      <div class="info-row"><div class="info-key">Domain</div><div class="info-val"><code>{_esc(d["domain"])}</code></div></div>
      <div class="info-row"><div class="info-key">IP Address</div><div class="info-val"><code>{_esc(d["ip"])}</code></div></div>
      <div class="info-row"><div class="info-key">Server</div><div class="info-val"><span class="tech-tag">{_esc(d["server"])}</span></div></div>
      <div class="info-row"><div class="info-key">Content-Type</div><div class="info-val"><code>{_esc(d["content_type"])}</code></div></div>
      <div class="info-row"><div class="info-key">Encoding</div><div class="info-val"><code>{_esc(d["encoding"])}</code></div></div>
    </div>
    <div>
      <div class="info-row"><div class="info-key">robots.txt</div><div class="info-val">{_bool_badge(d["has_robots"])}</div></div>
      <div class="info-row"><div class="info-key">sitemap.xml</div><div class="info-val">{_bool_badge(d["has_sitemap"])}</div></div>
      <div class="info-row"><div class="info-key">Favicon</div><div class="info-val">{_bool_badge(d["fav"])}</div></div>
      <div class="info-row"><div class="info-key">CDN</div><div class="info-val"><span class="tech-tag">{_esc(d["dns"].get("cdn", "None"))}</span></div></div>
    </div>
  </div></div>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Redirect Chain</div></div>
  <div class="card-body"><div class="rchain">{chain}</div>
  <div style="font-size:12px;color:var(--muted);font-family:var(--mono)">{len(d["redirect_chain"]) - 1} redirect(s)</div>
  </div>
</div>

<div class="card">
  <div class="card-header"><div class="card-title">Response Headers</div></div>
  <div class="card-body" style="padding:0"><div class="table-wrap">
    <table><thead><tr><th>Header</th><th>Value</th></tr></thead>
    <tbody>{hdr_rows}</tbody></table>
  </div></div>
</div>
""" + close_h


def build_security(d: dict) -> str:
    sec = d["sec"]
    issues = d["sec_issues"]
    score = d["security_score"]
    ssl = sec.get("ssl", {})

    css = """
.hdr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(130px,1fr));gap:10px;margin-bottom:20px}
.hdr-check{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 12px;text-align:center;font-family:var(--mono)}
.hdr-check .icon{font-size:18px;margin-bottom:6px}
.hdr-check .name{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.hdr-check.ok{border-color:rgba(0,230,118,.3);background:rgba(0,230,118,.05)}
.hdr-check.fail{border-color:rgba(255,61,87,.3);background:rgba(255,61,87,.05)}
.hdr-check.warn{border-color:rgba(255,171,0,.3);background:rgba(255,171,0,.05)}
.ssl-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start}
.ssl-meter{text-align:center;padding:20px}
.ssl-days{font-size:52px;font-weight:800;font-family:var(--mono);line-height:1}
.ssl-days-lbl{font-size:11px;color:var(--muted);font-family:var(--mono);margin-top:4px;text-transform:uppercase}
"""
    hdr_checks = {
        "HTTPS": ("https", sec.get("https", False)),
        "HSTS": ("hsts", sec.get("hsts", False)),
        "CSP": ("csp", sec.get("csp", False)),
        "X-Frame": ("xframe", sec.get("xframe", False)),
        "Referrer": ("ref", sec.get("ref", False)),
        "X-CTO": ("xcto", sec.get("xcto", False)),
        "Perms-Policy": ("perms", sec.get("perms", False)),
        "XSS-Protect": ("xxss", sec.get("xxss", False)),
    }
    checks_html = ""
    for label, (_, val) in hdr_checks.items():
        cls = "ok" if val else "fail"
        icon = "✅" if val else "❌"
        checks_html += f'<div class="hdr-check {cls}"><div class="icon">{icon}</div><div class="name">{label}</div></div>'

    # SSL block
    if "error" in ssl:
        ssl_html = (
            f'<p class="badge badge-bad">SSL Check Failed: {_esc(ssl["error"])}</p>'
        )
    elif ssl:
        days = ssl.get("days_left", "?")
        dc = "#00e676" if isinstance(days, int) and days > 30 else "#ff3d57"
        ssl_html = f"""<div class="ssl-grid">
  <div>
    <div class="info-row"><div class="info-key">Issuer</div><div class="info-val">{_esc(ssl.get("issuer", "?"))}</div></div>
    <div class="info-row"><div class="info-key">Subject</div><div class="info-val"><code>{_esc(ssl.get("subject", "?"))}</code></div></div>
    <div class="info-row"><div class="info-key">TLS Version</div><div class="info-val"><span class="badge badge-good">{_esc(ssl.get("tls_version", "?"))}</span></div></div>
    <div class="info-row"><div class="info-key">Valid From</div><div class="info-val"><code>{_esc(ssl.get("not_before", "?"))}</code></div></div>
    <div class="info-row"><div class="info-key">Valid Until</div><div class="info-val"><code>{_esc(ssl.get("not_after", "?"))}</code></div></div>
  </div>
  <div class="ssl-meter">
    <div class="ssl-days" style="color:{dc}">{days}</div>
    <div class="ssl-days-lbl">days until expiry</div>
  </div>
</div>"""
    else:
        ssl_html = '<p style="color:var(--muted);font-family:var(--mono);font-size:13px">N/A — non-HTTPS site</p>'

    vuln_rows = (
        "".join(
            f"<tr><td>{_sev_badge(i['severity'])}</td><td>{_esc(i['issue'])}</td><td>{_esc(i.get('detail', ''))}</td></tr>"
            for i in issues
        )
        or "<tr><td colspan='3' style='text-align:center;color:#00e676'>No issues found ✓</td></tr>"
    )

    exposed = sec.get("exposed_paths", [])
    exp_rows = (
        "".join(
            f"<tr><td><code>{_esc(e['path'])}</code></td><td>"
            f"<span class='badge {'badge-bad' if e['status'] == 200 else 'badge-warn'}'>{e['status']}</span></td></tr>"
            for e in exposed
        )
        or "<tr><td colspan='2' style='color:#00e676'>None exposed ✓</td></tr>"
    )

    cookies = sec.get("cookies", [])
    ck_rows = (
        "".join(
            f"<tr><td><code>{_esc(c['name'])}</code></td><td>{_bool_badge(c['secure'])}</td>"
            f"<td>{_bool_badge(c['httponly'])}</td><td>{_esc(c.get('samesite', '?'))}</td></tr>"
            for c in cookies
        )
        or "<tr><td colspan='4' style='color:var(--muted)'>No cookies detected</td></tr>"
    )

    risk_cls = {
        "Critical": "alert-critical",
        "High": "alert-high",
        "Medium": "alert-medium",
    }.get(d["risk_level"], "alert-good")
    open_h, close_h = _section_shell("Security", css)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">🔒</div>
  <div><h1>Security Analysis</h1><div class="sub">{len(issues)} issues &bull; {d["risk_level"]} Risk</div></div>
  <div class="score-badge">
    <div class="score-num" style="color:{_score_color(score)}">{score}</div>
    <div class="score-lbl" style="color:{_score_color(score)}">{_score_label(score)}</div>
  </div>
</div>

<div class="alert {risk_cls}">
  <div class="alert-icon">{"🚨" if d["risk_level"] == "Critical" else "⚠️" if d["risk_level"] in ("High", "Medium") else "✅"}</div>
  <div>
    <div class="alert-title">{d["risk_level"]} Risk — {len(issues)} security issues detected</div>
    <div class="alert-sub">Score: {score}/100 &bull; CORS: {_esc(sec.get("cors", "Not Set"))}</div>
  </div>
</div>

<div class="section-label">HTTP Security Headers</div>
<div class="hdr-grid">{checks_html}</div>

<div class="section-label">SSL Certificate</div>
<div class="card">
  <div class="card-header"><div class="card-title">TLS / Certificate Details</div>
    {('<span class="badge badge-good">Valid</span>' if ssl.get("valid") else '<span class="badge badge-bad">Invalid / Error</span>') if ssl else ""}
  </div>
  <div class="card-body">{ssl_html}</div>
</div>

<div class="section-label">Vulnerability Table</div>
<div class="card"><div class="card-body" style="padding:0"><div class="table-wrap">
  <table><thead><tr><th>Severity</th><th>Issue</th><th>Recommendation</th></tr></thead>
  <tbody>{vuln_rows}</tbody></table>
</div></div></div>

<div class="section-label">Sensitive Path Probe</div>
<div class="card"><div class="card-body" style="padding:0"><div class="table-wrap">
  <table><thead><tr><th>Path</th><th>Status</th></tr></thead>
  <tbody>{exp_rows}</tbody></table>
</div></div></div>

<div class="section-label">Cookie Analysis</div>
<div class="card"><div class="card-body" style="padding:0"><div class="table-wrap">
  <table><thead><tr><th>Name</th><th>Secure</th><th>HttpOnly</th><th>SameSite</th></tr></thead>
  <tbody>{ck_rows}</tbody></table>
</div></div></div>
""" + close_h


def build_seo(d: dict) -> str:
    seo = d["seo"]
    issues = d["seo_issues"]
    score = d["seo_score"]
    tl = seo["title_len"]
    t_pct = min(100, int(tl / 60 * 100))
    t_color = "#00e676" if 30 <= tl <= 60 else "#ff3d57"
    ml = seo["meta_desc_len"]
    m_pct = min(100, int(ml / 160 * 100))
    m_color = "#00e676" if ml <= 160 else "#ff3d57"

    h1s = seo["headings"].get("h1", [])
    h_rows = ""
    for tag in ["h1", "h2", "h3", "h4", "h5", "h6"]:
        for txt in seo["headings"].get(tag, []):
            indent = (int(tag[1]) - 1) * 16
            h_rows += f'<div style="padding:6px 0 6px {indent}px;border-bottom:1px solid var(--border);font-size:12px;font-family:var(--mono)"><span style="font-size:9px;background:var(--surface2);border:1px solid var(--border2);border-radius:4px;padding:1px 5px;margin-right:8px">{tag.upper()}</span>{_esc(txt[:80])}</div>'

    og_items = (
        "".join(
            f'<div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px 14px;font-size:12px;font-family:var(--mono);margin:3px"><div style="color:var(--accent2);font-size:10px;margin-bottom:4px">{_esc(k)}</div><div>{_esc(v[:100])}</div></div>'
            for k, v in seo["og"].items()
        )
        or '<span class="badge badge-bad">No OpenGraph tags found</span>'
    )

    issue_li = (
        "".join(f'<li><span class="icon">⚠️</span>{_esc(x)}</li>' for x in issues)
        or '<li><span class="icon">✅</span>All checks passed</li>'
    )

    css = """
.cbar{flex:1;height:4px;background:var(--surface2);border-radius:99px;overflow:hidden}
.cfill{height:100%;border-radius:99px}
.cmeter{margin-top:8px;display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:11px;color:var(--muted)}
"""
    open_h, close_h = _section_shell("SEO", css)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">🔎</div>
  <div><h1>SEO Analysis</h1><div class="sub">{len(issues)} issues found</div></div>
  <div class="score-badge">
    <div class="score-num" style="color:{_score_color(score)}">{score}</div>
    <div class="score-lbl" style="color:{_score_color(score)}">{_score_label(score)}</div>
  </div>
</div>

<div class="section-label">Title &amp; Meta</div>
<div class="card">
  <div class="card-header"><div class="card-title">Page Title</div><span class="badge {"badge-good" if 30 <= tl <= 60 else "badge-bad"}">{tl} chars</span></div>
  <div class="card-body">
    <div style="font-size:14px;font-weight:700;color:var(--text);margin-bottom:8px">{_esc(seo["title"] or "(empty)")}</div>
    <div class="cmeter"><span>0</span><div class="cbar"><div class="cfill" style="width:{t_pct}%;background:{t_color}"></div></div><span>60</span></div>
  </div>
</div>
<div class="card">
  <div class="card-header"><div class="card-title">Meta Description</div><span class="badge {"badge-good" if ml <= 160 else "badge-bad"}">{ml} chars</span></div>
  <div class="card-body">
    <div style="font-size:13px;color:var(--muted);margin-bottom:8px;line-height:1.6">{_esc((seo["meta_desc"] or "(missing)")[:160])}</div>
    <div class="cmeter"><span>0</span><div class="cbar"><div class="cfill" style="width:{m_pct}%;background:{m_color}"></div></div><span>160</span></div>
  </div>
</div>

<div class="section-label">OpenGraph &amp; Social</div>
<div class="card">
  <div class="card-header"><div class="card-title">OpenGraph Tags</div>{_bool_badge(bool(seo["og"]))}</div>
  <div class="card-body"><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px">{og_items}</div></div>
</div>
<div class="card">
  <div class="card-header"><div class="card-title">Twitter Cards</div>{_bool_badge(bool(seo["twitter"]))}</div>
  <div class="card-body">{"".join(f"<div class='info-row'><div class='info-key'>{_esc(k)}</div><div class='info-val'>{_esc(v)}</div></div>" for k, v in seo["twitter"].items()) or '<span style="color:var(--muted);font-family:var(--mono);font-size:12px">No twitter: tags found</span>'}</div>
</div>

<div class="section-label">Heading Structure</div>
<div class="card">
  <div class="card-header"><div class="card-title">Heading Hierarchy</div>{_bool_badge(len(h1s) == 1, "✓ Valid", "⚠ Issue")}</div>
  <div class="card-body">{"<div>" + h_rows + "</div>" if h_rows else '<p style="color:var(--muted)">No headings found</p>'}</div>
</div>

<div class="section-label">Links &amp; Images</div>
<div class="grid-2">
  <div class="card">
    <div class="card-header"><div class="card-title">Link Analysis</div></div>
    <div class="card-body">
      <div class="info-row"><div class="info-key">Internal Links</div><div class="info-val"><span class="badge badge-info">{seo["internal_links"]}</span></div></div>
      <div class="info-row"><div class="info-key">External Links</div><div class="info-val"><span class="badge badge-info">{seo["external_links"]}</span></div></div>
      <div class="info-row"><div class="info-key">Canonical URL</div><div class="info-val">{_bool_badge(bool(seo["canonical"]))}</div></div>
      <div class="info-row"><div class="info-key">Structured Data</div><div class="info-val"><span class="badge badge-{"good" if seo["structured_data"] else "bad"}">{seo["structured_data"]} block(s)</span></div></div>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><div class="card-title">Image Audit</div></div>
    <div class="card-body">
      <div class="info-row"><div class="info-key">Total Images</div><div class="info-val">{seo["images_total"]}</div></div>
      <div class="info-row"><div class="info-key">Missing Alt Text</div><div class="info-val"><span class="badge {"badge-bad" if seo["images_no_alt"] else "badge-good"}">{seo["images_no_alt"]} images</span></div></div>
      <div class="info-row"><div class="info-key">Viewport Meta</div><div class="info-val">{_bool_badge(seo["viewport"])}</div></div>
    </div>
  </div>
</div>

<div class="section-label">Issues</div>
<div class="card"><div class="card-body"><ul class="issue-list">{issue_li}</ul></div></div>
""" + close_h


def build_performance(d: dict) -> str:
    perf = d["perf"]
    issues = d["perf_issues"]
    score = d["perf_score"]
    ttfb = perf["ttfb"]
    tc = "#00e676" if ttfb < 400 else "#ffab00" if ttfb < 800 else "#ff3d57"
    issue_li = (
        "".join(f'<li><span class="icon">⚠️</span>{_esc(x)}</li>' for x in issues)
        or '<li><span class="icon">✅</span>All checks passed</li>'
    )

    css = """
.wrow{display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px;font-family:var(--mono)}
.wrow:last-child{border-bottom:none}
.wname{width:140px;flex-shrink:0;color:var(--muted);font-size:11px}
.wbwrap{flex:1;height:18px;background:var(--surface2);border-radius:4px;overflow:hidden}
.wbar{height:100%;border-radius:4px;display:flex;align-items:center;padding:0 6px;font-size:9px;color:#fff;font-weight:700;min-width:30px}
.wtime{width:60px;text-align:right;color:var(--text)}
"""
    open_h, close_h = _section_shell("Performance", css, CHARTJS)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">⚡</div>
  <div><h1>Performance Analysis</h1><div class="sub">{len(issues)} issue(s) found</div></div>
  <div class="score-badge">
    <div class="score-num" style="color:{_score_color(score)}">{score}</div>
    <div class="score-lbl" style="color:{_score_color(score)}">{_score_label(score)}</div>
  </div>
</div>

<div class="grid-3" style="margin-bottom:20px">
  <div class="stat-card" style="--accent-color:{tc}"><div class="stat-val">{ttfb}</div><div class="stat-label">TTFB (ms)</div></div>
  <div class="stat-card" style="--accent-color:#00d4ff"><div class="stat-val">{perf["page_size_kb"]}</div><div class="stat-label">Page Size (KB)</div></div>
  <div class="stat-card" style="--accent-color:{"#00e676" if perf["compressed"] else "#ff3d57"}">
    <div class="stat-val">{"ON" if perf["compressed"] else "OFF"}</div><div class="stat-label">Compression</div></div>
</div>

<div class="section-label">Caching &amp; Compression</div>
<div class="grid-2">
  <div class="card">
    <div class="card-header"><div class="card-title">Compression</div>{_bool_badge(perf["compressed"])}</div>
    <div class="card-body">
      <div class="info-row"><div class="info-key">Content-Encoding</div><div class="info-val"><code>{_esc(perf["encoding"] or "None")}</code></div></div>
      <div class="info-row"><div class="info-key">Page Size</div><div class="info-val">{perf["page_size_kb"]} KB</div></div>
    </div>
  </div>
  <div class="card">
    <div class="card-header"><div class="card-title">Caching</div>{_bool_badge(bool(perf["cache_control"] or perf["etag"]))}</div>
    <div class="card-body">
      <div class="info-row"><div class="info-key">Cache-Control</div><div class="info-val"><code>{_esc(perf["cache_control"] or "Not Set")}</code></div></div>
      <div class="info-row"><div class="info-key">ETag</div><div class="info-val"><code>{_esc(perf["etag"] or "Not Set")}</code></div></div>
      <div class="info-row"><div class="info-key">Last-Modified</div><div class="info-val">{_esc(perf["last_modified"] or "Not Set")}</div></div>
    </div>
  </div>
</div>

<div class="section-label">Resource Counts</div>
<div class="card"><div class="card-body">
  <div class="info-row"><div class="info-key">Scripts</div><div class="info-val">{perf["scripts"]}</div></div>
  <div class="info-row"><div class="info-key">Stylesheets</div><div class="info-val">{perf["css"]}</div></div>
  <div class="info-row"><div class="info-key">Images</div><div class="info-val">{perf["images"]}</div></div>
</div></div>

<div class="section-label">Issues</div>
<div class="card"><div class="card-body"><ul class="issue-list">{issue_li}</ul></div></div>
""" + close_h


def build_accessibility(d: dict) -> str:
    a11y = d["a11y"]
    issues = d["a11y_issues"]
    score = d["a11y_score"]
    issue_li = (
        "".join(f'<li><span class="icon">⚠️</span>{_esc(x)}</li>' for x in issues)
        or '<li><span class="icon">✅</span>All checks passed</li>'
    )

    checks = [
        ("HTML lang attr", a11y["lang"]),
        ("Alt Text on Images", a11y["missing_alts"] == 0),
        ("Form Labels", a11y["unlabeled_inputs"] == 0),
        ("Empty Buttons", a11y["empty_buttons"] == 0),
    ]
    checks_html = ""
    for label, ok in checks:
        cls = "ok" if ok else "fail"
        icon = "✅" if ok else "❌"
        checks_html += f'<div class="hdr-check {cls}"><div class="icon">{icon}</div><div class="name">{label}</div></div>'

    css = """
.hdr-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:20px}
.hdr-check{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 12px;text-align:center;font-family:var(--mono)}
.hdr-check .icon{font-size:18px;margin-bottom:6px}
.hdr-check .name{font-size:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em}
.hdr-check.ok{border-color:rgba(0,230,118,.3);background:rgba(0,230,118,.05)}
.hdr-check.fail{border-color:rgba(255,61,87,.3);background:rgba(255,61,87,.05)}
"""
    open_h, close_h = _section_shell("Accessibility", css)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">♿</div>
  <div><h1>Accessibility</h1><div class="sub">{len(issues)} issues found</div></div>
  <div class="score-badge">
    <div class="score-num" style="color:{_score_color(score)}">{score}</div>
    <div class="score-lbl" style="color:{_score_color(score)}">{_score_label(score)}</div>
  </div>
</div>

<div class="section-label">Quick Checks</div>
<div class="hdr-grid">{checks_html}</div>

<div class="section-label">ARIA &amp; Semantic Usage</div>
<div class="card"><div class="card-body">
  <div class="info-row"><div class="info-key">HTML lang attr</div><div class="info-val">{_bool_badge(a11y["lang"])}</div></div>
  <div class="info-row"><div class="info-key">aria-label attrs</div><div class="info-val">{a11y["aria_labels"]}</div></div>
  <div class="info-row"><div class="info-key">role attrs</div><div class="info-val">{a11y["roles"]}</div></div>
  <div class="info-row"><div class="info-key">Unlabeled Inputs</div><div class="info-val"><span class="badge {"badge-bad" if a11y["unlabeled_inputs"] else "badge-good"}">{a11y["unlabeled_inputs"]}</span></div></div>
  <div class="info-row"><div class="info-key">Empty Buttons</div><div class="info-val"><span class="badge {"badge-bad" if a11y["empty_buttons"] else "badge-good"}">{a11y["empty_buttons"]}</span></div></div>
  <div class="info-row"><div class="info-key">Images w/o Alt</div><div class="info-val"><span class="badge {"badge-bad" if a11y["missing_alts"] else "badge-good"}">{a11y["missing_alts"]}</span></div></div>
</div></div>

<div class="section-label">Issues</div>
<div class="card"><div class="card-body"><ul class="issue-list">{issue_li}</ul></div></div>
""" + close_h


def build_technologies(d: dict) -> str:
    techs = d["techs"]
    cards = ""
    icon_map = {
        "CDN": "☁️",
        "Web Server": "🖥️",
        "Language": "🐘",
        "Framework": "🚀",
        "Runtime": "🟢",
        "Frontend": "⚛️",
    }
    for t in techs:
        icon = icon_map.get(t["cat"], "🧩")
        cards += f"""<div class="tech-card">
  <div class="tc-icon">{icon}</div>
  <div class="tc-name">{_esc(t["name"])}</div>
  <div class="tc-cat">{_esc(t["cat"])}</div>
  <div class="tc-how"><span class="detect-src">via {_esc(t["via"])}</span></div>
</div>"""

    if not techs:
        cards = '<p style="color:var(--muted);font-family:var(--mono);font-size:13px">No technologies detected.</p>'

    css = """
.tech-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:14px;margin-bottom:20px}
.tech-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:18px;display:flex;flex-direction:column;gap:8px;transition:border-color .2s,transform .2s}
.tech-card:hover{border-color:var(--border2);transform:translateY(-2px)}
.tc-icon{font-size:26px}
.tc-name{font-size:14px;font-weight:700;color:var(--text)}
.tc-cat{font-size:10px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.1em;color:var(--muted)}
.tc-how{font-size:11px;color:var(--muted);font-family:var(--mono);background:var(--surface2);border:1px solid var(--border);border-radius:5px;padding:4px 8px;margin-top:4px}
.detect-src{color:var(--accent2)}
"""
    open_h, close_h = _section_shell("Technologies", css)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">🧩</div>
  <div><h1>Technology Stack</h1><div class="sub">{
            len(techs)
        } technologies detected via headers &amp; HTML patterns</div></div>
</div>

<div class="section-label">Detected Technologies</div>
<div class="tech-grid">{cards}</div>

<div class="section-label">Server Headers Evidence</div>
<div class="card"><div class="card-body" style="padding:0"><div class="table-wrap">
  <table><thead><tr><th>Header</th><th>Value</th></tr></thead><tbody>
    {
            "".join(
                f"<tr><td><code>{_esc(k)}</code></td><td>{_esc(d['headers'].get(k, ''))}</td></tr>"
                for k in ["Server", "X-Powered-By", "Via", "X-Generator"]
                if k in d["headers"]
            )
            or "<tr><td colspan='2' style='color:var(--muted)'>No identifying headers found</td></tr>"
        }
  </tbody></table>
</div></div></div>
""" + close_h


def build_dns(d: dict) -> str:
    dns = d["dns"]
    if "note" in dns:
        dns_table = f'<p style="color:var(--muted);font-family:var(--mono);font-size:13px">{_esc(dns["note"])}</p>'
    else:
        type_cls = {"A": "", "MX": "mx", "TXT": "txt", "NS": "ns", "CNAME": "cname"}
        rows = (
            "".join(
                f'<tr><td><span class="dns-type {type_cls.get(rt, "")}">{rt}</span></td><td><code>{_esc(v)}</code></td></tr>'
                for rt, vals in dns.items()
                if rt != "cdn" and isinstance(vals, list)
                for v in vals
            )
            or "<tr><td colspan='2' style='color:var(--muted)'>No DNS records retrieved</td></tr>"
        )
        dns_table = f"<div class='table-wrap'><table><thead><tr><th>Type</th><th>Value</th></tr></thead><tbody>{rows}</tbody></table></div>"

    css = """
.dns-type{display:inline-block;font-family:var(--mono);font-size:10px;font-weight:700;padding:2px 7px;border-radius:4px;background:rgba(0,212,255,.1);color:var(--accent);border:1px solid rgba(0,212,255,.25);min-width:44px;text-align:center}
.dns-type.mx{background:rgba(124,92,252,.1);color:var(--accent2);border-color:rgba(124,92,252,.25)}
.dns-type.txt{background:rgba(255,171,0,.1);color:#ffab00;border-color:rgba(255,171,0,.25)}
.dns-type.ns{background:rgba(0,230,118,.1);color:var(--good);border-color:rgba(0,230,118,.25)}
.dns-type.cname{background:rgba(255,100,50,.1);color:#ff7043;border-color:rgba(255,100,50,.25)}
"""
    open_h, close_h = _section_shell("DNS & Infrastructure", css)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">🌍</div>
  <div><h1>DNS &amp; Infrastructure</h1><div class="sub">Network configuration &amp; hosting details</div></div>
</div>

<div class="grid-3" style="margin-bottom:20px">
  <div class="stat-card" style="--accent-color:#00d4ff"><div class="stat-val" style="font-size:18px">{_esc(dns.get("cdn", "None"))}</div><div class="stat-label">CDN Provider</div></div>
  <div class="stat-card" style="--accent-color:#00e676"><div class="stat-val" style="font-size:18px">{_esc(d["ip"])}</div><div class="stat-label">IP Address</div></div>
  <div class="stat-card" style="--accent-color:#7c5cfc"><div class="stat-val" style="font-size:18px">{_esc(d["scheme"].upper())}</div><div class="stat-label">Protocol</div></div>
</div>

<div class="section-label">CDN Detection</div>
<div class="card">
  <div class="card-header"><div class="card-title">Content Delivery Network</div>
    <span class="badge {"badge-good" if dns.get("cdn") != "None" else "badge-warn"}">{_esc(dns.get("cdn", "None"))}</span>
  </div>
  <div class="card-body">
    <div class="info-row"><div class="info-key">Detected CDN</div><div class="info-val"><span class="tech-tag">{_esc(dns.get("cdn", "None"))}</span></div></div>
    <div class="info-row"><div class="info-key">Detection Method</div><div class="info-val">HTTP response headers</div></div>
  </div>
</div>

<div class="section-label">DNS Records</div>
<div class="card"><div class="card-body" style="padding:0">{dns_table}</div></div>
""" + close_h


def build_screenshots(d: dict) -> str:
    has_ss = bool(d["desktop_b64"] or d["mobile_b64"])
    if has_ss:
        ss_html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:20px">'
        if d["desktop_b64"]:
            ss_html += f'<div><div style="font-size:11px;font-family:var(--mono);color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em">Desktop — 1280×800</div><img src="data:image/png;base64,{d["desktop_b64"]}" style="max-width:100%;border-radius:8px;border:1px solid var(--border)"></div>'
        if d["mobile_b64"]:
            ss_html += f'<div><div style="font-size:11px;font-family:var(--mono);color:var(--muted);margin-bottom:8px;text-transform:uppercase;letter-spacing:.06em">Mobile — iPhone 12</div><img src="data:image/png;base64,{d["mobile_b64"]}" style="max-width:100%;border-radius:8px;border:1px solid var(--border)"></div>'
        ss_html += "</div>"
    else:
        ss_html = """<div style="background:var(--surface2);border:2px dashed var(--border2);border-radius:12px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:60px 40px;text-align:center;gap:12px">
  <div style="font-size:48px;opacity:.4">📸</div>
  <div style="font-size:15px;font-weight:700;color:var(--muted)">Screenshots Unavailable</div>
  <div style="font-size:12px;color:var(--muted);font-family:var(--mono);line-height:1.6">Install Playwright to enable:<br><br>pip install playwright Pillow<br>playwright install chromium</div>
</div>"""
    open_h, close_h = _section_shell("Screenshots")
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">📸</div>
  <div><h1>Screenshots</h1><div class="sub">Visual rendering — desktop &amp; mobile</div></div>
  {'<span class="badge badge-good">Captured</span>' if has_ss else '<span class="badge badge-warn">Playwright not installed</span>'}
</div>

<div class="section-label">Visual Captures</div>
<div class="card"><div class="card-body">{ss_html}</div></div>

<div class="section-label">Configuration</div>
<div class="card"><div class="card-body">
  <div class="info-row"><div class="info-key">Desktop Size</div><div class="info-val">1280 × 800 px</div></div>
  <div class="info-row"><div class="info-key">Mobile Device</div><div class="info-val">iPhone 12 emulation</div></div>
  <div class="info-row"><div class="info-key">Wait Strategy</div><div class="info-val"><code>networkidle</code></div></div>
  <div class="info-row"><div class="info-key">Format</div><div class="info-val">PNG (embedded base64)</div></div>
  <div class="info-row"><div class="info-key">Playwright</div><div class="info-val">{_bool_badge(HAS_PLAYWRIGHT)}</div></div>
</div></div>
""" + close_h


def build_charts(d: dict) -> str:
    sc = d["security_score"]
    seo = d["seo_score"]
    pc = d["perf_score"]
    ac = d["a11y_score"]
    ov = d["overall_score"]
    data = json.dumps(
        {
            "scores": [sc, seo, pc, ac],
            "issues": [
                len(d["sec_issues"]),
                len(d["seo_issues"]),
                len(d["perf_issues"]),
                len(d["a11y_issues"]),
            ],
            "overall": ov,
            "sec_headers": [
                int(d["sec"].get("https", False)),
                int(d["sec"].get("hsts", False)),
                int(d["sec"].get("csp", False)),
                int(d["sec"].get("xframe", False)),
                int(d["sec"].get("ref", False)),
                int(d["sec"].get("xcto", False)),
                int(d["sec"].get("perms", False)),
                int(d["sec"].get("xxss", False)),
            ],
        }
    )
    css = """
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
.chart-box{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px}
.chart-box-title{font-size:11px;font-family:var(--mono);text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin-bottom:16px}
.chart-box canvas{max-height:240px}
.score-line{display:flex;align-items:center;gap:14px;font-size:13px;margin-bottom:10px}
.score-line .sname{width:120px;flex-shrink:0;font-family:var(--mono);font-size:11px;color:var(--muted)}
.score-line .bwrap{flex:1;height:20px;background:var(--surface2);border-radius:6px;overflow:hidden}
.score-line .bfill{height:100%;border-radius:6px;display:flex;align-items:center;padding:0 8px;font-size:11px;font-weight:700;color:#fff;font-family:var(--mono)}
.score-line .bnum{width:36px;text-align:right;font-family:var(--mono);font-weight:700;font-size:13px}
"""
    score_bars = ""
    for name, score in [
        ("Security", sc),
        ("SEO", seo),
        ("Performance", pc),
        ("Accessibility", ac),
        ("Overall", ov),
    ]:
        cc = _score_color(score)
        score_bars += f'<div class="score-line"><div class="sname">{name}</div><div class="bwrap"><div class="bfill" style="width:{score}%;background:{cc}">{score}</div></div><div class="bnum" style="color:{cc}">{score}</div></div>'

    open_h, close_h = _section_shell("Charts", css, CHARTJS)
    return open_h + f"""
<div class="page-header">
  <div class="page-header-icon">📈</div>
  <div><h1>Score Charts</h1><div class="sub">Visual overview of all dimensions</div></div>
</div>

<div class="section-label">Score Bars</div>
<div class="card"><div class="card-body">{score_bars}</div></div>

<div class="chart-grid">
  <div class="chart-box"><div class="chart-box-title">Radar — All Dimensions</div><canvas id="radarChart"></canvas></div>
  <div class="chart-box"><div class="chart-box-title">Issues by Category</div><canvas id="issueChart"></canvas></div>
</div>
<div class="chart-grid">
  <div class="chart-box"><div class="chart-box-title">Issue Severity Mix</div><canvas id="sevChart"></canvas></div>
  <div class="chart-box"><div class="chart-box-title">Security Header Compliance</div><canvas id="secChart"></canvas></div>
</div>

<script>
const cd = {data};
const F={{family:'JetBrains Mono',size:11}};
const G='#1e2a38'; const T='#4e6070';
const COLORS=cd.scores.map(s=>s>=80?'#00e676':s>=60?'#ffab00':s>=40?'#ff7043':'#ff3d57');
const NAMES=['Security','SEO','Performance','Accessibility'];
new Chart(document.getElementById('radarChart'),{{type:'radar',data:{{labels:NAMES,datasets:[{{label:'Score',data:cd.scores,backgroundColor:'rgba(0,212,255,0.1)',borderColor:'#00d4ff',pointBackgroundColor:COLORS,pointBorderColor:'#fff',pointRadius:5,borderWidth:2}}]}},options:{{responsive:true,scales:{{r:{{min:0,max:100,ticks:{{stepSize:25,color:T,backdropColor:'transparent',font:F}},grid:{{color:G}},angleLines:{{color:G}},pointLabels:{{color:'#d4dfe8',font:{{...F,size:12,weight:'700'}}}}  }}}},plugins:{{legend:{{display:false}}}}}}}});
new Chart(document.getElementById('issueChart'),{{type:'bar',data:{{labels:NAMES,datasets:[{{data:cd.issues,backgroundColor:['rgba(255,61,87,.6)','rgba(255,171,0,.6)','rgba(0,230,118,.6)','rgba(124,92,252,.6)'],borderColor:['#ff3d57','#ffab00','#00e676','#7c5cfc'],borderWidth:1,borderRadius:6}}]}},options:{{responsive:true,plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:G}},ticks:{{color:T,font:F}}}},y:{{grid:{{color:G}},ticks:{{color:T,font:F}},beginAtZero:true}}}}}}}});
const sevLabels=['Critical','High','Medium','Low'];
const sevCounts=[{{}},{{}},{{}},{{}}];
// approximate severity counts from total issues
new Chart(document.getElementById('sevChart'),{{type:'doughnut',data:{{labels:sevLabels,datasets:[{{data:[0,cd.issues[0],cd.issues[1]+cd.issues[3],cd.issues[2]],backgroundColor:['rgba(220,38,38,.7)','rgba(255,61,87,.7)','rgba(255,171,0,.7)','rgba(0,212,255,.7)'],borderColor:['#dc2626','#ff3d57','#ffab00','#00d4ff'],borderWidth:1}}]}},options:{{responsive:true,cutout:'55%',plugins:{{legend:{{position:'right',labels:{{color:'#d4dfe8',font:F,padding:10}}}}}}}}}});
new Chart(document.getElementById('secChart'),{{type:'bar',data:{{labels:['HTTPS','HSTS','CSP','X-Frame','Referrer','X-CTO','Perms','XSS'],datasets:[{{data:cd.sec_headers,backgroundColor:cd.sec_headers.map(v=>v?'rgba(0,230,118,.6)':'rgba(255,61,87,.4)'),borderColor:cd.sec_headers.map(v=>v?'#00e676':'#ff3d57'),borderWidth:1,borderRadius:4}}]}},options:{{responsive:true,indexAxis:'y',plugins:{{legend:{{display:false}}}},scales:{{x:{{grid:{{color:G}},ticks:{{color:T,font:F}},max:1}},y:{{grid:{{color:G}},ticks:{{color:T,font:{{...F,size:10}}}}}}}}  }}}});
</script>
""" + close_h


# ══════════════════════════════════════════════════════════════════════════════
#  INDEX (SPA SHELL)
# ══════════════════════════════════════════════════════════════════════════════

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>WebAnalyzer — {domain}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Syne:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{{box-sizing:border-box;margin:0;padding:0}}
:root{{--bg:#080b10;--surface:#0e1319;--surface2:#141b24;--border:#1e2a38;--border2:#263040;--text:#d4dfe8;--muted:#4e6070;--accent:#00d4ff;--accent2:#7c5cfc;--good:#00e676;--warn:#ffab00;--danger:#ff3d57;--mono:'JetBrains Mono',monospace;--sans:'Syne',sans-serif}}
html,body{{height:100%;overflow:hidden}}
body{{background:var(--bg);color:var(--text);font-family:var(--sans);display:flex}}
.sidebar{{width:220px;min-height:100vh;background:var(--surface);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0;position:relative;z-index:10}}
.sidebar::after{{content:'';position:absolute;top:0;right:-1px;bottom:0;width:1px;background:linear-gradient(180deg,var(--accent) 0%,transparent 40%,var(--accent2) 100%);opacity:.4}}
.brand{{padding:24px 20px 20px;border-bottom:1px solid var(--border)}}
.brand-icon{{width:36px;height:36px;background:linear-gradient(135deg,var(--accent),var(--accent2));border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:18px;margin-bottom:10px;box-shadow:0 0 20px rgba(0,212,255,.3)}}
.brand-name{{font-size:13px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:var(--text)}}
.brand-sub{{font-size:10px;color:var(--muted);margin-top:2px;font-family:var(--mono)}}
.nav{{flex:1;padding:12px 0;overflow-y:auto}}
.nav-group-label{{padding:14px 20px 6px;font-size:9px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);font-family:var(--mono)}}
.nav-item{{display:flex;align-items:center;gap:10px;padding:9px 20px;font-size:12.5px;font-weight:600;color:var(--muted);cursor:pointer;position:relative;transition:color .2s,background .2s;border:none;background:none;width:100%;text-align:left;border-left:2px solid transparent;letter-spacing:.01em}}
.nav-item:hover{{color:var(--text);background:var(--surface2)}}
.nav-item.active{{color:var(--accent);background:rgba(0,212,255,.06);border-left-color:var(--accent)}}
.nav-item .ico{{width:18px;text-align:center;font-size:14px;flex-shrink:0}}
.nav-item .nb{{margin-left:auto;font-family:var(--mono);font-size:9px;background:var(--surface2);border:1px solid var(--border2);color:var(--muted);padding:1px 5px;border-radius:4px}}
.nav-item.active .nb{{border-color:rgba(0,212,255,.3);color:var(--accent)}}
.sidebar-footer{{padding:14px 20px;border-top:1px solid var(--border);font-family:var(--mono);font-size:10px;color:var(--muted)}}
.dot{{display:inline-block;width:6px;height:6px;background:var(--good);border-radius:50%;margin-right:6px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.3}}}}
.panel{{flex:1;height:100vh;overflow:hidden;position:relative;background:var(--bg)}}
.loader{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;background:var(--bg);z-index:5;opacity:0;pointer-events:none;transition:opacity .2s}}
.loader.visible{{opacity:1;pointer-events:all}}
.loader-ring{{width:40px;height:40px;border:2px solid var(--border2);border-top-color:var(--accent);border-radius:50%;animation:spin .7s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.loader-text{{margin-top:14px;font-family:var(--mono);font-size:11px;color:var(--muted)}}
#content-frame{{width:100%;height:100%;border:none;opacity:0;transition:opacity .3s}}
#content-frame.loaded{{opacity:1}}
.welcome{{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16px;padding:40px}}
.wglow{{width:120px;height:120px;background:radial-gradient(circle,rgba(0,212,255,.15),transparent 70%);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:52px}}
.welcome h2{{font-size:22px;font-weight:800;color:var(--text);text-align:center}}
.welcome p{{font-size:13px;color:var(--muted);text-align:center;max-width:340px;line-height:1.6}}
.grid-bg{{position:fixed;inset:0;background-image:linear-gradient(var(--border) 1px,transparent 1px),linear-gradient(90deg,var(--border) 1px,transparent 1px);background-size:40px 40px;opacity:.15;pointer-events:none}}
.domain-chip{{background:var(--surface2);border:1px solid var(--border2);border-radius:6px;padding:6px 12px;font-size:11px;font-family:var(--mono);color:var(--accent);margin-top:8px}}
.score-chip{{background:rgba(0,212,255,.08);border:1px solid rgba(0,212,255,.2);border-radius:6px;padding:4px 10px;font-size:12px;font-family:var(--mono);color:var(--accent);font-weight:700}}
</style>
</head>
<body>
<div class="grid-bg"></div>
<aside class="sidebar">
  <div class="brand">
    <div class="brand-icon">🔍</div>
    <div class="brand-name">WebAnalyzer</div>
    <div class="brand-sub">{domain}</div>
  </div>
  <nav class="nav">
    <div class="nav-group-label">Overview</div>
    <button class="nav-item" data-section="summary"><span class="ico">📊</span>Summary</button>
    <button class="nav-item" data-section="siteinfo"><span class="ico">🌐</span>Site Info</button>
    <div class="nav-group-label">Analysis</div>
    <button class="nav-item" data-section="security"><span class="ico">🔒</span>Security<span class="nb">SEC</span></button>
    <button class="nav-item" data-section="seo"><span class="ico">🔎</span>SEO<span class="nb">SEO</span></button>
    <button class="nav-item" data-section="performance"><span class="ico">⚡</span>Performance<span class="nb">PERF</span></button>
    <button class="nav-item" data-section="accessibility"><span class="ico">♿</span>Accessibility<span class="nb">A11Y</span></button>
    <div class="nav-group-label">Stack</div>
    <button class="nav-item" data-section="technologies"><span class="ico">🧩</span>Technologies</button>
    <button class="nav-item" data-section="dns"><span class="ico">🌍</span>DNS &amp; Infra</button>
    <div class="nav-group-label">Visuals</div>
    <button class="nav-item" data-section="screenshots"><span class="ico">📸</span>Screenshots</button>
    <button class="nav-item" data-section="charts"><span class="ico">📈</span>Charts</button>
  </nav>
  <div class="sidebar-footer"><span class="dot"></span>Passive Scan &bull; {scan_time}</div>
</aside>
<div class="panel" id="panel">
  <div class="welcome" id="welcome">
    <div class="wglow">🔍</div>
    <h2>Report Ready</h2>
    <p>Select a section from the sidebar to view its detailed analysis.</p>
    <div class="domain-chip">{domain}</div>
    <div class="score-chip">Overall Score: {overall_score}/100</div>
  </div>
  <div class="loader" id="loader"><div class="loader-ring"></div><div class="loader-text">Loading…</div></div>
  <iframe id="content-frame" title="Section Content"></iframe>
</div>
<script>
const navItems=document.querySelectorAll('.nav-item[data-section]');
const frame=document.getElementById('content-frame');
const loader=document.getElementById('loader');
const welcome=document.getElementById('welcome');
let current=null;
function loadSection(id){{
  if(id===current)return; current=id;
  navItems.forEach(n=>n.classList.toggle('active',n.dataset.section===id));
  welcome.style.display='none';
  loader.classList.add('visible');
  frame.classList.remove('loaded');
  frame.src='sections/'+id+'.html';
}}
frame.addEventListener('load',()=>{{loader.classList.remove('visible');frame.classList.add('loaded')}});
navItems.forEach(btn=>btn.addEventListener('click',()=>loadSection(btn.dataset.section)));
document.addEventListener('keydown',e=>{{
  const S=['summary','siteinfo','security','seo','performance','accessibility','technologies','dns','screenshots','charts'];
  const i=S.indexOf(current);
  if(e.key==='ArrowDown'&&i<S.length-1)loadSection(S[i+1]);
  if(e.key==='ArrowUp'&&i>0)loadSection(S[i-1]);
}});
loadSection('summary');
</script>
</body>
</html>
"""


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════


def webReport(
    url: str, out_dir: str = None, delay: int = 0, open_report: bool = True
) -> tuple[str, dict]:
    """
    Scan url and write the multi-section SPA report to out_dir.

    Returns (index_path, summary_dict).
    """
    if out_dir is None:
        out_dir = os.path.join(os.path.expanduser("~"), "Downloads", "WebReport")
    else:
        out_dir = os.path.expanduser(out_dir)

    base = Path(out_dir)
    sections = base / "sections"
    assets = base / "assets"
    for d in (base, sections, assets):
        d.mkdir(parents=True, exist_ok=True)

    # Run scan
    data = run_scan(url, delay)

    # Write shared CSS
    (assets / "shared.css").write_text(SHARED_CSS, encoding="utf-8")
    log.info("Wrote shared.css")

    # Write each section
    builders = {
        "summary": build_summary,
        "siteinfo": build_siteinfo,
        "security": build_security,
        "seo": build_seo,
        "performance": build_performance,
        "accessibility": build_accessibility,
        "technologies": build_technologies,
        "dns": build_dns,
        "screenshots": build_screenshots,
        "charts": build_charts,
    }
    for name, builder in builders.items():
        html = builder(data)
        path = sections / f"{name}.html"
        path.write_text(html, encoding="utf-8")
        log.info("Wrote sections/%s.html", name)

    # Write index
    index_html = INDEX_HTML.format(
        domain=_esc(data["domain"]),
        scan_time=_esc(data["scan_time"]),
        overall_score=data["overall_score"],
    )
    index_path = base / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    log.info("Wrote index.html")

    # Summary JSON
    summary = {
        "domain": data["domain"],
        "ip": data["ip"],
        "overall_score": data["overall_score"],
        "security_score": data["security_score"],
        "seo_score": data["seo_score"],
        "performance_score": data["perf_score"],
        "accessibility_score": data["a11y_score"],
        "risk_level": data["risk_level"],
        "technologies": [t["name"] for t in data["techs"]],
        "issues_total": len(data["sec_issues"])
        + len(data["seo_issues"])
        + len(data["perf_issues"])
        + len(data["a11y_issues"]),
        "cdn": data["dns"].get("cdn", "None"),
        "https": data["sec"].get("https", False),
        "report_path": str(index_path.resolve()),
        "scan_time": data["scan_time"],
    }
    (base / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log.info("Wrote summary.json")

    print(f"\n✅  Report ready → {index_path.resolve()}")
    print(
        f"📊  Overall score : {summary['overall_score']}/100  ({summary['risk_level']} risk)"
    )
    print(f"🔍  Domain        : https://{summary['domain']}")
    print(f"⚠️   Issues found  : {summary['issues_total']}")

    if open_report:
        webbrowser.open(f"{index_path.resolve()}")

    return str(index_path.resolve()), summary


# ══════════════════════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Passive web report generator")
    parser.add_argument("url", help="Target URL, e.g. https://example.com")
    parser.add_argument(
        "--out", default=None, help="Output directory (default: ~/Downloads/WebReport)"
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Delay in seconds before scanning (useful for page load/server start)",
    )
    args = parser.parse_args()

    path, info = webReport(args.url, args.out, args.delay)
    print("\n📋 Summary:")
    for k, v in info.items():
        print(f"   {k}: {v}")
