#!/usr/bin/env python3
"""
RackNerd 特价套餐抓取脚本。

从 https://www.racknerd.com/specials/ 抓取套餐数据，生成 data.json，
供 index.html 动态渲染。配合 .github/workflows/sync.yml 实现每日自动同步。

用法：
    python scraper.py

可选环境变量：
    RACKNERD_AFF_ID   你的 RackNerd 推广 ID（数字）。设置后购物车链接会被
                      转换为 aff.php 联盟链接；留空则使用官方原始链接。
"""

import json
import os
import re
import sys
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# ===== 配置 =====
SOURCE_URL = "https://www.racknerd.com/specials/"
OUTPUT = "data.json"
AFF_ID = os.environ.get("RACKNERD_AFF_ID", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def build_order_url(cart_url: str) -> str:
    """把官方购物车链接 (cart.php?a=add&pid=952) 转换为带推广参数的联盟链接。"""
    if not AFF_ID:
        return cart_url
    pid = re.search(r"pid=(\d+)", cart_url)
    if not pid:
        return cart_url
    return f"https://my.racknerd.com/aff.php?aff={AFF_ID}&pid={pid.group(1)}"


def scrape() -> dict:
    resp = requests.get(SOURCE_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    cards = soup.select(".plan-card")
    if not cards:
        raise RuntimeError("页面结构可能已变化，未找到 .plan-card 节点，保留旧数据。")

    plans = []
    for card in cards:
        title_el = card.select_one(".plan-header h3")
        price_el = card.select_one(".price")
        features_el = card.select_one(".plan-features")
        link_el = card.select_one(".plan-footer a")
        if not title_el or not price_el:
            continue

        price = price_el.get_text(" ", strip=True)
        price = re.sub(r"\s+", " ", price).replace("$ ", "$").strip()

        specs = [
            li.get_text(" ", strip=True)
            for li in features_el.select("li")
        ] if features_el else []

        cart_url = link_el.get("href", "") if link_el else ""

        plans.append({
            "title": title_el.get_text(strip=True),
            "price": price,
            "specs": specs,
            "featured": "featured" in (card.get("class") or []),
            "url": build_order_url(cart_url),
        })

    return {
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": SOURCE_URL,
        "plans": plans,
    }


def main() -> None:
    data = scrape()

    old = None
    if os.path.exists(OUTPUT):
        with open(OUTPUT, encoding="utf-8") as f:
            old = json.load(f)

    # 套餐内容未变化时不重写文件，避免每日产生无意义提交
    if old and old.get("plans") == data["plans"]:
        print(f"套餐无变化，跳过更新（共 {len(data['plans'])} 个套餐）。")
        return

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"成功更新 {len(data['plans'])} 个特价套餐数据！")
    for p in data["plans"]:
        flag = " ★" if p["featured"] else ""
        print(f"  - {p['title']}{flag} | {p['price']}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # 失败则退出非 0，workflow 会保留旧数据
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
