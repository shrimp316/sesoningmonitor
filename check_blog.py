import requests
from bs4 import BeautifulSoup
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

URL = "https://www.seasoninggames.com/ko/blog"
STATE_FILE = "blog_state.json"

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_PASSWORD = os.environ["GMAIL_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]


def fetch_posts():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(URL, headers=headers, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")

    posts = []
    # Wix 블로그 구조: 각 포스트 링크 수집
    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)
        if "/post/" in href and title:
            full_url = href if href.startswith("http") else "https://www.seasoninggames.com" + href
            posts.append({"title": title, "url": full_url})

    # 중복 제거
    seen = set()
    unique = []
    for p in posts:
        if p["url"] not in seen:
            seen.add(p["url"])
            unique.append(p)
    return unique


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_state(posts):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f, ensure_ascii=False, indent=2)


def send_email(new_posts):
    subject = f"[Seasoning Games] 새 블로그 글 {len(new_posts)}개 업데이트!"
    body = "새로운 글이 올라왔어요:\n\n"
    for p in new_posts:
        body += f"📌 {p['title']}\n{p['url']}\n\n"

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
    print(f"이메일 발송 완료: {len(new_posts)}개 새 글")


def main():
    current = fetch_posts()
    previous_urls = {p["url"] for p in load_state()}

    new_posts = [p for p in current if p["url"] not in previous_urls]

    if new_posts:
        print(f"새 글 발견: {len(new_posts)}개")
        send_email(new_posts)
        save_state(current)
    else:
        print("새 글 없음")


if __name__ == "__main__":
    main()
