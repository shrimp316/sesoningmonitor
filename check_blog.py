import requests
import urllib3
from bs4 import BeautifulSoup
import json
import os
import re
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

URL = "https://www.seasoninggames.com/ko/blog"
STATE_FILE = "blog_state.json"

GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", "")


def fetch_posts():
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(URL, headers=headers, timeout=15, verify=False)
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
    """본문 텍스트만 추출해서 해시 생성 (동적 요소 제거)"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        soup = BeautifulSoup(res.text, "html.parser")

        # 동적/불필요 태그 전부 제거
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "iframe", "noscript", "meta", "link"]):
            tag.decompose()

        # data-*, id, class 속성 제거 (세션/토큰 등 동적 값 포함 가능)
        for tag in soup.find_all(True):
            for attr in list(tag.attrs):
                if attr.startswith("data-") or attr in ("id", "class"):
                    del tag[attr]

        # 본문 영역만 추출
        article = (
            soup.find("article") or
            soup.find(attrs={"role": "main"}) or
            soup.find("main") or
            soup.body
        )

        content = article.get_text(separator=" ", strip=True) if article else ""

        # 공백 정규화
        content = re.sub(r'\s+', ' ', content).strip()

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

    # 최신 글 정보를 latest_post.json에 저장 (홈페이지 배너용)
    if current_posts:
        import datetime
        latest = current_posts[0]
        latest_data = {
            "title": latest["title"],
            "url": latest["url"],
            "updated_at": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        }
        os.makedirs("data", exist_ok=True)
        with open("data/latest_post.json", "w", encoding="utf-8") as f:
            json.dump(latest_data, f, ensure_ascii=False, indent=2)
        print(f"latest_post.json 업데이트: {latest['title']}")

    save_state(new_state)


if __name__ == "__main__":
    main()
