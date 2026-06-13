# CCR Compliance Agent – Novulis Consulting Assignment

## Overview

This project builds an end-to-end compliance agent. The system:

1. Discovers CCR regulation URLs
2. Extracts regulation content as structured Markdown
3. Reconstructs the canonical CCR hierarchy
4. Validates crawl coverage and extraction completeness
5. Chunks and prepares documents for vector indexing
6. Supports retrieval-augmented compliance guidance with citations

The implementation prioritizes completeness, observability, and reproducibility over raw crawl speed.

# Setup

## Prerequisites

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run discovery:

```bash
cd crawl
python -m discover
```

Run extraction [it contains extraction, validation, and chunking, all rolled in one]:

```bash
cd crawl
python -m extract
```

Now you can execute the ingestion script to add the data to Supabase and then setup your agent

```bash
cd agent
python -m ingest
```

Environment variables should be configured through a `.env` file.

# Design Decisions

## Initial Source: Westlaw CCR

The assignment specified:

https://govt.westlaw.com/calregs

Initial crawling attempts were performed against this source.

### Challenge

Westlaw is protected by Cloudflare Turnstile's bot verification.

Example response:

```text
![Icon for govt.westlaw.com](https://govt.westlaw.com/favicon.ico)
# govt.westlaw.com
## Performing security verification
This website uses a security service to protect against malicious bots. This page is displayed while the website verifies you are not a bot.
## Verification successful. Waiting for govt.westlaw.com to respond
Ray ID: `a098159faaa1179b`
Performance and Security by [Cloudflare](https://www.cloudflare.com?utm_source=challenge&utm_campaign=m)[Privacy](https://www.cloudflare.com/privacypolicy/)
```

This prevented reliable automated extraction despite multiple crawling approaches [including stealth mode, undetected browser, etc.].

### Decision

Rather than attempting to bypass anti-bot protections, I requested clarification and was advised to use [California Department of Industrial Relations (DIR) resources](https://dir.ca.gov/) instead.

### Trade-off

Pros:

* Stable crawling
* Publicly accessible content
* Reduced operational complexity

Cons:

* Required reconstructing hierarchy from multiple sources rather than relying on a single canonical portal

# URL Discovery Strategy

The crawler separates:

1. URL discovery
2. Section extraction

This allows discovery results to be persisted and reused without re-crawling the source.

## Sources Used

### Title 8 (DIR)

Contains labor and workplace regulations including:

* Cal/OSHA
* Division of Workers' Compensation
* Workers' Compensation Appeals Board
* Division of Labor Standards Enforcement
* Industrial Welfare Commission
* Division of Labor Statistics and Research
* California Apprenticeship Council

### California Legislative Information (LegInfo)

Contains statutory code references and supporting legal materials.

# Discovery Challenges

## Sitemap Noise

The DIR sitemap contains:

* Administrative pages
* News content
* Social links
* Non-regulatory resources

Indexing everything would significantly reduce retrieval quality.

### Decision

Discovery was restricted to compliance-relevant regulatory sections only.

### Result

Improved signal-to-noise ratio while preserving relevant labor and workplace regulations.

## Different URL Structures

The two primary sources use different hierarchy models.

### Title 8

Uses deeply nested hierarchy structures encoded in URL patterns and navigation paths.

### LegInfo

Uses parameterized URLs with hierarchy encoded through query parameters.

### Decision

Separate hierarchy extraction logic was implemented for each source.

This improved extraction accuracy and reduced false hierarchy assignments.

---

# Content Extraction

Each regulation section is transformed into a structured record containing:

* Title
* Division
* Chapter
* Subchapter
* Article
* Section number
* Section heading
* Citation
* Breadcrumb path
* Source URL
* Retrieved timestamp
* Markdown content

The extraction pipeline includes:

* Markdown cleanup
* Navigation removal
* Boilerplate removal
* Hierarchy reconstruction
* Validation checks

---

# Coverage Validation

A dedicated validation layer was implemented because coverage is the primary evaluation criterion.

Validation records include:

* Missing hierarchy fields
* Missing citations
* Missing section numbers
* Extraction failures
* Hierarchy consistency issues

Coverage reports are generated separately from extracted records.

This allows extraction quality to be measured independently of retrieval quality.

---

# Chunking Strategy

Extracted regulations are converted into overlapping chunks for vector search.

Each chunk preserves:

* Citation
* Hierarchy metadata
* Source URL
* Breadcrumb path

This allows retrieved chunks to remain traceable to their original regulation sections.

---

# Issues Encountered

## Missing Hierarchy Information

Some Title 8 regulations contain chapter and subchapter information but do not expose division information.

### Decision

Records were preserved rather than discarded.

Missing fields are explicitly reported in validation output.

### Reasoning

Retaining incomplete records provides better regulatory coverage than silently dropping valid sections.

---

## Extraction Failures

One Title 8 page failed extraction due to server-side HTTP/2 protocol issues.

### Decision

Failure was logged and included in coverage reporting.

### Result

The crawler remains transparent about known gaps.

---

## LegInfo Chunking Bug

An early version of the extraction pipeline produced chunks for Title 8 but omitted LegInfo records.

### Root Cause

Title 8 and LegInfo use different URL and hierarchy structures.

### Resolution

Source-specific extraction logic was introduced.

Subsequent validation confirmed both sources were included in chunk generation.

---

# Current Coverage

Current extraction results:

* 3,225 total documents processed
* Structured regulation records generated
* Validation reports generated
* Chunked retrieval corpus generated

Known limitations and unresolved hierarchy gaps are explicitly reported rather than hidden.

---

# Future Improvements

Given additional time, I would:

1. Add persistent crawl checkpoints for long-running jobs
2. Expand hierarchy resolution beyond Title 8
3. Add automated regression tests for extraction quality
4. Improve metadata enrichment for partially structured pages

# Known Limitations

* A small number of pages could not be retrieved due to server-side issues.
* Some regulations do not expose complete hierarchy information.
* Coverage is high but not guaranteed to be 100%.
* Regulatory interpretation should not be considered legal advice.

The system prioritizes transparency and reporting of limitations rather than assuming completeness.
