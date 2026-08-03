# ============================================================================
#  ApnaSoft POS 2.0 - ANDROID build (Kivy/buildozer) - Urdu + English APK
# ============================================================================
[app]
title = ApnaSoft POS 2.0
package.name = apnasoftpos2
package.domain = com.apnasoft
source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,ttf,json
source.exclude_patterns = _shot.py,_boot.py,__pycache__,*.pyc,.github,bin,build
version = 0.1

# python3 + kivy + sqlite3 اصل انجن؛ pyjnius موبائل ID کے لیے؛
# arabic_reshaper/python-bidi اردو جوڑ+ترتیب کے لیے - سب pure/recipe
requirements = python3,kivy,sqlite3,pyjnius,arabic_reshaper,python-bidi

orientation = portrait
fullscreen = 0
# مکمل OFFLINE - کوئی اجازت درکار نہیں (کلیدیں بھی offline)
android.permissions =

[buildozer]
log_level = 2
warn_on_root = 1
