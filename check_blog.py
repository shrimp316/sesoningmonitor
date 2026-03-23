import requests
from bs4 import BeautifulSoup
import json
import os
import hashlib
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
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"]
        title = a.get_text(strip=True)
        if "/post/" in href and title:
            full_url = href if href.startswith("http") else "https://www.seasoninggames.com" + href
            if full_url not in seen:
                seen.add(full_url)
                posts.append({"title": title, "url": full_url})

    return posts


def fetch_post_hash(url):
    """각 글의 본문 내용을 가져와서 해시값 생성"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        content = soup.get_text(separator=" ", strip=True)

        return hashlib.md5(content.encode("utf-8")).hexdigest()
    except Exception as e:
        print(f"해시 생성 실패 ({url}): {e}")
        return None


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def send_email(new_posts, modified_posts):
    parts = []
    if new_posts:
        parts.append(f"새 글 {len(new_posts)}개 업데이트!")
    if modified_posts:
        parts.append(f"수정된 글 {len(modified_posts)}개 감지!")
    subject = "[Seasoning Games] " + " / ".join(parts)

    body = ""
    if new_posts:
        body += "🆕 새로운 글:\n"
        for p in new_posts:
            body += f"  📌 {p['title']}\n  {p['url']}\n\n"
    if modified_posts:
        body += "✏️ 수정된 글:\n"
        for p in modified_posts:
            body += f"  📝 {p['title']}\n  {p['url']}\n\n"

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
    print(f"이메일 발송 완료 - 새 글: {len(new_posts)}개, 수정: {len(modified_posts)}개")


def main():
    current_posts = fetch_posts()
    previous_state = load_state()
    new_state = {}

    new_posts = []
    modified_posts = []

    for post in current_posts:
        url = post["url"]
        current_hash = fetch_post_hash(url)
        new_state[url] = {"title": post["title"], "hash": current_hash}

        if url not in previous_state:
            new_posts.append(post)
            print(f"새 글: {post['title']}")
        elif previous_state[url].get("hash") != current_hash:
            modified_posts.append(post)
            print(f"수정됨: {post['title']}")
        else:
            print(f"변경 없음: {post['title']}")

    if new_posts or modified_posts:
        send_email(new_posts, modified_posts)

    save_state(new_state)


if __name__ == "__main__":
    main()
