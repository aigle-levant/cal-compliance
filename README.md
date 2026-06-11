# ccr-compliance-novulis
Assignment for Novulis Consulting.

- Tried parsing, faced a real block

```md
## Performing security verification
This website uses a security service to protect against malicious bots. This page is displayed while the website verifies you are not a bot.
## Verification successful. Waiting for govt.westlaw.com to respond
Ray ID: `a0980e763cd7426e`
Performance and Security by [Cloudflare](https://www.cloudflare.com?utm_source=challenge&utm_campaign=m)[Privacy](https://www.cloudflare.com/privacypolicy/)
```

- Inquired about this, was asked to use https://dir.ca.gov/ instead. Which works with normal crawler.

- Used normal crawler. Works fine with new URL. Tried discovery, extraction, coverage logging. Found out that unnecessary junk content kept appearing.

- Used deep crawler. Some pages were unavailable or showed 403 forbidden even for a normal user. Skipped them.

- Noticed the site has a sitemap. Utilized it. Also discovered the robots.txt explicitly won't be allowing XML stuff, so went with the HTML one there. The DIR sitemap contains administrative pages, social links, and non-regulatory resources.

To improve retrieval quality, discovery was restricted to compliance-relevant divisions:

- DOSH
- DLSE
- DAS
- CAC
- DWC
- Legal Info: California

This reduced noise while preserving labor, safety, and workplace regulation content.
