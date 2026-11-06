from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from email.parser import BytesParser
from email.policy import default
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json, uuid, html, mimetypes, traceback, os

BASE = Path(__file__).resolve().parent
ORDERS = BASE / "orders"
ORDERS.mkdir(exist_ok=True)
MAX = 25 * 1024 * 1024
ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()
RUBIKA_BASE = "https://botapi.rubika.ir/v3"

PAGE = """<!doctype html><html lang="fa" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>کافی‌نت نوید</title>
<style>
body{margin:0;background:radial-gradient(circle at top,#333,#151515 60%);color:#fff;font-family:Tahoma;padding:22px 14px}.wrap{max-width:600px;margin:auto}.brand{text-align:center;margin:18px 0 24px}.mark{margin:auto auto 12px;border:1px solid #d7b45b;border-radius:18px;width:62px;height:62px;display:grid;place-items:center;color:#d7b45b;font-size:30px}h1,h2{color:#d7b45b}.card{background:#202020;border:1px solid #80652e;border-radius:20px;padding:22px}label{display:block;margin:14px 0 7px;font-size:13px}input,textarea{width:100%;box-sizing:border-box;background:#141414;color:white;border:1px solid #555;border-radius:10px;padding:13px;font:inherit}.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.only{margin-top:16px;padding:12px;border:1px solid #80652e;border-radius:10px;color:#f5d98d}button{margin-top:18px;width:100%;padding:14px;background:linear-gradient(110deg,#b58a32,#f0d27d);border:0;border-radius:10px;font-weight:bold;font-size:15px}.hint{font-size:11px;color:#aaa;line-height:1.8}.contact{text-align:center;line-height:2;margin:20px;color:#ddd}.contact b{color:#d7b45b;direction:ltr;display:inline-block}@media(max-width:450px){.grid{grid-template-columns:1fr}}
</style><main class="wrap"><header class="brand"><div class="mark">ن</div><h1>کافی‌نت نوید</h1><div>سامانه سفارش آنلاین پرینت</div><p class="hint">فایل خود را ارسال کنید تا برای هماهنگی با شما تماس بگیریم.</p></header>
<section class="card"><h2>ثبت سفارش پرینت</h2><form action="/order" method="post" enctype="multipart/form-data">
<label>نام و نام خانوادگی</label><input name="customer" required maxlength="100">
<div class="grid"><div><label>شماره تماس شما</label><input name="phone" required inputmode="tel" placeholder="09xxxxxxxxx"></div><div><label>تعداد صفحات</label><input name="pages" required inputmode="numeric" placeholder="مثلاً ۲۰"></div></div>
<label>تعداد نسخه</label><input name="copies" value="1" inputmode="numeric">
<label>انتخاب فایل PDF یا عکس</label><input type="file" name="files" accept=".pdf,.jpg,.jpeg,.png,.webp" multiple required>
<p class="hint">حداکثر حجم مجموع فایل‌ها ۲۵ مگابایت.</p><div class="only">✓ فقط پرینت سیاه‌وسفید</div>
<label>توضیحات (اختیاری)</label><textarea name="notes" rows="3"></textarea>
<button type="submit">ارسال سفارش برای کافی‌نت نوید</button></form></section>
<div class="contact">ارتباط با کافی‌نت نوید<br><b>09910124573</b><br>روبیکا • ایتا • شاد<br><span class="hint">برای پیام‌رسان‌ها شماره را در برنامه مربوطه جست‌وجو کنید.</span></div><p class="hint" style="text-align:center">اول طراز ناهید</p></main></html>"""

def rubika_request(method, payload):
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN در تنظیمات Render وارد نشده است.")

    url = f"{RUBIKA_BASE}/{BOT_TOKEN}/{method}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urlopen(req, timeout=45) as response:
        result = json.loads(response.read().decode("utf-8"))

    if result.get("status") != "OK":
        raise RuntimeError(f"Rubika {method} پاسخ ناموفق داد: {result}")

    return result.get("data", {})
def rubika_send_message(chat_id, text):
    return rubika_request("sendMessage", {"chat_id": chat_id, "text": text})

def rubika_send_file(chat_id, file_path, caption):
    file_path = Path(file_path)
    request_data = rubika_request("requestSendFile", {"type": "File"})
    upload_url = request_data.get("upload_url")
    if not upload_url:
        raise RuntimeError(f"آدرس آپلود از روبیکا دریافت نشد: {request_data}")

    file_bytes = file_path.read_bytes()
    boundary = "----KafinetNavid" + uuid.uuid4().hex
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode("utf-8") + file_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    req = Request(upload_url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urlopen(req, timeout=120) as response:
        upload_result = json.loads(response.read().decode("utf-8"))
    file_id = upload_result.get("data", {}).get("file_id") or upload_result.get("file_id")
    if not file_id:
        raise RuntimeError(f"شناسه فایل از روبیکا دریافت نشد: {upload_result}")
    return rubika_request("sendFile", {"chat_id": chat_id, "file_id": file_id, "text": caption})

def deliver_to_rubika(record, folder):
    chat_id = CHAT_ID
    if not chat_id:
        raise RuntimeError("CHAT_ID در تنظیمات Render وارد نشده است.")
    summary = (
        "🖨 سفارش جدید کافی‌نت نوید\n"
        f"کد پیگیری: {record['order_id']}\n"
        f"نام: {record['customer']}\n"
        f"تلفن: {record['phone']}\n"
        f"صفحات: {record['pages']}\n"
        f"نسخه: {record['copies']}\n"
        "نوع چاپ: سیاه‌وسفید\n"
        f"توضیحات: {record['notes'] or 'ندارد'}\n"
        f"تعداد فایل: {len(record['files'])}"
    )
    rubika_send_message(chat_id, summary)
    for item in record["files"]:
        path = folder / item["saved_as"]
        rubika_send_file(chat_id, path, f"سفارش {record['order_id']} - {item['original_name']}")

class H(BaseHTTPRequestHandler):
    def send(self, s, code=200):
        b = s.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        self.send(PAGE if self.path == "/" else "یافت نشد", 200 if self.path == "/" else 404)

    def do_POST(self):
        if self.path != "/order":
            return self.send("یافت نشد", 404)
        n = int(self.headers.get("Content-Length", "0"))
        if n < 1 or n > MAX:
            return self.send("<h3>حجم فایل‌ها باید کمتر از ۲۵ مگابایت باشد. <a href='/'>بازگشت</a></h3>", 413)
        raw = self.rfile.read(n)
        ct = self.headers.get("Content-Type", "")
        msg = BytesParser(policy=default).parsebytes(
            ("Content-Type: " + ct + "\r\nMIME-Version: 1.0\r\n\r\n").encode() + raw
        )
        fields, files = {}, []
        for part in msg.iter_parts():
            name = part.get_param("name", header="content-disposition")
            fn = part.get_filename()
            data = part.get_payload(decode=True) or b""
            if fn and data:
                files.append((fn, data))
            elif name:
                fields[name] = data.decode("utf-8", "replace").strip()
        if not all(fields.get(k) for k in ("customer", "phone", "pages")) or not files:
            return self.send("<h3>اطلاعات ناقص است. <a href='/'>بازگشت</a></h3>", 400)

        oid = datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper()
        folder = ORDERS / oid
        folder.mkdir()
        saved = []
        for fn, data in files:
            ext = Path(fn).suffix.lower()
            if ext in ALLOWED:
                name = uuid.uuid4().hex[:8] + ext
                (folder / name).write_bytes(data)
                saved.append({"saved_as": name, "original_name": Path(fn).name})
        if not saved:
            folder.rmdir()
            return self.send("<h3>فقط PDF و عکس مجاز است. <a href='/'>بازگشت</a></h3>", 400)

        record = {
            "order_id": oid,
            "created_at": datetime.now().isoformat(timespec="minutes"),
            "customer": fields["customer"],
            "phone": fields["phone"],
            "pages": fields["pages"],
            "copies": fields.get("copies", "1"),
            "print_type": "سیاه‌وسفید",
            "notes": fields.get("notes", ""),
            "files": saved
        }
        (folder / "order.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            deliver_to_rubika(record, folder)
            delivery = "<p style='color:green'>فایل‌ها به روبیکا ارسال شدند.</p>"
            print(f"Rubika delivery OK: {oid}")
        except Exception as exc:
            delivery = "<p style='color:#b33'>سفارش ثبت شد، اما ارسال روبیکا انجام نشد. لطفاً با کافی‌نت تماس بگیرید.</p>"
            print(f"Rubika delivery error for {oid}: {exc!r}")
            traceback.print_exc()

        self.send(
            "<h2>سفارش ثبت شد</h2><p>کد پیگیری: <b>" + html.escape(oid) +
            "</b></p>" + delivery +
            "<p>برای هماهنگی با شما تماس می‌گیریم.</p><p>09910124573</p><a href='/'>بازگشت</a>"
        )

if __name__ == "__main__":
    print("Kafinet Navid: http://127.0.0.1:5000")
    print("برای توقف Ctrl+C را بزنید.")
   port = int(os.environ.get("PORT", "5000"))
ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
