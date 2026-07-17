"""MilkLab Agent Harness (S2) - Ultimate Edition (Anti-Auto-Link)."""

import argparse
import json
import os
import sys
import requests
import gspread
from datetime import datetime

from dotenv import load_dotenv
from google import genai

# ==========================================
# 2.2 ออกแบบ tool schema
# ==========================================
TOOL_SCHEMA = [
    {
        "name": "log_sale",
        "description": "บันทึกการขายลง Google Sheets และส่ง notification",
        "parameters": {
            "type": "object",
            "properties": {
                "menu": {"type": "string", "description": "ชื่อเมนู"},
                "qty": {"type": "integer", "description": "จำนวนที่ขาย"},
                "price": {"type": "number", "description": "ราคาต่อหน่วย"},
            },
            "required": ["menu", "qty", "price"],
        },
    },
    {
        "name": "query_sales",
        "description": "ดูยอดขายของวันที่ระบุ",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "วันที่ format YYYY-MM-DD"},
            },
            "required": ["date"],
        },
    },
    {
        "name": "send_alert",
        "description": "ส่ง message แจ้งเตือนผ่าน Bot",
        "parameters": {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
            },
            "required": ["message"],
        },
    },
]


def parse_command(cmd: str, api_key: str | None = None) -> dict:
    api_key = api_key or os.environ.get(
        "GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    prompt = f"""
    คุณคือ AI Agent แปลงคำสั่งภาษาไทยเป็น JSON
    คำสั่ง: "{cmd}"
    Tool Schema: {json.dumps(TOOL_SCHEMA, ensure_ascii=False)}
    
    ตอบเป็น JSON เท่านั้น รูปแบบ: {{"tool": "ชื่อ_tool", "args": {{"ชื่อตัวแปร": "ค่า"}}}}
    ห้ามมีข้อความอื่นปนเด็ดขาด
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.5-flash',
            contents=prompt,
        )

        clean_text = response.text.strip()
        if clean_text.startswith('```json'):
            clean_text = clean_text[7:]
        elif clean_text.startswith('```'):
            clean_text = clean_text[3:]

        if clean_text.endswith('```'):
            clean_text = clean_text[:-3]

        return json.loads(clean_text.strip())
    except Exception as e:
        raise RuntimeError(f"Parse failed: {e}")


def dispatch_tool(tool_call: dict) -> str:
    tool_name = tool_call.get("tool")
    args = tool_call.get("args", {})

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    sheets_creds_str = os.environ.get("GOOGLE_SHEETS_CREDENTIALS")

    if tool_name == "log_sale":
        if args.get("qty", 0) <= 0:
            raise ValueError("quantity must be positive")
        if args.get("price", 0) <= 0:
            raise ValueError("price must be positive")

        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+07")
        menu = args.get('menu', 'ไม่ระบุ')
        qty = args.get('qty', 0)
        price = args.get('price', 0)
        total = qty * price

        # 1. ส่งแจ้งเตือนเข้า Telegram (ต่อ String หลอกโปรแกรม)
        if bot_token and chat_id:
            msg = f"🚨 มีออเดอร์ใหม่เข้าจ้า!\n🥛 เมนู: {menu}\n📦 จำนวน: {qty} ขวด\n💰 ราคา: {price} บาท\n💵 ยอดรวม: {total} บาท"
            tg_api = "https://" + "api.telegram.org/bot"
            url = f"{tg_api}{bot_token}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": msg})

        # 2. บันทึกลง Google Sheets
        if sheets_creds_str:
            try:
                if not sheets_creds_str.strip():
                    raise ValueError("ข้อมูลใน .env ว่างเปล่า")

                creds_dict = json.loads(sheets_creds_str)
                gc = gspread.service_account_from_dict(creds_dict)
                sheet = gc.open("Sales Logger").sheet1
                sheet.append_row([now_str, menu, qty, price, total])
            except Exception as e:
                raise RuntimeError(f"Google Sheets Error: {e}")

        return f"OK: row appended at {now_str}"

    elif tool_name == "query_sales":
        return f"OK: query sales for {args.get('date')}"

    elif tool_name == "send_alert":
        message_text = args.get('message', 'ไม่มีข้อความ')
        if not bot_token or not chat_id:
            raise ValueError(
                "ยังไม่ได้ใส่ TELEGRAM_BOT_TOKEN หรือ TELEGRAM_CHAT_ID")

        # ต่อ String หลอกโปรแกรมเหมือนกัน
        tg_api = "https://" + "api.telegram.org/bot"
        url = f"{tg_api}{bot_token}/sendMessage"
        resp = requests.post(
            url, json={"chat_id": chat_id, "text": f"🤖 [AI Agent]:\n{message_text}"})

        if resp.ok:
            return "OK: ส่งข้อความเข้ามือถือสำเร็จแล้ว!"
        else:
            raise RuntimeError(f"พังจ้า Telegram บ่นว่า: {resp.text}")

    else:
        raise ValueError(f"Unknown tool: {tool_name}")


def main() -> int:
    load_dotenv(override=True)

    parser = argparse.ArgumentParser()
    parser.add_argument("--cmd", required=True, help="คำสั่งภาษาไทย")
    args = parser.parse_args()

    try:
        msg_user_in = f"[USER] {args.cmd}"
        print(msg_user_in)

        tool_call = parse_command(args.cmd)
        args_str = ", ".join(
            [f"{k}: {v}" for k, v in tool_call.get("args", {}).items()])
        msg_llm = f"[LLM]  tool={tool_call['tool']} args={{{args_str}}}"
        print(msg_llm)

        result = dispatch_tool(tool_call)
        msg_tool = f"[TOOL] {tool_call['tool']} {result}"
        print(msg_tool)

        if tool_call['tool'] == "log_sale":
            total = tool_call["args"].get(
                "qty", 0) * tool_call["args"].get("price", 0)
            final_ans = f"บันทึกแล้วยอด {total} บาท"
        else:
            final_ans = "ดำเนินการสำเร็จ"

        msg_user_out = f"[USER] ←  {final_ans}"
        print(msg_user_out)

        # -------------------------------------------------------------
        # เพิ่มโค้ดส่วนนี้เข้าไปเพื่อเขียนลงไฟล์ agent_trace.log
        try:
            # เปิดไฟล์ในโหมด 'a' (append) และกำหนด encoding เป็น utf-8 เพื่อให้อ่านภาษาไทยได้
            with open("agent_trace.log", "a", encoding="utf-8") as log_file:
                # บันทึกข้อมูลที่โชว์บนหน้าจอลงไฟล์
                log_file.write(f"{msg_user_in}\n")
                log_file.write(f"{msg_llm}\n")
                log_file.write(f"{msg_tool}\n")
                log_file.write(f"{msg_user_out}\n")
                # ขีดเส้นใต้คั่นแต่ละรอบให้ดูง่ายขึ้น
                log_file.write("-" * 50 + "\n")
        except Exception as e:
            print(f"[Warning] ไม่สามารถบันทึกลงไฟล์ log ได้: {e}")
        # -------------------------------------------------------------

    except Exception as e:
        print(f"[ERROR] {e}")

        # --- (เพิ่มเติม) บันทึก Error ลงไฟล์ด้วย ---
        try:
            with open("agent_trace.log", "a", encoding="utf-8") as log_file:
                log_file.write(f"[USER] {args.cmd}\n")
                log_file.write(f"[ERROR] {e}\n")
                log_file.write("-" * 50 + "\n")
        except:
            pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
