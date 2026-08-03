# -*- coding: utf-8 -*-
# اردو متن کو Android/Kivy پر درست (جوڑ + دائیں سے بائیں) دکھانے کا ننھا کام
# Kivy خود shaping نہیں کرتا - reshape + bidi لازمی ہے۔ انگریزی/ہندسے جوں کے توں۔
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _HAS = True
except Exception:
    _HAS = False

_URDU_MARK = ("ا", "ب", "پ", "ت", "ٹ", "ث", "ج", "چ", "ح", "خ", "د", "ڈ",
              "ذ", "ر", "ڑ", "ز", "ژ", "س", "ش", "ص", "ض", "ط", "ظ", "ع",
              "غ", "ف", "ق", "ک", "گ", "ل", "م", "ن", "و", "ہ", "ی", "ے")


def is_urdu(text):
    return any(ch in _URDU_MARK for ch in (text or ""))


def shp(text):
    """Button/Label کے لیے تیار متن: اردو جملہ درست ترتیب میں"""
    t = text or ""
    if not (_HAS and is_urdu(t)):
        return t
    try:
        return get_display(arabic_reshaper.reshape(t))
    except Exception:
        return t
