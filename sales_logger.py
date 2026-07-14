import argparse
import json
import os
import sys
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
import requests


def send_telegram(menu, qty, price, total):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("ไม่พบ Token หรือ Chat ID ของ Telegram ข้ามการแจ้งเตือน")
        return

    text = f"🚨 มียอดขายใหม่เข้าจ้า!\n🥛 เมนู: {menu}\n📦 จำนวน: {qty} ขวด\n💰 ราคา: {price} บาท\n💵 ยอดรวม: {total} บาท"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}

    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"ส่ง Telegram ไม่สำเร็จ: {e}")


def main():
    # 1. รับค่าจาก Command Line
    parser = argparse.ArgumentParser()
    parser.add_argument("--menu", required=True, type=str)
    parser.add_argument("--qty", required=True, type=int)
    parser.add_argument("--price", required=True, type=float)
    args = parser.parse_args()

    total = args.qty * args.price
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+07:00")

    # 2. เตรียมเชื่อมต่อ Google Sheets
    creds_json = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")
    if not creds_json:
        print("Error: ไม่พบ GOOGLE_SHEETS_CREDENTIALS", file=sys.stderr)
        sys.exit(1)

    try:
        creds_dict = json.loads(creds_json)
        scopes = ["https://spreadsheets.google.com/feeds",
                  "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(
            creds_dict, scopes=scopes)
        gc = gspread.authorize(creds)

        # *** สำคัญ: ตรงนี้ต้องเปลี่ยนเป็นชื่อไฟล์ Google Sheet ของคุณ ***
        sheet = gc.open("Sales Logger").sheet1

        # 3. บันทึกลง Sheet
        sheet.append_row([now, args.menu, args.qty, args.price, total])
        print(f"บันทึก {args.menu} จำนวน {args.qty} ลง Google Sheet สำเร็จ!")

    except Exception as e:
        # 4. จัดการ Error กรณีเข้า Sheet ไม่ได้
        print(
            f"Error: เข้าถึง Google Sheets ไม่ได้ โปรดตรวจสอบการแชร์ไฟล์ ({e})", file=sys.stderr)
        sys.exit(1)

    # ส่งแจ้งเตือนเข้า Telegram
    send_telegram(args.menu, args.qty, args.price, total)


if __name__ == "__main__":
    main()
