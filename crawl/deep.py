import asyncio
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig

async def two_phase_crawl(start_url: str):
    async with AsyncWebCrawler() as crawler:
        # ═══════════════════════════════════════════════
        # Phase 1: Fast discovery (prefetch mode)
        # ═══════════════════════════════════════════════
        prefetch_config = CrawlerRunConfig(prefetch=True)
        discovery = await crawler.arun(start_url, config=prefetch_config)

        all_urls = [link["href"] for link in discovery.links.get("internal", [])]
        print(f"Discovered {len(all_urls)} URLs")

        # Filter to URLs you care about
        blog_urls = [url for url in all_urls if "/blog/" in url]
        print(f"Found {len(blog_urls)} blog posts to process")

        # ═══════════════════════════════════════════════
        # Phase 2: Full processing on selected URLs only
        # ═══════════════════════════════════════════════
        full_config = CrawlerRunConfig(
            # Your normal extraction settings
            word_count_threshold=100,
            remove_overlay_elements=True,
        )

        results = []
        for url in blog_urls:
            result = await crawler.arun(url, config=full_config)
            if result.success:
                results.append(result)
                print(f"Processed: {url}")

        return results

if __name__ == "__main__":
    results = asyncio.run(two_phase_crawl("https://dir.ca.gov/sitemap/sitemap.html"))
    print(f"Fully processed {len(results)} pages")