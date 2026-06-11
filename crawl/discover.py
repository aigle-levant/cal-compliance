import asyncio
import json
from pathlib import Path
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

TARGET_SITEMAP = "https://www.dir.ca.gov/sitemap/sitemap.html"
OUTPUT_FILE = "../data/urls.jsonl"

async def discover_regulatory_urls():
    print(f"Targeting HTML directory mapping page: {TARGET_SITEMAP}")
    
    async with AsyncWebCrawler() as crawler:
        # Fast prefetch discovery config
        config = CrawlerRunConfig(prefetch=True)
        result = await crawler.arun(TARGET_SITEMAP, config=config)
        
        if not result.success:
            print(f"Failed to load directory mapping: {result.error_message}")
            return
            
        # Extract internal links gathered by Crawl4AI
        all_links = [link["href"] for link in result.links.get("internal", [])]
        
        valid_urls = set()
        for url in all_links:
            url_lower = url.lower()
            
            # Whitelist path targets containing workplace rules/labor laws/safety orders
            if any(pattern in url_lower for pattern in ["/title8/", "/dlse/", "/dosh/", "regulations", "leginfo", "/das/", "/cac/"]):
                # Skip media releases, contact lists, and asset styling paths
                if not any(noise in url_lower for noise in ["contactus", "mediaroom", "dirnews"]):
                    valid_urls.add(url)
                    
        # Write clean whitelisted records to your discovery file
        Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf8") as f:
            for clean_url in sorted(valid_urls):
                f.write(json.dumps({"url": clean_url, "depth": 1}) + "\n")
                
        print(f"Discovery phase complete! Saved {len(valid_urls)} whitelisted regulatory URLs.")

if __name__ == "__main__":
    asyncio.run(discover_regulatory_urls())