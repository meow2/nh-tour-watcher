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
# ★URLはカレンダーが表示される正しいものを維持してください
BASE_URL = "https://ana-blue-hangar-tour.resv.jp/reserve/calendar.php?x=....." 
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

        # 全角数字などを正規化
        text_norm = unicodedata.normalize('NFKC', text_all)
        
        # 1. まず日付を特定する（セルの先頭の数字）
        day_match = re.match(r'^(\d+)', text_norm)
        if not day_match:
            continue # 日付がないセルは無視
        
        day_str = day_match.group(1)

        # 2. セル内の「すべての」空きパターンを探す
        # パターン: 「残」+「席数」+「時間」
        # 例: 残19:30 -> 席数1, 時間9:30
        # 例: 残1010:00 -> 席数10, 時間10:00
        
        # 正規表現の説明:
        # 残        : "残"という文字
        # (\d+)     : 席数 (グループ1)
        # (\d{1,2}:\d{2}) : 時間 (グループ2)
        # 以前の問題「残19:30」を「19席」と読まないよう、時間の直前で区切る
        
        iterator = re.finditer(r'残(\d+)(\d{1,2}:\d{2})', text_norm)
        
        for match in iterator:
            seats = int(match.group(1))
            time_str = match.group(2)
            
            # デバッグ用: 何を見つけたか表示
            # print(f"  [Check] {day_str}日 {time_str} -> 残{seats}")

            # 3. 判定: 席数が1以上か？
            if seats >= 1:
                # 4. 「○」や「△」などの記号も近くにあるか確認（念のため）
                #    なくても「残1」以上なら通知する設定にします（画像で残数が確実なので）
                
                status_emoji = "△" if seats <= 5 else "○"
                
                display_text = f"【{day_str}日 {time_str}】 {status_emoji} 残り{seats}席"
                print(f"  -> MATCH! Found: {display_text}")

                # 今日の日付 + ツアー日時 + 席数 をキーにして重複通知を防ぐ
                today = datetime.now().strftime("%Y-%m-%d")
                unique_key = f"{today}: {day_str} {time_str} {seats}"
                
                if not any(unique_key in s for s in notified_slots if s.startswith(today)):
                    found_slots.append(display_text)
                    new_notified_slots.append(unique_key)

    if found_slots:
        print(f"Found {len(found_slots)} slots.")
        # 通知メッセージ作成
        msg = "✈️ ANA工場見学 空き発生！\n\n" + "\n".join(found_slots) + f"\n\n予約: {BASE_URL}"
        send_line_message(msg)
        
        with open(NOTIFIED_FILE, "a") as f:
            for s in new_notified_slots: f.write(s + "\n")
    else:
        print("No availability found.")

if __name__ == "__main__":
    check_availability()
