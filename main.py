import os
import requests
import json
from bs4 import BeautifulSoup
from datetime import datetime
import re

# 設定
BASE_URL = "https://ana-blue-hangar-tour.resv.jp/reserve/calendar.php"
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
    except Exception:
        pass # エラーはログに出るためここでは無視

def get_soup(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, 'lxml')
    except Exception as e:
        print(f"Error: {e}")
        return None

def check_availability():
    # 通知済みリスト読み込み
    notified_slots = []
    if os.path.exists(NOTIFIED_FILE):
        with open(NOTIFIED_FILE, "r") as f:
            notified_slots = [line.strip() for line in f.readlines()]

    found_slots = []
    new_notified_slots = []
    
    # URLリスト作成（今月と次月）
    urls = [BASE_URL]
    soup = get_soup(BASE_URL)
    if soup:
        next_link = soup.find('a', string=re.compile(r'次月|翌月|Next'))
        if next_link and next_link.get('href'):
            href = next_link.get('href')
            if not href.startswith('http'):
                urls.append("https://ana-blue-hangar-tour.resv.jp/reserve/" + href)

    # 巡回
    print(f"Checking URLs: {urls}")
    for url in urls:
        soup = get_soup(url)
        if not soup: continue
        
        for cell in soup.find_all('td'):
            day_text = cell.get_text(strip=True)
            link = cell.find('a')
            
            if not day_text or not link: continue
            
            cell_text = cell.get_text(strip=True) # 全テキスト
            link_text = link.get_text(strip=True) # リンク内テキスト
            
            is_avail = False
            # 判定: ○か△、または数字が2以上
            if "○" in cell_text or "◎" in cell_text or "△" in cell_text:
                is_avail = True
            else:
                nums = re.findall(r'\d+', link_text)
                for n in nums:
                    if int(n) >= 2: # 2席以上
                        is_avail = True
                        break
            
            if is_avail:
                # テキスト整形して記録
                clean_text = re.sub(r'\s+', ' ', cell_text).strip()
                today = datetime.now().strftime("%Y-%m-%d")
                unique_key = f"{today}: {clean_text}"
                
                # 今日まだ通知してないなら追加
                if not any(unique_key in s for s in notified_slots if s.startswith(today)):
                    found_slots.append(clean_text)
                    new_notified_slots.append(unique_key)

    if found_slots:
        print(f"Found: {len(found_slots)}")
        msg = "✈️ ANA工場見学 空きあり(2席以上)\n\n" + "\n".join(found_slots) + f"\n\n予約: {BASE_URL}"
        send_line_message(msg)
        with open(NOTIFIED_FILE, "a") as f:
            for s in new_notified_slots: f.write(s + "\n")
    else:
        print("No slots found.")

if __name__ == "__main__":
    check_availability()
