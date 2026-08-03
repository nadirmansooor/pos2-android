# -*- coding: utf-8 -*-
# ============================================================================
#  ApnaSoft POS 2.0 - CENTRAL CONFIG
#  (OFFLINE | zero external package | SQLite)
# ============================================================================
import os
import sys

APP_NAME    = "ApnaSoft POS 2.0"
APP_SHORT   = "POS 2.0"
VERSION     = "1.0"
BUILD       = "22 July 2026"
DB_NAME     = "pos2.db"
APP_TAG     = "pos2"                 # backup tag
FINGER_TAG  = "apnapos2"

# ---- APNASOFT IDENTITY (compulsory part of the license - buyer cannot change it)
COMPANY        = "ApnaSoft Software Solutions"
COMPANY_WEB    = "blazinginfo.com"
COMPANY_EMAIL  = "apnasoft@blazinginfo.com"
COMPANY_PHONES = ("0346-3247580", "0341-4042159", "0311-6969288")
COMPANY_LINE   = (COMPANY + "  |  " + COMPANY_WEB + "  |  " + COMPANY_EMAIL +
                  "  |  " + " / ".join(COMPANY_PHONES))

# ---- 1-MONTH FREE TRIAL (bound to the hardware ID - reinstall never
#      resets it; the whole software works during the trial, only the
#      calendar clock limits it)
TRIAL_DAYS = 30                     # free trial length (calendar days)
DEMO_WATERMARK = ("ایک ماہ مفت آزمائش - مکمل ورژن، سب کچھ چلتا ہے - "
                  "کبھی بھی اپنی لائسنس کلید لگائیں")
EXPIRY_WARN_DAYS = 15               # warn this many days before license expiry
EXPIRY_ALERT_DAYS = 30              # warn for products expiring within N days

# ----------------------------------------------------------------------------
#  ONLINE LICENSE REGISTRY (optional - the app keeps working 100% offline
#  even if the registry can not be reached; blocking applies once the
#  software successfully talks to the registry and the key is BLOCKED).
#  Upload online-registry-pos2/registry.php to your hosting and put its
#  URL here BEFORE building the client EXE.
# ----------------------------------------------------------------------------
REGISTRY_URL = "https://blazinginfo.com/apnasoft/pos2/registry.php"
REGISTRY_ENABLED = True
REGISTRY_TIMEOUT = 5            # seconds

PAYMENT_METHODS = ("Cash", "Card", "Digital", "Credit")
ROLES = ("admin", "cashier")
RECEIPT_PAPERS = ("58mm", "80mm", "A4")
# The main unit of a product can be ANY of these - a wholesale item's
# unit IS its big pack (bora / carton), so one product button sells the
# whole bora at the bora rate with no extra pack buttons anywhere.
PRODUCT_UNITS = ("pcs", "kg", "g", "litre", "ml", "metre", "dozen",
                 "pack", "packet", "box", "bag", "bora", "carton",
                 "bottle", "tin", "strip")

DEFAULT_EXPENSE_CATS = ("Rent", "Electricity", "Salary", "Transport",
                        "Tea/Food", "Repair", "Other")
DEFAULT_CATEGORIES = ("Grocery", "Beverages", "Snacks", "Dairy", "Bakery",
                      "Personal Care", "Household", "Stationery", "Other")


def base_dir():
    """The ONE folder the owner can always see: next to the exe when the
    software runs as a built exe, the project root when it runs from
    source. Crash and boot notes land here so a client finds them right
    beside ApnaSoftPOS2.exe, photographs them and sends them over -
    a hidden temp folder would swallow them the moment the app closes."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir():
    env = os.environ.get("APNAPOS2_DATA")
    if env:
        os.makedirs(env, exist_ok=True)
        return env
    d = os.path.join(base_dir(), "data")
    os.makedirs(d, exist_ok=True)
    return d


def db_path():
    return os.environ.get("APNAPOS2_DB",
                          os.path.join(data_dir(), DB_NAME))


def asset(name):
    """Path to a bundled image/font - honest in EVERY build: in dev it is
    the project assets folder; inside the built exe PyInstaller unpacks
    the datas beside the executable (one-dir) or into _MEIPASS (one-
    file). The first real existing candidate wins - a client never sees
    the tkinter feather where our own logo belongs."""
    cands = [os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "assets", name)]
    try:
        import sys
        if getattr(sys, "frozen", False):
            exe_d = os.path.dirname(os.path.abspath(sys.executable))
            frozen = [os.path.join(exe_d, "assets", name),
                      os.path.join(exe_d, "_internal", "assets", name)]
            if getattr(sys, "_MEIPASS", ""):
                frozen.insert(0, os.path.join(sys._MEIPASS, "assets",
                                              name))
            cands = frozen + cands
    except Exception:
        pass
    for c in cands:
        if os.path.exists(c):
            return c
    return cands[0]


def reports_dir():
    d = os.path.join(data_dir(), "exports")
    os.makedirs(d, exist_ok=True)
    return d
