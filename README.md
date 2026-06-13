# ccr-compliance-novulis
Assignment for Novulis Consulting.

## Setup

This pipeline leverages a local-first architecture using **Ollama** and **Llama 3.2** to handle intelligent URL filtering and graph pruning asynchronously. 

To run this pipeline locally, follow these quick setup steps:

1. **Install Ollama:** Download and install the background engine from [ollama.com](https://ollama.com).

2. **Pull the Model:** Open your terminal and download the lightweight 3B parameter model:
```bash
   ollama pull llama3.2
```
3. Verify the Server: Ensure Ollama is actively running in your system tray. The script will automatically connect to your local endpoint at http://localhost:11434/v1.
4. Install required packages

```
Bash
pip install -r requirements.txt
python -m extract
```

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

- Legal Info: California:
  - Has codes and specific legal texts on various Californian laws
- T8: Has information on:
  - Cal/OSHA
  - Division of Workers' Compensation
  - Workers' Compensation Appeals Board
  - Division of Labor Standards Enforcement and Industrial Welfare Commission
  - Self Insurance Plans
  - Division of Labor Statistics and Research
  - California Apprenticeship Council
  - Office of the Director

This reduced noise while preserving labor, safety, and workplace regulation content.

- Saw leginfo didn't work as expected, tested it using test.py. Modified discover.py acc to its results.

- Found out that T8 has deeply nested URLs. Leginfo doesn't. Got leginfo urls first, then focused on T8.

- Note: the extraction process can take time!

- Ran the jsonl file several times over with AI to check if any improvements can be made according to the schema. Obtained the final version at my 5th run through.

- Extracted, validated and chunked T8 and LegInfo pages. Of which, 1 page from T8 failed to be extracted due to server-side HTTP/2 protocol errors. A few pages have missing division id and name. These were handled too.

- Found out entirety of Leginfo was missing from the chunks, so realised this had to do with the URL structure being different for both T8 and LegInfo, decided to structure extract.py acc to this.

- Finished CLI, ingestion. Found that duplication occurred in the records. This called for proper de-duplication.

- Found that there was an easier way to simply obtain the leaf nodes as everything about the node that the chunks required was already in the 
