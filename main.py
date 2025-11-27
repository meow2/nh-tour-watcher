import os
import time
import json
import unicodedata
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import re

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# 設定
BASE_URL = "https://ana-blue-hangar-tour.resv.jp/reserve/calendar.php?x=....." # ★URLはそのまま使ってください
NOTIFIED_FILE = "notified_dates.txt"

# LINE Messaging API 設定
LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
LINE_USER_ID = os.environ.get("LINE_USER_ID")
LINE_API_URL = "https://api.line.me/v2/bot/message/push"

def send_line_message(message):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_ACCESS_TOKEN}"
    }
    data = {
        "to": LINE_USER_ID,
        "messages": [{"type": "text", "text": message}]
    }
    try:
        requests.post(LINE_API_URL, headers=headers, data=json.dumps(data))
    except Exception as e:
        print(f"LINE送信エラー: {e}")

def get_html_via_selenium(url):
    print(f"Opening Chrome... {url[:30]}...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1280,1024')
    
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(url)
        time.sleep(5)
        html = driver.page_source
    except Exception as e:
        print(f"Selenium Error: {e}")
        html = None
    finally:
        driver.quit()
    return html

def check_availability():
    notified_slots = []
    if os.path.exists(NOTIFIED_FILE):
        with open(NOTIFIED_FILE, "r") as f:
            notified_slots = [line.strip() for line in f.readlines()]

    found_slots = []
    new_notified_slots = []
    
    html = get_html_via_selenium(BASE_URL)
    if not html: return

    soup = BeautifulSoup(html, 'lxml')
    cells = soup.find_all('td')
    print(f"Cells found: {len(cells)}")

    for cell in cells:
        text_all = cell.get_text(strip=True)
        if not text_all: continue

        text_norm = unicodedata.normalize('NFKC', text_all)
        
        # --- 判定ロジック ---
        is_avail = False
        seat_info = ""

        # 1. 記号判定
        if "○" in text_norm or "◎" in text_norm:
            is_avail = True
            seat_info = "余裕あり(○)"
        elif "△" in text_norm:
            is_avail = True
            seat_info = "残りわずか(△)"
        
        # 2. 「残数」判定 (修正箇所)
        # 修正前: re.search(r'残(\d+)', text_norm) -> 時間の数字まで吸い込んでいた
        # 修正後: re.search(r'残(\d+)(?=\d{1,2}:\d{2})', text_norm)
        # 解説: 「後ろに『数字:数字』(時間)が控えている直前までの数字」だけを抜き取る
        
        if not is_avail:
            # 時間(9:30など)の前にある数字だけを取得する
            match_zan = re.search(r'残(\d+)(?=\d{1,2}:\d{2})', text_norm)
            
            # もし時間のパターンがない場合（単に「残1」で終わっている場合など）の予備チェック
            if not match_zan:
                 # 時間チェックなしで数字を取るが、桁数制限（1〜2桁）をかけて誤検知を防ぐ
                 match_zan = re.search(r'残(\d{1,2})', text_norm)

            if match_zan:
                seats = int(match_zan.group(1))
                if seats >= 1: # 1席以上あればヒット
                    is_avail = True
                    seat_info = f"残り{seats}席"

        if is_avail:
            # 日付を取得
            day_match = re.match(r'^(\d+)', text_norm)
            day_str = f"{day_match.group(1)}日" if day_match else "日付不明"
            
            # 表示用テキスト
            display_text = f"【{day_str}】 {seat_info}"
            print(f"  -> MATCH! Found: {display_text} (原盤: {text_norm[:15]}...)")
            
            # 通知ロジック
            today = datetime.now().strftime("%Y-%m-%d")
            # 席数や日付が変わっても通知されるように、キーには席数情報を含める
            unique_key = f"{today}: {day_str} {seat_info}"
            
            # まだ今日通知していない内容なら追加
            if not any(unique_key in s for s in notified_slots if s.startswith(today)):
                found_slots.append(display_text)
                new_notified_slots.append(unique_key)

    if found_slots:
        print(f"Found {len(found_slots)} slots.")
        msg = "✈️ ANA工場見学 空き発生！\n\n" + "\n".join(found_slots) + f"\n\n予約: {BASE_URL}"
        send_line_message(msg)
        
        with open(NOTIFIED_FILE, "a") as f:
            for s in new_notified_slots: f.write(s + "\n")
    else:
        print("No availability found.")

if __name__ == "__main__":
    check_availability()
