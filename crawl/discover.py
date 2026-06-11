import json
from crawl4ai import AsyncWebCrawler
import asyncio

OUTFILE = "../data/urls.jsonl"


async def main():
    async with AsyncWebCrawler() as crawler:

        result = await crawler.arun(
            url="https://dir.ca.gov/"
        )

        urls = set()

        for category in result.links.values():

            for link in category:

                href = link.get("href")

                if href and "dir.ca.gov" in href:
                    urls.add(href)

        with open(OUTFILE, "w") as f:

            for url in sorted(urls):

                f.write(
                    json.dumps(
                        {"url": url}
                    )
                    + "\n"
                )

        print(f"Saved {len(urls)} URLs")


asyncio.run(main())