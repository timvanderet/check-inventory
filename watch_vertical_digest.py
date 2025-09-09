# pip install requests beautifulsoup4
import os, time, re, json, smtplib, requests, sys
from bs4 import BeautifulSoup
from email.message import EmailMessage
from pathlib import Path

# ===== CONFIG =====
# Keep your own three color pages here. If you already set these, leave them as-is.
# Example:
# PRODUCTS = [
#     {"name": "Beige 8-Pack", "url": "https://cheappegboard.com/..."},
#     {"name": "Grey 8-Pack",  "url": "https://cheappegboard.com/..."},
#     {"name": "White 8-Pack", "url": "https://cheappegboard.com/..."},
# ]
PRODUCTS = [
    {"name": "Beige 8-Pack",  "url": "https://cheappegboard.com/copy-of-8-pack-of-pegboard-scratch-dent-wall-control-16in-w-x-32in-t-pink-metal-pegboard/"},
    {"name": "Grey 8-pack",     "url": "https://cheappegboard.com/copy-of-8-pack-of-pegboard-scratch-dent-wall-control-16in-w-x-32in-t-white-metal-pegboard-1/"},
    {"name": "White 8-pack",     "url": "https://cheappegboard.com/copy-of-8-pack-of-pegboard-scratch-dent-wall-control-16in-w-x-32in-t-black-metal-pegboard/"},
]

VERTICAL_MATCH = "Vertical"

# Read email settings from environment (NO hard-coded secrets)
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = os.environ.get("SMTP_USER")              # required
SMTP_PASS = os.environ.get("SMTP_PASS")              # required (Gmail App Password)
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USER) # optional; defaults to SMTP_USER
EMAIL_TO = os.environ.get("EMAIL_TO", SMTP_USER or "")  # optional; defaults to SMTP_USER
RECIPIENTS = [e.strip() for e in EMAIL_TO.split(",") if e.strip()]

# Networking
HEADERS = {"User-Agent": "Mozilla/5.0 (stock-watcher)"}
TIMEOUT = 20
RETRIES = 2

# ===== LOGIC =====

def log(msg: str):
    print(msg, flush=True)

def http_get(url: str) -> str:
    last_err = None
    for _ in range(RETRIES):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            log(f"[HTTP] {url} -> {r.status_code}, {len(r.text)} bytes")
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            log(f"[HTTP] retry after error: {e}")
            time.sleep(2)
    raise last_err

def extract_instock_ids(html: str) -> set[int]:
    # BigCommerce injects: updateProductDetails({... "inStockAttributeValues":[78], ...});
    blocks = re.findall(r'updateProductDetails\((\{.*?\})\);', html, flags=re.S)
    if not blocks:
        log("[PARSE] updateProductDetails block NOT found")
        return set()
    data = json.loads(blocks[-1])
    raw = data.get("inStockAttributeValues", [])
    ids = set()
    for x in raw:
        sx = str(x)
        if sx.isdigit():
            ids.add(int(sx))
    log(f"[PARSE] inStockAttributeValues = {sorted(ids)}")
    return ids

def extract_option_map(html: str) -> dict[int, str]:
    soup = BeautifulSoup(html, "html.parser")
    opts: dict[int, str] = {}
    for sel in soup.select(".productAttributeList select"):
        for o in sel.select("option"):
            v = (o.get("value") or "").strip()
            if v.isdigit():
                opts[int(v)] = o.get_text(strip=True)
    log(f"[PARSE] options = {opts}")
    return opts

def vertical_status(html: str) -> tuple[bool, str]:
    ids_in_stock = extract_instock_ids(html)
    options = extract_option_map(html)
    label = "Vertical"
    in_stock = False
    for vid, text in options.items():
        if VERTICAL_MATCH.lower() in text.lower():
            label = text
            in_stock = vid in ids_in_stock
            break
    return in_stock, label

def build_digest(rows: list[dict]) -> str:
    lines = ["Pegboard Vertical status:\n"]
    for r in rows:
        status = "IN STOCK ✅" if r["status"] else "Out of stock ❌"
        lines.append(f"• {r['name']}: {status}\n  Option: {r['label']}\n  {r['url']}")
    return "\n".join(lines)

def send_email(subject: str, body: str):
    if not SMTP_USER or not SMTP_PASS:
        raise RuntimeError("Missing SMTP_USER or SMTP_PASS env vars.")
    if not RECIPIENTS:
        raise RuntimeError("EMAIL_TO missing/empty (set EMAIL_TO or rely on SMTP_USER).")

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = ", ".join(RECIPIENTS)
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
    log("[EMAIL] Sent OK")

def main():
    rows = []
    for item in PRODUCTS:
        name, url = item["name"], item["url"]
        try:
            html = http_get(url)
            ok, label = vertical_status(html)
            rows.append({"name": name, "url": url, "label": label, "status": ok})
            log(f"[STATUS] {name}: {'IN STOCK' if ok else 'Out of stock'} ({label})")
        except Exception as e:
            rows.append({"name": name, "url": url, "label": "Vertical", "status": False})
            log(f"[ERROR] {name}: {e}")

    body = build_digest(rows)
    log("\n===== DIGEST =====\n" + body + "\n==================\n")
    send_email("Pegboard Vertical — Status", body)

if __name__ == "__main__":
    main()
