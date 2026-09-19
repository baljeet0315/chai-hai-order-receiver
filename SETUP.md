# Setup checklist

Everything goes into the `.env` file in this folder (locally) and into Railway -> Variables (production).
Never paste keys into chat or commit `.env`.

## 1. Claude key  (5 min)  -> unlocks the parser tests
1. Open `.env`, set `ANTHROPIC_API_KEY=` to your key.
2. Run:  `pip install -r requirements.txt`  then  `pytest tests/test_parser_live.py -v`
3. Send the failures to Claude. Failures here mean the prompt or aliases need tuning, not that the code is broken.

## 2. Supabase  (10 min)
1. Create a new project at supabase.com.
2. SQL Editor -> paste all of `db/schema.sql` -> Run.
3. Project Settings -> API: copy **Project URL** into `SUPABASE_URL` and the **service_role** key into `SUPABASE_SERVICE_KEY`.
   (service_role, not anon. It is a secret.)

## 3. Google Sheet  (15 min)
1. Create a Google Sheet. Copy the id from its URL into `GOOGLE_SHEET_ID`.
2. console.cloud.google.com -> new project -> enable **Google Sheets API**.
3. IAM & Admin -> Service Accounts -> create one -> Keys -> Add key -> JSON. A file downloads.
4. Share the Google Sheet with the service account's email (ends in `iam.gserviceaccount.com`) as **Editor**.
5. Put the whole JSON file on ONE line into `GOOGLE_SERVICE_ACCOUNT_JSON`.
   One-liner to print it on one line:  `python3 -c "import json;print(json.dumps(json.load(open('KEYFILE.json'))))"`
The app creates the "Orders" tab and header row by itself.

## 4. Railway  (10 min)
1. Push this folder to a private GitHub repo (`git init`, commit, push). `.gitignore` already excludes `.env`.
2. Railway -> New Project -> Deploy from GitHub repo. The `Procfile` tells it how to start.
3. Variables -> add every name from `.env` with its value.
4. Settings -> Networking -> Generate Domain. Your webhook URL is `https://<that-domain>/webhook`.
5. Check `https://<that-domain>/health` shows `{"ok": true}`.

## 5. Meta / WhatsApp  (30 min)
1. business.facebook.com -> create a Business account (if you have none).
2. developers.facebook.com -> My Apps -> Create App -> type **Business** -> add the **WhatsApp** product.
3. WhatsApp -> API Setup:
   - copy **Phone number ID** (of the test number) into `WHATSAPP_PHONE_NUMBER_ID`
   - copy the temporary **access token** into `WHATSAPP_TOKEN` (expires in 24h, fine for the first test)
   - under "To", add and verify your personal WhatsApp number
4. App settings -> Basic -> **App secret** -> `WHATSAPP_APP_SECRET`.
5. Invent a random string -> `WHATSAPP_VERIFY_TOKEN`.
6. Set `OWNER_PHONE` to your personal number, digits only with country code (e.g. 16045551234).
7. Update the Railway variables, let it redeploy.
8. WhatsApp -> Configuration -> Webhook: Callback URL = your `/webhook` URL, Verify token = the string from step 5.
   Then **Manage** webhook fields -> subscribe to **messages**.
9. From your phone, send "3 masala 2 adrak" to the test number. You should get the approval message with buttons.

### Before real customers
- Permanent token: Business Settings -> System users -> create one -> assign the app and WhatsApp account ->
  generate a token with `whatsapp_business_messaging` and `whatsapp_business_management`. Replace `WHATSAPP_TOKEN`.
- Register a new real phone number and complete business verification.
- WhatsApp Manager -> Message templates -> create a **Utility** template named `order_confirmed`, language English,
  body: `Your Chai Hai order is confirmed: {{1}}. Thank you!`
- The 24-hour rule also applies to messages the bot sends YOU. If you have not messaged the business number
  in the last 24 hours, approval messages will not be delivered. Simplest fix: send it any message each morning.

## How to use it
- **Approve / Reject**: tap the button.
- **Correct an order**: long-press the approval message -> Reply -> type the fix, e.g. `masala 5, remove ginger`
  or `those 5 packs are classic`. You get a fresh approval message.
- Orders with an unknown flavour or quantity cannot be approved until corrected.
- Anything that is not an order is forwarded to you; the customer gets no reply.
