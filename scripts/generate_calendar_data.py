#!/usr/bin/env python3
"""Scan vault for dated files and generate calendar data JSON"""
import os, re, json
from datetime import datetime, date

VAULT = "/home/yunmai/知识付费工作室"
calendar_data = {}
date_pattern = re.compile(r'【?(\d{4})[-年](\d{1,2})[-月](\d{1,2})[日】]?')

# Only scan directories that get deployed to the website
deployed_roots = ["AI板块", "旅游板块", "OPC板块", "案例点评", "工具需求板块"]

for root, dirs, files in os.walk(VAULT):
    # Determine if this path is under a deployed root
    rel_from_vault = os.path.relpath(root, VAULT)
    parts = rel_from_vault.split(os.sep)
    top_dir = parts[0] if parts[0] and parts[0] != "." else ""
    if top_dir not in deployed_roots:
        continue

    for f in files:
        if not f.endswith(".md") or f.startswith("."):
            continue
        full_path = os.path.join(root, f)

        # Skip index.md and welcome pages
        if f in ("index.md", "欢迎.md"):
            continue

        m = date_pattern.search(f)
        if m:
            year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
            date_obj = date(year, month, day)
        else:
            mtime = os.path.getmtime(full_path)
            date_obj = datetime.fromtimestamp(mtime).date()

        date_str = date_obj.strftime("%Y-%m-%d")

        # Relative path from vault root
        rel_path = os.path.relpath(full_path, VAULT)

        # Strip date prefix from filename for website URL matching
        dir_part, file_part = os.path.split(rel_path.replace("\\", "/"))
        file_clean = re.sub(r'^【?\d{4}[-年]\d{1,2}[-月]\d{1,2}[日】]?[ _　]*', '', file_part)
        url_path = (dir_part + "/" + file_clean).replace(".md", "")
        if url_path.startswith("/"):
            url_path = url_path[1:]

        # Title
        title = file_part.replace(".md", "")
        title = re.sub(r'^【?\d{4}[-年]\d{1,2}[-月]\d{1,2}[日】]?[ _　]*', '', title)
        title = title.strip()
        if not title:
            title = file_part.replace(".md", "")

        section = top_dir if top_dir in deployed_roots else "其他"

        if date_str not in calendar_data:
            calendar_data[date_str] = []
        calendar_data[date_str].append({"title": title, "path": url_path, "section": section})

out_dir = "/tmp/content-site/docs/assets"
os.makedirs(out_dir, exist_ok=True)
with open(os.path.join(out_dir, "calendar-data.json"), "w", encoding="utf-8") as f:
    json.dump(calendar_data, f, ensure_ascii=False, indent=2)

print(f"Found {len(calendar_data)} dates with articles:")
for d in sorted(calendar_data.keys()):
    print(f"  {d}: {len(calendar_data[d])} articles")
    for a in calendar_data[d]:
        print(f"    {a['title']} -> /{a['path']}")
