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
from selenium.webdriver.common.by import By

# 設定
# ★URLはカレンダーが表示される状態のものを維持
BASE_URL = "https://ana-blue-hangar-tour.resv.jp/reserve/calendar.php?x=....." 
NOTIFIED_FILE = "notified_dates.txt"
TARGET_TIMES = ["9:30", "10:45", "13:00", "14:15", "15:30"]

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

def parse_html(html, notified_slots, found_slots, new_notified_slots):
    """HTMLから空き情報を抽出する（共通処理）"""
    soup = BeautifulSoup(html, 'lxml')
    cells = soup.find_all('td')
    print(f"  -> Cells found: {len(cells)}")

    for cell in cells:
        text_all = cell.get_text(strip=True)
        if not text_all: continue

        text_norm = unicodedata.normalize('NFKC', text_all)
        
        # 1. 日付特定
        day_match = re.match(r'^(\d+)', text_norm)
        if not day_match: continue
        day_str = day_match.group(1)

        # 2. 時間枠チェック
        for time_str in TARGET_TIMES:
            is_avail = False
            seat_info = ""
            
            # パターンA: 残数明記 (例: 残19:30)
            pattern_zan = re.compile(f'残(\d+){time_str}')
            match_zan = pattern_zan.search(text_norm)
            
            if match_zan:
                seats = int(match_zan.group(1))
                if seats >= 1:
                    is_avail = True
                    seat_info = f"残り{seats}席"
            
            # パターンB: 記号 (直前をチェック)
            if not is_avail:
                idx = text_norm.find(time_str)
                if idx != -1:
                    sub_text = text_norm[max(0, idx-10):idx]
                    if "○" in sub_text or "◎" in sub_text:
                        is_avail = True
                        seat_info = "余裕あり(○)"
                    elif "△" in sub_text:
                        is_avail = True
                        seat_info = "残りわずか(△)"

            if is_avail:
                display_text = f"【{day_str}日 {time_str}】 {seat_info}"
                print(f"    MATCH! Found: {display_text}")

                today = datetime.now().strftime("%Y-%m-%d")
                # キーに年月を含めたいが、画面からは「日」しか取れないため
                # 実行日ベースで重複排除する（簡易実装）
                unique_key = f"{today}: {day_str} {time_str} {seat_info}"
                
                if not any(unique_key in s for s in notified_slots if s.startswith(today)):
                    if display_text not in found_slots:
                        found_slots.append(display_text)
                        new_notified_slots.append(unique_key)

def check_availability():
    print("Starting check...")
    
    # 通知履歴読み込み
    notified_slots = []
    if os.path.exists(NOTIFIED_FILE):
        with open(NOTIFIED_FILE, "r") as f:
            notified_slots = [line.strip() for line in f.readlines()]

    found_slots = []
    new_notified_slots = []

    # Selenium設定
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1280,1024')
    
    driver = webdriver.Chrome(options=options)
    
    try:
        # --- 1ページ目（今月） ---
        print(f"Loading page 1... {BASE_URL[:30]}...")
        driver.get(BASE_URL)
        time.sleep(5) # 描画待ち
        
        print("Parsing page 1...")
        parse_html(driver.page_source, notified_slots, found_slots, new_notified_slots)
        
        # --- 2ページ目（次月）への移動 ---
        try:
            print("Looking for Next Month button (#next a)...")
            
            # ★ここを修正: IDが 'next' の要素の中にあるリンクを探す
            next_btns = driver.find_elements(By.CSS_SELECTOR, "#next a")
            
            if next_btns:
                print("Clicking Next Month button...")
                
                # JavaScriptのリンクなのでclick()で発火
                driver.execute_script("arguments[0].click();", next_btns[0])
                time.sleep(5) # 画面切り替わり待ち
                
                print("Parsing page 2...")
                parse_html(driver.page_source, notified_slots, found_slots, new_notified_slots)
            else:
                print("Next Month button not found.")
                
        except Exception as e:
            print(f"Could not move to next month: {e}")

    except Exception as e:
        print(f"Selenium Error: {e}")
    finally:
        driver.quit()

    # 通知処理
    if found_slots:
        print(f"Total slots found: {len(found_slots)}")
        msg = "✈️ ANA工場見学 空き発生！\n\n" + "\n".join(found_slots) + f"\n\n予約: {BASE_URL}"
        send_line_message(msg)
        
        with open(NOTIFIED_FILE, "a") as f:
            for s in new_notified_slots: f.write(s + "\n")
    else:
        print("No availability found.")

if __name__ == "__main__":
    check_availability()
