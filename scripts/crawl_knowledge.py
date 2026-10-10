"""
电商知识库爬虫 v2 — 京东帮助中心
两阶段爬取：分类列表页 → 文章详情页
"""
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from loguru import logger

# ========== 配置 ==========
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_DELAY = 1.5   # 爬虫礼仪：请求间隔
TIMEOUT = 15.0
MAX_ARTICLES_PER_CATEGORY = 5   # 每个分类最多抓取文章数
OUTPUT_DIR = Path("data/crawled")

# 京东帮助中心分类页（关注客服高频问题类目）
JD_CATEGORY_PAGES = [
    {"url": "https://help.jd.com/user/issue/list-112.html", "category": "售后政策"},
    {"url": "https://help.jd.com/user/issue/list-116.html", "category": "退款说明"},
    {"url": "https://help.jd.com/user/issue/list-132.html", "category": "价格保护"},
    {"url": "https://help.jd.com/user/issue/list-151.html", "category": "会员介绍"},
    {"url": "https://help.jd.com/user/issue/list-171.html", "category": "支付流程"},
    {"url": "https://help.jd.com/user/issue/list-177.html", "category": "京东白条"},
    {"url": "https://help.jd.com/user/issue/list-29.html", "category": "购物流程"},
    {"url": "https://help.jd.com/user/issue/list-30.html", "category": "促销咨询"},
    {"url": "https://help.jd.com/user/issue/list-49.html", "category": "修改订单"},
    {"url": "https://help.jd.com/user/issue/list-50.html", "category": "取消订单"},
    {"url": "https://help.jd.com/user/issue/list-80.html", "category": "发货与签收"},
    {"url": "https://help.jd.com/user/issue/list-83.html", "category": "配送时效"},
    {"url": "https://help.jd.com/user/issue/list-85.html", "category": "配送运费"},
    {"url": "https://help.jd.com/user/issue/list-499.html", "category": "发票开具"},
    {"url": "https://help.jd.com/user/issue/list-505.html", "category": "发票类型"},
    {"url": "https://help.jd.com/user/issue/list-149.html", "category": "账户安全"},
    {"url": "https://help.jd.com/user/issue/list-488.html", "category": "售后常见问题"},
    {"url": "https://help.jd.com/user/issue/109-188.html", "category": "配送费收取标准"},
    {"url": "https://help.jd.com/user/issue/104-137.html", "category": "物流查询"},
]


class JdHelpCrawler:
    """京东帮助中心爬虫（两阶段）"""
    
    def __init__(self):
        self.client = httpx.AsyncClient(
            headers=HEADERS, timeout=TIMEOUT, follow_redirects=True
        )
        self.collected: list[dict] = []
    
    async def close(self):
        await self.client.aclose()
    
    async def fetch(self, url: str) -> Optional[str]:
        """抓取页面（自动处理编码）"""
        try:
            await asyncio.sleep(REQUEST_DELAY)
            resp = await self.client.get(url)
            resp.raise_for_status()
            
            raw = resp.content
            # 京东帮助中心使用 GBK 编码
            if "jd.com" in url:
                return raw.decode("gbk", errors="ignore")
            
            # 其他站点尝试从 header 或 meta 获取编码
            charset = resp.charset_encoding or "utf-8"
            try:
                return raw.decode(charset, errors="ignore")
            except (LookupError, UnicodeDecodeError):
                return raw.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Fetch failed: {url} — {e}")
            return None
    
    def clean_text(self, text: str) -> str:
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        return text.strip()
    
    def clean_line(self, line: str) -> str:
        """单行清洗（保留换行结构）"""
        line = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', line)
        line = re.sub(r'\s+', ' ', line)
        return line.strip()
    
    # ========== 阶段1：从分类页提取文章链接 ==========
    def extract_article_links(self, html: str, base_url: str) -> list[tuple[str, str]]:
        """从分类列表页提取文章链接"""
        soup = BeautifulSoup(html, "html.parser")
        articles = []
        seen = set()
        
        for a in soup.find_all("a", href=True):
            href = a["href"]
            title = a.get_text(strip=True)
            
            # 匹配文章页 URL 格式 /user/issue/109-188.html
            if re.search(r'/user/issue/\d+-\d+\.html', href):
                if href.startswith("//"):
                    href = "https:" + href
                elif href.startswith("/"):
                    href = "https://help.jd.com" + href
                
                if href not in seen and title and len(title) >= 4:
                    seen.add(href)
                    articles.append((href, title))
        
        return articles
    
    # ========== 阶段2：从文章页提取内容 ==========
    def extract_article_content(self, html: str, url: str, category: str, title_hint: str) -> Optional[dict]:
        """从文章页提取正文内容"""
        soup = BeautifulSoup(html, "html.parser")
        
        # 移除无关元素
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        
        # 尝试定位正文区域（京东帮助文章正文容器为 .contxt）
        content_selectors = [
            ".contxt",                      # 京东帮助中心正文
            "#pdfContainer .container",
            ".issue-content", ".article-content", ".help-content",
            "#content", ".content-box", ".detail-content",
            ".main-content", ".issue-detail",
        ]
        
        content_elem = None
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                break
        
        # fallback: 取 body 主体文本
        if not content_elem:
            content_elem = soup.body or soup
        
        # 逐行提取并清洗（保留换行结构，避免整页合并成一行）
        raw_lines = content_elem.get_text("\n", strip=True).split("\n")
        
        # 清理：去除页头页脚噪音
        noise_markers = [
            "品类齐全，轻松购物", "多仓直发，极速配送", "正品行货，精致服务",
            "天天低价，畅选无忧", "English Site", "Copyright",
            "京公网安备", "京ICP证", "消费者维权热线",
            "你好，请登录", "免费注册", "我的订单", "我的京东", "京东会员",
            "企业采购", "手机京东", "关注京东", "客户服务", "网站导航",
            "新手指南", "常见问题分类",
        ]
        
        cleaned_lines = []
        for line in raw_lines:
            line = self.clean_line(line)
            if len(line) < 6:  # 跳过短行
                continue
            if any(marker in line for marker in noise_markers):
                continue
            cleaned_lines.append(line)
        
        content = "\n".join(cleaned_lines)
        
        # 验证内容有效性
        if len(content) < 50:
            return None
        
        # 提取标题
        h1 = soup.find("h1")
        h2 = soup.find("h2")
        title = self.clean_text(h1.get_text()) if h1 else (
            self.clean_text(h2.get_text()) if h2 else title_hint
        )
        if not title or len(title) < 4:
            title = title_hint
        # 清理标题中的装饰符
        title = title.strip("· 　\t")
        
        return {
            "category": category,
            "title": title[:100],
            "content": content[:3000],  # 限制长度
            "source_url": url,
            "crawled_at": datetime.now().isoformat(),
        }
    
    # ========== 主流程 ==========
    async def crawl(self):
        """两阶段爬取"""
        all_article_urls = []
        
        # 阶段1: 收集文章链接
        logger.info("=" * 50)
        logger.info("Phase 1: Collecting article URLs from category pages")
        logger.info("=" * 50)
        
        for cat in JD_CATEGORY_PAGES:
            url = cat["url"]
            category = cat["category"]
            logger.info(f"[{category}] {url}")
            
            html = await self.fetch(url)
            if not html:
                continue
            
            # 如果本身就是文章页（如 109-188），直接处理
            if re.search(r'/user/issue/\d+-\d+\.html$', url) and 'list-' not in url:
                entry = self.extract_article_content(html, url, category, category)
                if entry:
                    self.collected.append(entry)
                    logger.info(f"  ✓ Article content extracted ({len(entry['content'])} chars)")
                continue
            
            # 列表页：提取文章链接
            articles = self.extract_article_links(html, url)
            logger.info(f"  Found {len(articles)} articles")
            
            for article_url, article_title in articles[:MAX_ARTICLES_PER_CATEGORY]:
                all_article_urls.append({
                    "url": article_url,
                    "title": article_title,
                    "category": category,
                })
        
        # 阶段2: 抓取文章内容
        logger.info("=" * 50)
        logger.info(f"Phase 2: Fetching {len(all_article_urls)} articles")
        logger.info("=" * 50)
        
        for i, article in enumerate(all_article_urls, 1):
            logger.info(f"[{i}/{len(all_article_urls)}] {article['title']}")
            
            html = await self.fetch(article["url"])
            if not html:
                continue
            
            entry = self.extract_article_content(
                html, article["url"], article["category"], article["title"]
            )
            if entry:
                self.collected.append(entry)
                logger.info(f"  ✓ Extracted ({len(entry['content'])} chars)")
            else:
                logger.info(f"  ✗ No valid content")
        
        logger.info(f"\nTotal collected: {len(self.collected)} articles")
        return self.collected
    
    def save_to_json(self, filepath: str = None) -> str:
        """保存到 JSON"""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filepath = str(OUTPUT_DIR / f"jd_crawled_{timestamp}.json")
        
        # 去重（按URL）
        seen = set()
        unique = []
        for entry in self.collected:
            if entry["source_url"] not in seen:
                seen.add(entry["source_url"])
                unique.append(entry)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(unique, f, ensure_ascii=False, indent=2)
        
        logger.info(f"Saved {len(unique)} entries to {filepath}")
        return filepath


async def main():
    crawler = JdHelpCrawler()
    try:
        await crawler.crawl()
        output = crawler.save_to_json()
        print(f"\n✅ Crawled data saved: {output}")
    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
