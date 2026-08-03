# -*- coding: utf-8 -*-
# ============================================================================
#  ApnaSoft POS 2.0 - ANDROID (Kivy) - v0 بنیاد
#  * وہی POS3 کلید (offline) * وہی sqlite ڈیٹابیس انجن (database/db)
#  * اردو + English - ایک ہی کوڈ، دو APK (APP_LANG بدل کر)
# ============================================================================
import os

APP_LANG = os.environ.get("POS2_LANG", "ur")        # "ur" | "en"
APP_TITLE = "ApnaSoft POS 2.0" + (" (اردو)" if APP_LANG == "ur" else " (EN)")

import keymgr3
from urdu import shp

FONT = "assets/fonts/jameel-noori.ttf"
FONT_EN = None  # Kivy کا Default (Roboto)

T = {
    "ur": dict(
        act_title="لائسنس فعال کریں", client="کلائنٹ نام",
        key="لائسنس کلید (POS3-...)", activate="فعال کریں",
        dev="موبائل شناخت", bad="کلید نامنظور:", ok="الحمد للہ! لائسنس فعال",
        home="ڈیش بورڈ", billing="بلنگ / سیل", stock="اسٹاک",
        customers="گاہک / ادھار", reports="رپورٹس",
        soon="(اگلے ورژن میں)", lic="لائسنس",
        trial="ایک ماہ مفت آزمائش چل رہی ہے",
        scan="پروڈکٹ نام / کوڈ", add="شامل", cart="بل (کارٹ)",
        total="کل", finish="بل مکمل (Cash)", saved="بل محفوظ",
        empty="کارٹ خالی ہے", logout="باہر"),
    "en": dict(
        act_title="Activate Licence", client="Client name",
        key="Licence key (POS3-...)", activate="ACTIVATE",
        dev="Device ID", bad="Key refused:", ok="Licence active!",
        home="Dashboard", billing="Billing / Sale", stock="Stock",
        customers="Customers / Credit", reports="Reports",
        soon="(next update)", lic="Licence",
        trial="Free 1-month trial running",
        scan="Product name / code", add="Add", cart="Bill (Cart)",
        total="Total", finish="Complete Sale (Cash)", saved="Sale saved",
        empty="Cart is empty", logout="Exit"),
}


def tr(k):
    lang = T.get(APP_LANG, T["ur"])
    txt = lang.get(k, k)
    return shp(txt) if APP_LANG == "ur" else txt


def setup_data_dir():
    """APK کا پرائیویٹ فولڈر - db & license یہیں رہیں (ہر بار پہلے یہ)"""
    try:
        from android.storage import app_storage_path      # Android only
        d = os.path.join(app_storage_path(), "data")
    except Exception:
        d = os.path.join(os.path.expanduser("~"), ".pos2-android")
    os.makedirs(d, exist_ok=True)
    os.environ["APNAPOS2_DATA"] = d
    return d


def db_boot():
    """وہی db انجن جو ڈیسک ٹاپ چلاتا ہے - جوں کا توں"""
    import database.db as db
    db.init_db()
    return db


# ----------------------------------------------------------------------------
#  KIVY UI (شروع بعد میں - درخواست پر)
# ----------------------------------------------------------------------------
def run():
    setup_data_dir()
    db = db_boot()
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.gridlayout import GridLayout
    from kivy.uix.label import Label
    from kivy.uix.button import Button
    from kivy.uix.textinput import TextInput
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.screenmanager import Screen, ScreenManager
    from kivy.core.window import Window
    from kivy.metrics import dp

    try:
        import android  # noqa: F401  (صرف اصلی موبائل پر موجود)
    except Exception:
        Window.size = (400, 780)     # ڈیسک ٹاپ ٹیسٹ کے لیے موبائل سائز
    Window.clearcolor = (0.94, 0.96, 0.95, 1)
    TEAL = (0.05, 0.45, 0.36, 1)
    DARK = (0.07, 0.24, 0.21, 1)
    RED = (0.74, 0.22, 0.17, 1)
    GREEN = (0.10, 0.55, 0.28, 1)
    ORANGE = (0.71, 0.33, 0.03, 1)

    def lbl(text, size=16, color=(0, 0, 0, 1), bold=False, **kw):
        kw.setdefault("font_size", size)
        fnt = FONT if APP_LANG == "ur" else FONT_EN
        if fnt:
            kw["font_name"] = fnt
        return Label(text=text, color=color, bold=bold, **kw)

    def btn(text, cb, bg=TEAL, size=16, **kw):
        b = Button(text=text, font_size=size, background_color=bg,
                   background_normal="", **kw)
        fnt = FONT if APP_LANG == "ur" else FONT_EN
        if fnt:
            b.font_name = fnt
        b.bind(on_release=lambda *_a: cb())
        return b

    class ActivationScreen(Screen):
        def __init__(self, sm, **kw):
            super().__init__(**kw)
            self.sm = sm
            box = BoxLayout(orientation="vertical", padding=dp(18),
                            spacing=dp(10))
            box.add_widget(lbl(tr("act_title"), 26, TEAL, True,
                               size_hint_y=None, height=dp(60)))
            box.add_widget(lbl(tr("dev") + ":  " + keymgr3.device_fingerprint(),
                               12, DARK, size_hint_y=None, height=dp(30)))
            self.t_client = TextInput(hint_text=tr("client"), multiline=False,
                                      size_hint_y=None, height=dp(46),
                                      font_size=16)
            self.t_key = TextInput(hint_text=tr("key"), multiline=False,
                                   size_hint_y=None, height=dp(46), font_size=14)
            box.add_widget(self.t_client)
            box.add_widget(self.t_key)
            box.add_widget(btn(tr("activate"), self.do_activate, GREEN, 18,
                               size_hint_y=None, height=dp(52)))
            self.stat = lbl(tr("trial"), 14, ORANGE, size_hint_y=None,
                            height=dp(70))
            box.add_widget(self.stat)
            box.add_widget(Label())     # خالی جگہ
            self.add_widget(box)

        def do_activate(self):
            client = self.t_client.text.strip()
            key = self.t_key.text.strip()
            ok, msg, exp = keymgr3.validate_key(client, key)
            if not ok:
                self.stat.text = tr("bad") + " " + shp(msg)
                return
            ok2, cnt, lim = keymgr3.register_device(key)
            if not ok2:
                self.stat.text = shp("یہ کلید %d موبائل پر پہلے چل رہی ہے"
                                     " (حد %d)" % (cnt, lim))
                return
            keymgr3.save_license(client, key, exp)
            self.stat.text = tr("ok")
            self.sm.current = "home"

    class HomeScreen(Screen):
        def __init__(self, sm, **kw):
            super().__init__(**kw)
            self.sm = sm
            box = BoxLayout(orientation="vertical", padding=dp(14),
                            spacing=dp(8))
            lic = keymgr3.get_license()
            ltxt = (tr("lic") + ": " + (lic["client"] if lic else "?"))
            box.add_widget(lbl(APP_TITLE, 22, TEAL, True, size_hint_y=None,
                               height=dp(50)))
            box.add_widget(lbl(ltxt, 13, DARK, size_hint_y=None, height=dp(26)))
            grid = GridLayout(cols=1, spacing=dp(8))
            grid.add_widget(btn(tr("billing"), lambda: setattr(sm, "current",
                                                               "billing"),
                                GREEN, 18, size_hint_y=None, height=dp(54)))
            for name in ("stock", "customers", "reports"):
                grid.add_widget(btn(tr(name) + " " + tr("soon"),
                                    lambda: None, DARK, 15,
                                    size_hint_y=None, height=dp(48)))
            box.add_widget(grid)
            self.add_widget(box)

    class BillingScreen(Screen):
        """v0: مکمل بلنگ چکر - اگلے مراحل میں یہاں پورا POS اسکرین آئے گی"""
        def __init__(self, sm, db, **kw):
            super().__init__(**kw)
            self.sm, self.db = sm, db
            self.cart = []
            root = BoxLayout(orientation="vertical", padding=dp(10),
                             spacing=dp(6))
            top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
            self.t_prod = TextInput(hint_text=tr("scan"), multiline=False,
                                    font_size=15)
            top.add_widget(self.t_prod)
            top.add_widget(btn(tr("add"), self.add_prod, TEAL, 15,
                               size_hint_x=None, width=dp(80)))
            root.add_widget(top)
            self.list_box = BoxLayout(orientation="vertical", spacing=dp(4),
                                      size_hint_y=None)
            self.list_box.bind(minimum_height=self.list_box.setter("height"))
            sv = ScrollView()
            sv.add_widget(self.list_box)
            root.add_widget(lbl(tr("cart"), 16, TEAL, True, size_hint_y=None,
                                height=dp(28)))
            root.add_widget(sv)
            self.lbl_total = lbl(tr("total") + ": Rs 0.00", 18, DARK, True,
                                 size_hint_y=None, height=dp(34))
            root.add_widget(self.lbl_total)
            bot = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
            bot.add_widget(btn(tr("finish"), self.finish, GREEN, 16))
            bot.add_widget(btn("‹ " + tr("home"),
                               lambda: setattr(sm, "current", "home"), DARK,
                               15, size_hint_x=None, width=dp(110)))
            root.add_widget(bot)
            self.stat = lbl("", 13, ORANGE, size_hint_y=None, height=dp(26))
            root.add_widget(self.stat)
            self.add_widget(root)

        def _find(self, term):
            rows = self.db.q(
                "SELECT * FROM products WHERE name LIKE ? OR barcode=?"
                " ORDER BY name LIMIT 8", ("%" + term + "%", term))
            return rows

        def add_prod(self):
            term = self.t_prod.text.strip()
            if not term:
                return
            rows = self._find(term)
            if not rows:
                self.stat.text = shp("کوئی پروڈکٹ نہ ملی: ") + term
                return
            p = rows[0]
            self.cart.append({"product_id": p["id"], "name": p["name"],
                              "qty": 1, "price": float(p["price"]),
                              "discount": 0.0, "cost": float(p["cost"])})
            self._paint()

        def _paint(self):
            self.list_box.clear_widgets()
            tot = 0.0
            for it in self.cart:
                line = it["qty"] * it["price"]
                tot += line
                self.list_box.add_widget(lbl(
                    "%s   x%d   Rs %.2f" % (shp(it["name"]), it["qty"], line),
                    14, DARK, size_hint_y=None, height=dp(30),
                    halign="right"))
            self.lbl_total.text = "%s: Rs %.2f" % (tr("total"), tot)

        def finish(self):
            if not self.cart:
                self.stat.text = tr("empty")
                return
            tot = round(sum(i["qty"] * i["price"] for i in self.cart), 2)
            sid, inv_no, _t = self.db.save_sale(dict(
                customer_id=None, paid=tot, payment="Cash", discount=0.0,
                tax_percent=0.0, username="admin", items=list(self.cart)))
            self.stat.text = "%s: %s (Rs %.2f)" % (tr("saved"), inv_no, tot)
            self.cart = []
            self._paint()

    class POSApp(App):
        def build(self):
            self.title = APP_TITLE
            sm = ScreenManager()
            sm.add_widget(ActivationScreen(sm, name="activation"))
            sm.add_widget(HomeScreen(sm, name="home"))
            sm.add_widget(BillingScreen(sm, db, name="billing"))
            lic = keymgr3.get_license()
            sm.current = "home" if lic else "activation"
            return sm

    POSApp().run()


if __name__ == "__main__":
    run()
