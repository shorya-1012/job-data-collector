# Job Data Collector

Collects job postings from company career pages such as **Greenhouse** and **Lever**.

## How it works

The collection process happens in **two steps**:

1. **Fetch company names**

   * Run the company-name collection scripts first.
   * These use the **SERP API** to search for companies and identify their job-board pages.
   * The results are saved as JSON and are used as input for the job collectors.

2. **Fetch job postings**

   * Run the job collection scripts after the company JSON files have been generated.
   * The collectors use the discovered company/job-board information to fetch the actual job postings.

```text
SERP API
   │
   ▼
Company Search Scripts
   │
   ▼
Company JSON
   │
   ▼
Job Collection Scripts
   │
   ▼
Job Data API
```

## Requirements

* Python
* SERP API key

The **company-fetching step must be completed first**, since the job collectors depend on the generated company data.

## Sources

Currently supports job boards including:

* Greenhouse
* Lever

More sources can be added by implementing additional collectors.
