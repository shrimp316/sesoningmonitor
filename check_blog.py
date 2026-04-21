import requests
import urllib3
import difflib
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
CONTENT_MAX_LEN = 3000

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


def fetch_post_content(url):
    """본문 텍스트와 해시를 함께 반환 (hash, content)"""
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        soup = BeautifulSoup(res.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header",
                         "iframe", "noscript", "meta", "link"]):
            tag.decompose()

        for tag in soup.find_all(True):
            for attr in list(tag.attrs):
                if attr.startswith("data-") or attr in ("id", "class"):
                    del tag[attr]

        article = (
            soup.find("article") or
            soup.find(attrs={"role": "main"}) or
            soup.find("main") or
            soup.body
        )

        content = article.get_text(separator=" ", strip=True) if article else ""
        content = re.sub(r'\s+', ' ', content).strip()

        content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        return content_hash, content[:CONTENT_MAX_LEN]
    except Exception as e:
        print(f"콘텐츠 가져오기 실패 ({url}): {e}")
        return None, ""


def get_diff_summary(old_text, new_text, max_lines=10):
    """변경 전/후 텍스트 비교 후 변경분 요약 반환"""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    diff = list(difflib.unified_diff(old_lines, new_lines, lineterm="", n=0))
    changes = [l for l in diff if l.startswith(("+", "-")) and not l.startswith(("---", "+++"))]
    if not changes:
        return "(변경 내용을 추출할 수 없음)"
    summary = "\n".join(changes[:max_lines])
    if len(changes) > max_lines:
        summary += f"\n... 외 {len(changes) - max_lines}줄 변경"
    return summary


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
            diff_text = get_diff_summary(p.get("old_content", ""), p.get("new_content", ""))
            body += f"  📝 {p['title']}\n  {p['url']}\n\n"
            body += f"  [변경 내용]\n{diff_text}\n\n"

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
        current_hash, current_content = fetch_post_content(url)
        new_state[url] = {"title": post["title"], "hash": current_hash, "content": current_content}

        if url not in previous_state:
            new_posts.append(post)
            print(f"새 글: {post['title']}")
        elif previous_state[url].get("hash") != current_hash:
            modified_posts.append({
                **post,
                "old_content": previous_state[url].get("content", ""),
                "new_content": current_content,
            })
            print(f"수정됨: {post['title']}")
        else:
            print(f"변경 없음: {post['title']}")

    if new_posts or modified_posts:
        send_email(new_posts, modified_posts)

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
