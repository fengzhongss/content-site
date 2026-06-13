#!/usr/bin/env python3
"""
采集 r/SomebodyMakeThis 中适合一人公司的轻量工具类求助帖。

工作方式:
  首次运行 (--init): 扫过去一年的 top 帖
  每日运行 (默认):  扫 hot + new 帖
  
过滤规则:
  排除需要硬件的 (硬件/PCB/3D打印/实体产品等关键词)
  排除成熟竞品已存在的
  保留纯软件/轻量工具方向

输出位置:
  通用板块/素材库/Reddit采集/SomethingMakeThis/

去重:
  用标题 hash 记录已处理帖子，避免重复输出
"""

import os
import re
import sys
import json
import hashlib
import subprocess
import logging
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

# ── 配置 ──────────────────────────────────────────────────────────────────

SUBREDDIT = "SomebodyMakeThis"
VAULT_ROOT = Path("/home/yunmai/知识付费工作室")
OUTPUT_DIR = VAULT_ROOT / "通用板块" / "素材库" / "Reddit采集" / "SomethingMakeThis"
STATE_FILE = Path(os.path.expanduser("~/.hermes/scripts/.reddit_smt_state.json"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

# 排除硬件相关的关键词（命中任一就跳过）
HARDWARE_KEYWORDS = re.compile(
    r"(hardware|device|pcb|circuit|3d\s*print|manufacturing|"
    r"supply\s*chain|physical\s*product|hardware\s*product|"
    r"injection\s*mold|mould|arduino|raspberry\s*pi|esp32|esp8266|"
    r"robot|drone|iot\s*device|sensor|嵌入式|硬件|实体产品|量产|模具)",
    re.IGNORECASE,
)

# 排除已存在成熟竞品的关键词
COMPETITOR_KEYWORDS = re.compile(
    r"(already\s+exists|already\s+have|existing\s+solution|"
    r"like\s+.*but|similar\s+to|alternative\s+to|"
    r"clone\s+of|replacement\s+for|市场上已有|已经有)",
    re.IGNORECASE,
)

# 鼓励保留的方向（轻量工具类）
ENCOURAGE_KEYWORDS = re.compile(
    r"(chrome\s*extension|browser\s*extension|web\s*app|mobile\s*app|"
    r"telegram\s*bot|discord\s*bot|slack\s*bot|whatsapp\s*bot|"
    r"saas|api|cli\s*tool|desktop\s*app|electron|pwa|"
    r"notion\s*template|obsidian\s*plugin|vscode\s*extension|"
    r"script|automation|workflow|小工具|插件|小程序|bot|机器人|浏览器扩展)",
    re.IGNORECASE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("reddit_smt")


# ── 状态管理 ──────────────────────────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"seen_titles": [], "total_saved": 0}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def title_hash(title):
    return hashlib.md5(title.strip().lower().encode()).hexdigest()[:12]


def is_seen(state, title):
    return title_hash(title) in state["seen_titles"]


def mark_seen(state, title):
    h = title_hash(title)
    if h not in state["seen_titles"]:
        state["seen_titles"].append(h)
    # 保持列表不无限增长
    if len(state["seen_titles"]) > 10000:
        state["seen_titles"] = state["seen_titles"][-5000:]


# ── 抓取 ──────────────────────────────────────────────────────────────────

def fetch_old_reddit(url):
    """用 curl 抓取 old.reddit.com HTML（requests 被 Cloudflare 拦截）。"""
    cmd = [
        "curl", "-s", "--max-time", "20",
        "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "-H", "Accept: text/html",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-L",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    if result.returncode != 0:
        raise RuntimeError(f"curl failed (exit {result.returncode}): {result.stderr[:200]}")
    return BeautifulSoup(result.stdout, "lxml")


def parse_posts(soup):
    """从 old.reddit.com 的 HTML 页面解析帖子列表。"""
    posts = []
    for thing in soup.select("div.thing"):
        title_el = thing.select_one("a.title")
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        url_rel = title_el.get("href", "")
        permalink = thing.select_one("a.bylink")
        post_url = permalink.get("href", "") if permalink else ""

        # 分数
        score_el = thing.select_one("div.score.unvoted")
        score = 0
        if score_el:
            score_text = score_el.get_text(strip=True)
            try:
                score = int(score_text.replace(" points", "").replace(" point", ""))
            except ValueError:
                score = 0

        # 评论数
        comments_el = thing.select_one("a.bylink")
        comments = 0
        if comments_el:
            match = re.search(r"(\d+)\s+comment", comments_el.get_text(strip=True))
            if match:
                comments = int(match.group(1))

        # 内容（selftext 或 link）
        usertext = thing.select_one("div.usertext-body div.md")
        selftext = usertext.get_text(strip=True) if usertext else ""

        # 是否是 link post (不是 self post)
        domain_el = thing.select_one("span.domain")
        is_link = domain_el and "self." not in domain_el.get_text()

        posts.append({
            "title": title,
            "url": url_rel if url_rel.startswith("http") else f"https://old.reddit.com{url_rel}",
            "permalink": f"https://old.reddit.com{post_url}" if post_url else "",
            "score": score,
            "comments": comments,
            "selftext": selftext,
            "is_link": is_link,
        })

    return posts


def get_next_page(soup):
    """找到 "next" 按钮的 URL。"""
    next_el = soup.select_one("span.next-button a")
    if next_el and next_el.get("href"):
        return next_el["href"]
    return None


# ── 过滤 ──────────────────────────────────────────────────────────────────

def should_keep(post):
    """判断帖子是否值得保存（一人公司可做的轻量工具）。"""
    text = f"{post['title']} {post['selftext']}"

    # 排除硬件
    if HARDWARE_KEYWORDS.search(text):
        return False, "硬件相关"

    # 排除成熟竞品
    if COMPETITOR_KEYWORDS.search(text):
        return False, "已有竞品"

    # 鼓励保留的方向
    if ENCOURAGE_KEYWORDS.search(text):
        return True, "轻量工具方向"

    # 不确定的，保留让用户判断
    if post["score"] >= 5 and post["selftext"]:
        return True, "人工判断"

    return False, "不明确"


# ── 输出 ──────────────────────────────────────────────────────────────────

def save_post(post, reason):
    """将帖子保存为 markdown 文件。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 文件名用日期 + 标题 slug
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", post["title"]).strip("-")[:60]
    filename = f"{today}_{slug}.md"
    filepath = OUTPUT_DIR / filename

    # 避免同名覆盖，加序号
    counter = 1
    while filepath.exists():
        filename = f"{today}_{slug}_{counter}.md"
        filepath = OUTPUT_DIR / filename
        counter += 1

    content = f"""---
source: r/SomebodyMakeThis
date: {today}
score: {post['score']}
comments: {post['comments']}
filter: {reason}
---

# {post['title']}

[[score: {post['score']} | comments: {post['comments']}]]

{post['selftext']}

---

[查看原文]({post['permalink'] or post['url']})
"""
    filepath.write_text(content)
    log.info(f"  ✅ saved: {filename} ({reason})")
    return filename


# ── 主逻辑 ────────────────────────────────────────────────────────────────

def scrape_list(url, label, state, max_save=0):
    """抓取一个帖子列表页及后续分页，返回新保存的帖子数。
    max_save: 最多保存多少篇（0=不限制）
    """
    page_url = url
    page_num = 1
    saved = 0
    skipped = 0

    while page_url and page_num <= 50:  # 最多50页
        if max_save > 0 and saved >= max_save:
            log.info(f"  [{label}] 已达当日上限 {max_save} 篇，停止翻页")
            break

        log.info(f"  [{label}] 抓取第 {page_num} 页: {page_url[:80]}...")
        try:
            soup = fetch_old_reddit(page_url)
            posts = parse_posts(soup)

            if not posts:
                log.info(f"  [{label}] 本页无帖子，结束")
                break

            for post in posts:
                if max_save > 0 and saved >= max_save:
                    break

                if is_seen(state, post["title"]):
                    skipped += 1
                    continue

                keep, reason = should_keep(post)
                if keep:
                    save_post(post, reason)
                    mark_seen(state, post["title"])
                    saved += 1
                else:
                    skipped += 1

            page_url = get_next_page(soup)
            page_num += 1

        except Exception as e:
            log.error(f"  [{label}] 第 {page_num} 页出错: {e}")
            break

    log.info(f"  [{label}] 完成: 保存 {saved} / 跳过 {skipped}")
    return saved


def run_initial():
    """首次运行：扫过去一年 top 帖。"""
    log.info("=" * 60)
    log.info("首次采集：过去一年 top 帖")
    state = load_state()
    total = 0

    # top 帖 (一年的)
    url = f"https://old.reddit.com/r/{SUBREDDIT}/top/?t=year&limit=100"
    total += scrape_list(url, "top-year", state)

    # 再加 hot 帖
    url = f"https://old.reddit.com/r/{SUBREDDIT}/hot/?limit=100"
    total += scrape_list(url, "hot", state)

    state["total_saved"] = state.get("total_saved", 0) + total
    save_state(state)
    log.info(f"首次采集完成，共保存 {total} 篇新帖子")
    return total


def run_daily():
    """每日运行：扫 hot + new 帖，上限30篇。"""
    log.info("=" * 60)
    log.info("每日采集（上限30篇）")
    state = load_state()
    total = 0
    DAILY_LIMIT = 30

    url = f"https://old.reddit.com/r/{SUBREDDIT}/hot/?limit=25"
    total += scrape_list(url, "hot", state, max_save=DAILY_LIMIT)

    remaining = DAILY_LIMIT - total
    if remaining > 0:
        url = f"https://old.reddit.com/r/{SUBREDDIT}/new/?limit=25"
        total += scrape_list(url, "new", state, max_save=remaining)

    state["total_saved"] = state.get("total_saved", 0) + total
    save_state(state)

    if total > 0:
        log.info(f"每日采集完成，新增 {total} 篇")
    else:
        log.info("无新帖子")

    # 打印汇总
    total_saved = state.get("total_saved", 0)
    file_count = len(list(OUTPUT_DIR.glob("*.md"))) if OUTPUT_DIR.exists() else 0
    log.info(f"累计保存: {total_saved} 篇, 文件数: {file_count}")

    return total


def main():
    if "--init" in sys.argv:
        count = run_initial()
    else:
        count = run_daily()

    # 输出简洁结果供 cron 脚本消费
    if count > 0:
        print(f"✅ 采集到 {count} 篇新帖子 → {OUTPUT_DIR}")
    else:
        print("⏸️  无新帖子")


if __name__ == "__main__":
    main()
