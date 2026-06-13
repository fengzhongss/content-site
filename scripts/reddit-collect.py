#!/usr/bin/env python3
"""
Reddit 多社区采集 · 按类型分类
采集源（4类 × 9社区）→ 输出到 _reddit_data/{类型}/{社区}/ 目录

工作方式:
  首次 (--init): 扫各社区 hot + top 3月
  每日: 扫 hot + new

输出:
  _reddit_data/{反馈型|故事型|干货型|展示型}/{社区名}/
  每帖一个 .md 文件
"""

import os, re, sys, json, hashlib, time, logging
from datetime import datetime, timezone
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────────
COMMUNITIES = {
    "反馈型": ["SideProject", "microsaas"],
    "故事型": ["indiehackers", "startups"],
    "干货型": ["SEO", "marketing", "DigitalMarketing"],
    "展示型": ["InternetIsBeautiful", "artificial"],
}

OUTPUT_ROOT = Path("_reddit_data")
STATE_FILE = Path.home() / ".reddit_collect_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

DAILY_LIMIT_PER_SUB = 10   # 每个子社区每日最多保存
INIT_LIMIT_PER_SUB = 30    # 初始化每个子社区最多

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"seen": {}, "total": 0}

def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def post_hash(title, subreddit):
    return hashlib.md5(f"{subreddit}:{title.lower().strip()}".encode()).hexdigest()[:16]

def fetch_page(url):
    import urllib.request, urllib.error
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        log.warning(f"  ⚠ 请求失败: {url[:60]}... {e}")
        return None

def parse_posts(html, subreddit):
    """Parse old.reddit.com HTML listing into post dicts."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    posts = []
    for row in soup.find_all("div", class_="thing"):
        title_el = row.find("a", class_="title")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        url = title_el.get("href", "")
        if url.startswith("/r/"):
            url = f"https://old.reddit.com{url}"
        pid = row.get("data-fullname", "") or post_hash(title, subreddit)
        score_el = row.find("div", class_="score")
        score = int(score_el.get_text(strip=True)) if score_el and score_el.get_text(strip=True).lstrip("-").isdigit() else 0
        comments_el = row.find("a", class_="comments")
        comments = 0
        if comments_el:
            txt = comments_el.get_text(strip=True)
            m = re.search(r"(\d+)", txt)
            if m: comments = int(m.group(1))
        time_el = row.find("time")
        posted = time_el.get("datetime", "") if time_el else ""
        tagline = row.find("p", class_="tagline")
        author_el = tagline.find("a", class_="author") if tagline else None
        author = author_el.get_text(strip=True) if author_el else "[deleted]"
        # Fetch body text
        body = ""
        expando = row.find("div", class_="expando")
        if expando:
            body_div = expando.find("div", class_="md")
            if body_div:
                body = body_div.get_text(strip=True)[:500]
        posts.append({
            "id": pid,
            "title": title,
            "url": url,
            "score": score,
            "comments": comments,
            "author": author,
            "posted": posted,
            "body": body,
            "subreddit": subreddit,
        })
    return posts

def scrape_list(url, label, subreddit, state, max_save=10):
    html = fetch_page(url)
    if not html:
        return 0, []
    posts = parse_posts(html, subreddit)
    saved = 0
    items = []
    for p in posts:
        h = post_hash(p["title"], subreddit)
        if h in state["seen"]:
            continue
        state["seen"][h] = datetime.now(timezone.utc).isoformat()
        items.append(p)
        saved += 1
        if saved >= max_save:
            break
    return saved, items

def save_post(post, community_type, subreddit):
    """Save a single post as markdown file."""
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    safe_title = re.sub(r'[<>:"/\\|?*]', "_", post["title"])[:60]
    fname = f"{date_str}_{safe_title}.md"
    outdir = OUTPUT_ROOT / community_type / subreddit
    outdir.mkdir(parents=True, exist_ok=True)
    fpath = outdir / fname
    if fpath.exists():
        return False
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(f"""---
title: "{post['title']}"
community_type: "{community_type}"
subreddit: "r/{subreddit}"
date: "{post['posted'][:10] if post['posted'] else date_str}"
url: "{post['url']}"
score: {post['score']}
comments: {post['comments']}
author: "{post['author']}"
collected_at: "{datetime.now(timezone.utc).isoformat()}"
status: "未分析"
---

# {post['title']}

> **来源：** r/{subreddit} · {community_type} · ⬆ {post['score']} · 💬 {post['comments']} · u/{post['author']}

{post['body']}

---
*由自动化采集于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}*
""")
    return True

def run_collection(label, max_per_sub):
    state = load_state()
    total = {"反馈型": 0, "故事型": 0, "干货型": 0, "展示型": 0}
    for ctype, subs in COMMUNITIES.items():
        log.info(f"\n{'='*40}\n{ctype}\n{'='*40}")
        for sub in subs:
            log.info(f"  → r/{sub}")
            count = 0
            for sort in ["hot", "new"]:
                url = f"https://old.reddit.com/r/{sub}/{sort}/?limit=25"
                saved, items = scrape_list(url, sort, sub, state, max_save=max_per_sub - count)
                count += saved
                if count >= max_per_sub:
                    break
            saved_actual = 0
            for p in items[:max_per_sub]:
                if save_post(p, ctype, sub):
                    saved_actual += 1
            total[ctype] += saved_actual
            log.info(f"   保存 {saved_actual} 篇")
    save_state(state)
    return total

def run_daily():
    log.info("📡 Reddit 每日采集开始")
    total = run_collection("每日", DAILY_LIMIT_PER_SUB)
    all_count = sum(total.values())
    if all_count > 0:
        detail = " | ".join(f"{k}={v}" for k, v in total.items() if v > 0)
        print(f"✅ 采集到 {all_count} 篇: {detail}")
    else:
        print("⏸️  无新帖子")
    return all_count

def run_initial():
    log.info("📡 Reddit 初始化采集（深度扫描）")
    total = run_collection("初始化", INIT_LIMIT_PER_SUB)
    all_count = sum(total.values())
    print(f"✅ 初始化完成: {all_count} 篇")
    return all_count

def main():
    if "--init" in sys.argv:
        run_initial()
    else:
        run_daily()

if __name__ == "__main__":
    main()
