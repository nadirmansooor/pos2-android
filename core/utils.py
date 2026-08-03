# ============================================================================
#  UTILS - date, money, helpers (pure stdlib - offline, fast)
# ============================================================================
import datetime
import os
import sys
import webbrowser


# Jameel Noori Nastaleeq for EVERY html page we hand to the browser: the
# @font-face file URL loads the bundled font even when it is not installed
# system-wide (silent fallback to Arial if the file is missing).
_TTF_PATH = os.path.abspath(os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "assets", "fonts",
    "jameel-noori.ttf")).replace(os.sep, "/").replace(" ", "%20")
JAMEEL_FACE = ("@font-face{font-family:'Jameel Noori Nastaleeq';"
               "src:url('file:///" + _TTF_PATH + "') format('truetype');}")


def today():
    return datetime.date.today().isoformat()


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def this_month():
    return datetime.date.today().strftime("%Y-%m")


def add_days(iso, days):
    return (datetime.date.fromisoformat(iso) +
            datetime.timedelta(days=days)).isoformat()


def days_between(iso1, iso2):
    return (datetime.date.fromisoformat(iso2) -
            datetime.date.fromisoformat(iso1)).days


def money(x):
    try:
        return f"{float(x):,.2f}"
    except Exception:
        return "0.00"


def money0(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "0"


def to_float(txt, default=0.0):
    try:
        return float(str(txt).replace(",", "").strip())
    except Exception:
        return default


def to_int(txt, default=0):
    try:
        return int(float(str(txt).replace(",", "").strip()))
    except Exception:
        return default


def wa_digits(phone):
    """Local phone -> international digits for wa.me (Pakistan default)."""
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    if d.startswith("0092"):
        d = d[2:]
    if d.startswith("0"):
        d = "92" + d[1:]
    if len(d) == 10:                    # 3xxxxxxxxx -> 923xxxxxxxxx
        d = "92" + d
    return d


def open_whatsapp(phone, text):
    """Open WhatsApp (app/browser) with a READY-TO-SEND message for one
    customer. One-way, user presses Send themselves - fully safe."""
    import urllib.parse
    d = wa_digits(phone)
    if not d:
        return False
    try:
        webbrowser.open("https://wa.me/" + d + "?text=" +
                        urllib.parse.quote(text or ""))
        return True
    except Exception:
        return False


def open_file(path):
    """Open a file in the browser/viewer (the print-preview lane).
    Windows gets TWO honest attempts - the shell association first, the
    browser layer right behind it - because a silent no-open once left a
    shopkeeper clicking PRINT into thin air. Returns True/False so the
    caller can SPEAK the saved path when even this fails."""
    try:
        if sys.platform.startswith("win"):
            try:
                os.startfile(path)  # noqa
                return True
            except Exception:
                pass
            try:
                return bool(webbrowser.open("file://" +
                                            os.path.abspath(path)))
            except Exception:
                return False
        if sys.platform == "darwin":
            import subprocess
            subprocess.Popen(["open", path])
            return True
        return bool(webbrowser.open("file://" + os.path.abspath(path)))
    except Exception:
        return False


def html_page(title, body):
    return ("<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<title>{title}</title>"
            "<style>" + JAMEEL_FACE +
            "body{font-family:'Jameel Noori Nastaleeq',Arial;"
            "margin:10mm;color:#222}"
            "h2{color:#123350;margin:0 0 2px}"
            "table{border-collapse:collapse;width:100%;margin-top:8px}"
            "th{background:#123350;color:#fff;padding:7px 6px;font-size:13px;text-align:left}"
            "td{border:1px solid #ccc;padding:6px;font-size:12.5px}"
            "tr:nth-child(even) td{background:#f2f6fa}"
            ".tot td{font-weight:bold;background:#ddeaf7}"
            ".wm{position:fixed;top:42%;left:12%;transform:rotate(-24deg);"
            "font-size:60px;color:rgba(200,60,40,0.12);font-weight:bold;z-index:-1}"
            "@media print{body{margin:5mm}}"
            "</style></head><body>" + body + "</body></html>")


def save_and_open_html(fname, title, body, folder):
    path = os.path.join(folder, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_page(title, body))
    open_file(path)
    return path
