import asyncio
import logging
import os

import httpx

ENDPOINT = os.environ.get("FIRECRAWL_ENDPOINT")


async def _crawl(url: str, client: httpx.AsyncClient) -> str:
    r = await client.post(
        "/v2/scrape",
        json={"url": url, "formats": ["markdown"], "onlyMainContent": True},
    )
    if r.status_code != 200:
        await r.aread()
        return r.text
    resp = r.json()["data"]
    return f"# {resp['metadata']['title']}\n\n{resp['markdown']}"


async def crawl(urls: list[str]) -> str:
    if not ENDPOINT:
        logging.error("FIRECRAWL_ENDPOINT is not set")
        return ""
    try:
        async with httpx.AsyncClient(
            base_url=ENDPOINT, http2=True, timeout=60 * 5
        ) as client:
            result = await asyncio.gather(*[_crawl(url, client) for url in urls])
    except Exception as e:
        logging.error(e)
        return repr(e)
    lines = ["", "URLs in this message are crawled as follows:"]
    lines.extend([x for pair in zip(urls, result) for x in pair])
    return "\n\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(asyncio.run(crawl(["https://github.com", "https://example.com"])))
