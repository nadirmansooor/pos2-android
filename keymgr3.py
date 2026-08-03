# -*- coding: utf-8 -*-
# ============================================================================
#  ApnaSoft POS 2.0 - ANDROID licence engine
#  یہ POS3-V3 کلید انجن *لفظ بہ لفظ* وہی ہے جو ڈیسک ٹاپ (Windows) ورژن میں ہے -
#  اسی لیے آپ کی موجودہ "Licence Studio" سے بنی ہر کلید اس APK میں بھی چلے گی۔
#  ایک کلید = محدود موبائلز (machine token) - ہر موبائل کا ANDROID_ID lock۔
# ============================================================================
import datetime as _dt
import hashlib
import hmac
import json
import os
import uuid

_B36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_DEVICES = 2
_V3_LIFE = 888888

# --- seal key: عین وہی 3 ٹکڑے جو ڈیسک ٹاپ کے 3 ماڈیولز میں بکھرے تھے --------
_S2A = (0x51, 0xA3, 0x2C, 0x77, 0x19, 0xE8, 0x46, 0x0B,
        0xC2, 0x35, 0x89, 0x5E, 0x74, 0xAA, 0x31, 0x6D)
_CFG_CHUNK = "r8Tz4Km9xQ2w7Vp3".encode()
_LCK_CHUNK = b"m4Q9x7RzK2w8p5Vn"
_S2 = {"k": b""}


def _secret2():
    if not _S2["k"]:
        p1 = bytes(x ^ 0x5A for x in _S2A)
        mix = p1 + _CFG_CHUNK + _LCK_CHUNK
        h = hashlib.sha256()
        for i in range(64):
            h.update(mix)
            h.update(bytes([(i * 13) & 0xFF]))
            mix = mix[3:] + mix[:3][::-1]
        _S2["k"] = h.digest()
    return _S2["k"]


def _b36n(num, width):
    num = int(num) % (36 ** width)
    out = ""
    for _i in range(width):
        num, r = divmod(num, 36)
        out = _B36[r] + out
    return out


def _v3h(tag, text):
    return hmac.new(_secret2(), ("V3|" + tag + "|" + text).encode(),
                    hashlib.sha256).digest()


def _v3_client_code(client):
    num = int.from_bytes(_v3h("cl", client.strip().upper())[:5], "big")
    return _b36n(num, 8)


def _v3_exp_token(code, expiry):
    if expiry == "999999":
        raw = _V3_LIFE
    else:
        d = _dt.date(2000 + int(expiry[0:2]), int(expiry[2:4]),
                     int(expiry[4:6]))
        raw = (d - _dt.date(2024, 1, 1)).days
        if raw < 0 or raw > 36524:
            raise ValueError("صرف 2024 اور اس کے بعد کی تاریخی کلیدیں۔")
    mask = int.from_bytes(_v3h("em", code)[:2], "big") & 0xFFFFF
    return _b36n(raw ^ mask, 5)


def _v3_exp_read(code, token):
    try:
        raw = int(token, 36) ^ (int.from_bytes(_v3h("em", code)[:2],
                                               "big") & 0xFFFFF)
    except Exception:
        return "bad", ""
    if raw == _V3_LIFE:
        return None, "LIFETIME"
    if not (0 <= raw < 36525):
        return "bad", ""
    d = _dt.date(2024, 1, 1) + _dt.timedelta(days=raw)
    return None, "%04d-%02d-%02d" % (d.year, d.month, d.day)


def _v3_mach_token(code, machines):
    v = (int(machines) & 0x7F) ^ (int.from_bytes(_v3h("mm", code)[:1],
                                                 "big") & 0x7F)
    v = ((v << 3) | (v >> 4)) & 0x7F
    return _b36n(v + 36, 3)


def _v3_mach_read(code, token):
    try:
        v = int(token, 36) - 36
        v = ((v >> 3) | (v << 4)) & 0x7F
        m = v ^ (int.from_bytes(_v3h("mm", code)[:1], "big") & 0x7F)
        return m if 1 <= m <= 99 else -1
    except Exception:
        return -1


def _v3_sig(tag, text):
    return _b36n(int.from_bytes(_v3h(tag, text)[:3], "big"), 5)


def make_key3(client, expiry, machines):
    """STUDIO-side generator (صرف جانچ کے لیے یہاں بھی - اصل کلیدیں آپ کی
    موجودہ Licence Studio بنائے گی؛ algorithm بایت بہ بایت ایک ہی ہے)"""
    client = (client or "").strip()
    if not client:
        raise ValueError("کلائنٹ کا نام ضروری ہے")
    if not (expiry.isdigit() and len(expiry) == 6):
        raise ValueError("میعاد 6 ہندسے YYMMDD یا 999999 ہونی چاہیے۔")
    m = int(machines)
    if not (1 <= m <= 99):
        raise ValueError("موبائل کی حد 1 تا 99 ہونی چاہیے")
    p1 = _v3_client_code(client)
    p2 = _v3_exp_token(p1, expiry)
    p3 = _v3_mach_token(p1, m)
    p4 = _v3_sig("a1", p1 + p2)
    p5 = _v3_sig("b2", p1 + p3 + p4)
    p6 = _v3_sig("z9", client.strip().upper() + ":" + p2 + p3 + p4 + p5)
    return "POS3-%s-%s-%s-%s-%s-%s" % (p1, p2, p3, p4, p5, p6)


def _v3_parts(key):
    parts = (key or "").strip().upper().split("-")
    return parts[1:] if (len(parts) == 7 and parts[0] == "POS3") else None


def _today():
    return _dt.date.today().isoformat()


def validate_key(client, key):
    """Returns (ok, message, expiry_iso) - POS3 keys only (جوں ڈیسک ٹاپ)"""
    if not (key or "").strip().upper().startswith("POS3-"):
        return False, "یہ پرانے طرز کی کلید قبول نہیں۔ ایڈمن سے نئی کلید لیں۔", ""
    client = (client or "").strip()
    seg = _v3_parts(key)
    if not seg:
        return False, "کلید کا فارمیٹ غلط ہے۔", ""
    p1, p2, p3, p4, p5, p6 = seg
    if not hmac.compare_digest(p1, _v3_client_code(client)):
        return False, "یہ کلید کسی اور کلائنٹ نام کے لیے بنی ہے۔", ""
    if not hmac.compare_digest(p4, _v3_sig("a1", p1 + p2)):
        return False, "کلید کا جانچ کوڈ غلط ہے۔", ""
    if not hmac.compare_digest(p5, _v3_sig("b2", p1 + p3 + p4)):
        return False, "کلید کا جانچ کوڈ غلط ہے۔", ""
    if not hmac.compare_digest(
            p6, _v3_sig("z9", client.strip().upper() + ":" + p2 + p3 +
                        p4 + p5)):
        return False, "کلید کی مہر غلط ہے۔", ""
    bad, human = _v3_exp_read(p1, p2)
    if bad:
        return False, "کلید کا ڈیٹا خراب ہے۔", ""
    if human != "LIFETIME" and human < _today():
        return False, "اس کلید کی میعاد گزر چکی ہے: %s" % human, human
    m = _v3_mach_read(p1, p3)
    if m < 1:
        return False, "کلید کا ڈیٹا خراب ہے۔", ""
    return True, ("لائسنس یافتہ: %s - یہ کلید %d موبائلز تک چلتی ہے۔"
                  % (client, m)), human


def key_machine_limit(key):
    seg = _v3_parts(key)
    if seg:
        m = _v3_mach_read(seg[0], seg[2])
        return m if m >= 1 else MAX_DEVICES
    return MAX_DEVICES


# ----------------------------------------------------------------------------
#  موبائل ڈیوائس لاک (ANDROID_ID + محفوظ fallback)
# ----------------------------------------------------------------------------
_DATA_DIR = os.environ.get("APNAPOS2_DATA",
                          os.path.join(os.path.expanduser("~"),
                                       ".pos2-android"))


def _device_id_file():
    os.makedirs(_DATA_DIR, exist_ok=True)
    return os.path.join(_DATA_DIR, "device.id")


def device_fingerprint():
    """موبائل کی شناخت: پرانڈروائیڈ ANDROID_ID؛ بصورتِ عدم دستیابی ایک
    مستقل random ID جو پہلی بار بن کر ہمیشہ کے لیے محفوظ ہو جاتی ہے"""
    try:
        from jnius import autoclass                       # صرف Android پر
        Secure = autoclass("android.provider.Settings$Secure")
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()
        aid = Secure.getString(resolver, "android_id")
        if aid:
            return hashlib.sha256(("apnapos2|" + aid).encode()
                                  ).hexdigest()[:20]
    except Exception:
        pass
    path = _device_id_file()
    try:
        if os.path.exists(path):
            v = open(path, encoding="utf-8").read().strip()
            if v:
                return v
    except Exception:
        pass
    v = hashlib.sha256((str(uuid.uuid4()) + "|apnapos2").encode()
                       ).hexdigest()[:20]
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(v)
    except Exception:
        pass
    return v


def _lic_path():
    os.makedirs(_DATA_DIR, exist_ok=True)
    return os.path.join(_DATA_DIR, "license.json")


def save_license(client, key, expiry):
    data = {"client": client, "key": key, "expiry": expiry,
            "devices": [device_fingerprint()]}
    with open(_lic_path(), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data


def get_license():
    try:
        with open(_lic_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def register_device(key):
    """Returns (ok, count, limit): نیا موبائل کلید کی حد میں شمار ہو"""
    lic = get_license() or {}
    fp = device_fingerprint()
    devs = lic.get("devices") or []
    if fp in devs:
        return True, len(devs), key_machine_limit(key)
    lim = key_machine_limit(key)
    if len(devs) >= lim:
        return False, len(devs), lim
    devs.append(fp)
    return True, len(devs), lim
