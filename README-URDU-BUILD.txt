v5 - آخری جگہ (راستہ بدل دیا):
raw buildozer لائن کی جگہ اب "buildozer-action" (ہزاروں Kivy APKs کا
آزمودہ action) - یہ اپنا SDK + Java + NDK + licences سب خود لاتا ہے۔
دو الگ jobs: اردو اور English - اب ایک مرے تو دوسری پھر بھی بنے گی۔

==========================================================================
  ApnaSoft POS 2.0 - ANDROID APK بنانا (مفت، بادل میں) - v2 مضبوط
==========================================================================
v4 - حتمی ورژن (تین مرض، تین علاج - اس بار اور بھی مضبوط):
1) Python 3.12 کا مرض -> workflow خود 3.11 لگاتا ہے
2) Google SDK کا "Accept? (y/N)" مرض (Aidl not found) ->
   SDK پہلے سے رکھ کر licences خود قبول + دستی stamp بھی
3) Java کا خاموش مرض (نئے SDK کو Java 17 چاہیے) ->
   setup-java سے پن شدہ Temurin 17
اضافہ: step کے اوپر "WORKFLOW v4" لکھا آئے گا تاکہ تصویر سے پتہ چلے
کہ نیا ورژن ہی چلا؛ build fail ہو تو خود آخری 120 لائنیں چھاپ دے گا۔

v3 - اس بار کا علاج (دو ROOT CAUSES ٹھیک کیے):
1) GitHub کا نیا Ubuntu Python 3.12 لاتا ہے - workflow خود Python 3.11 لگاتا ہے
2) Google کا Android SDK درمیان میں "Accept? (y/N)" پوچھ کر build-tools
   نصب نہیں ہونے دیتا تھا (پچھلا fail- "Aidl not found" یہی تھا)۔
   اب workflow Google کا SDK پہلے سے رکھ کر سب licences پہلے قبول کرتا ہے -
   لہٰذا 'Aidl not found' والا مرض دوبارہ نہیں آئے گا، ان شاء اللہ۔

zip کے اندر workflow دو جگہ ہے (دونوں ایک جیسی):
  1) .github/workflows/build-apk.yml   (مکمل ترتیب - خودکار راستہ)
  2) build-workflow.yml                (paste کے لیے - محفوظ راستہ)

--------------------------------------------------------------------------
قدم 1:  zip کھولیں - "pos2-android" فولڈر سامنے آئے گا
--------------------------------------------------------------------------
قدم 2:  GitHub اکاؤنٹ + خالی خانہ (repository)
--------------------------------------------------------------------------
1) github.com -> مفت اکاؤنٹ -> اوپر دائیں "+" -> "New repository"
2) نام: pos2-android  ->  سبز "Create repository"

--------------------------------------------------------------------------
قدم 3:  فائلیں چڑھائیں  - دو راستے، جو آسان لگے:
--------------------------------------------------------------------------
راستہ A (ویب upload - آسان مگر .github نہیں چڑھتا):
   * repo کے صفحے پر "uploading an existing file" -> pos2-android
     فولڈر drag کریں -> "Commit changes"
   * پھر قدم 4 (paste) لازمی کریں

راستہ B (git کمانڈ - کمپلیٹ، .github بھی چڑھتا ہے):
   repo کے صفحے پر جیسی ہدایات ہوں، اپنے PC کے CMD میں:
      cd pos2-android
      git init
      git add -A
      git commit -m "apnasoft pos android"
      git branch -M main
      git remote add origin https://github.com/APNA-USER/pos2-android.git
      git push -u origin main
   (APNA-USER کی جگہ اپنا username، پاس ورڈ کی جگہ GitHub کا
    Personal Access Token: Settings -> Developer settings -> Tokens)

--------------------------------------------------------------------------
قدم 4:  workflow لگانا (راستہ A کے لیے - 2 منٹ)
--------------------------------------------------------------------------
1) zip سے نکالی "build-workflow.yml" Notepad میں کھولیں -> سارا متن
   نقل کریں (Ctrl+A, Ctrl+C)
2) repo میں اوپر "Actions" -> "set up a workflow yourself"
3) editor کا متن مٹا کر اپنا چپکائیں -> سبز "Commit changes" دوبارہ

(راستہ B سے چڑھایا تو قدم 4 کی ضرورت نہیں - Actions خود تیار ملے گا)

--------------------------------------------------------------------------
قدم 5:  چلائیں -> APK ڈاؤن لوڈ
--------------------------------------------------------------------------
1) "Actions" -> بائیں "Build ApnaSoft POS Android APKs"
2) دائیں "Run workflow" -> سبز بٹن
3) 30-60 منٹ -> نیچے دو Artifacts:
      * ApnaSoftPOS2-Urdu-apk
      * ApnaSoftPOS2-English-apk

--------------------------------------------------------------------------
اگر کہیں fail (لال نشان) آئے: اس step پر کلک کر کے سب سے نیچے والی
20-30 لائنیں نقل کر مجھے بھیج دیں - میں سطر بہ سطر ٹھیک کر دوں گا۔
==========================================================================
