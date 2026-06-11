import asyncio
from crawl4ai import AsyncWebCrawler

async def main():

    async with AsyncWebCrawler() as crawler:

        result = await crawler.arun(
            "https://leginfo.legislature.ca.gov/faces/codedisplayexpand.xhtml?tocCode=LAB"
        )

        print(result.success)

        if not result.success:
            print(result.error_message)
            return

        print(len(result.links["internal"]))

if __name__ == "__main__":
    asyncio.run(main())