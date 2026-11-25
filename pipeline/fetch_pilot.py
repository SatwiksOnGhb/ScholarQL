"""Refresh the cached arXiv and OpenAlex responses for the 353-paper pilot design."""

from __future__ import annotations

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from normalize_pilot import arxiv_rows

ARXIV_URL = "https://export.arxiv.org/api/query"
OPENALEX_URL = "https://api.openalex.org/works/https://doi.org/10.48550/arXiv."
ANCHORS = """1802.01528 1805.08318 1805.12515 1807.03748 1809.03962 1810.04805
1810.12894 1810.12247 1811.05102 1811.08883 1812.04948
1901.05486 1902.02912 1902.07188 1903.03864 1904.10509 1905.07830 1906.02629
1906.08237 1907.11692 1908.10084 1910.01108 1910.10683 1912.01703 1912.11986
2001.08361 2002.06305 2002.09405 2004.11362 2005.11401 2005.14165 2006.11239 2006.07733
2007.01883 2007.11946 2009.06732 2010.02502 2010.11929 2011.10566 2012.12877
2101.00027 2101.06804 2102.09672 2102.12422 2103.14030 2104.08691 2105.05233 2105.07103
2106.09685 2106.09672 2106.10270 2106.13884 2107.03374 2108.01169 2108.07258
2110.03653 2112.05682 2112.11446
2201.11903 2202.01279 2202.06720 2202.07714 2203.02155 2203.12500 2204.02311
2204.06125 2204.14198 2205.11487 2205.11630 2207.12598 2208.07339 2209.01640
2210.03347 2210.03629 2210.11416 2211.01786 2212.08073
2302.04761 2302.05543 2302.06590 2303.08774 2303.11366 2303.11532 2303.16199
2304.02643 2304.03442 2304.07193 2304.10525 2305.10601 2305.14314 2305.17220
2305.18290 2306.01540 2306.05685 2307.03172 2307.09288 2309.06180 2310.06825
2310.11511 2310.12036 2310.17213 2310.18042 2311.05232 2312.00752 2312.11805
2401.04088 2401.13649 2402.03300 2402.17764 2403.08295 2404.07143 2404.14219
2404.17957 2405.07987 2405.16720 2406.01454 2407.10671 2407.21783 2409.12186
2410.05258 2412.19437""".split()


def fetch(url: str, path: Path, timeout: int) -> bool:
    if path.is_file():
        return True
    request = Request(url, headers={"User-Agent": "ScholarQL/1.0 (research metadata pilot)"})
    try:
        with urlopen(request, timeout=timeout) as response:
            data = response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        print(
            f"{path.name}: {type(error).__name__} ({getattr(error, 'code', 'connection')})",
            flush=True,
        )
        return False
    stage = path.with_suffix(path.suffix + ".tmp")
    stage.write_bytes(data)
    stage.replace(path)
    return True


def fetch_arxiv(cache: Path):
    jobs = []
    for start in range(0, len(ANCHORS), 24):
        group = ANCHORS[start : start + 24]
        # Preserve the original request ordering used by the frozen pilot.
        query = "id_list=" + ",".join(group) + "&max_results=" + str(len(group))
        jobs.append((cache / f"anchor-{start // 24}.xml", query))
    for year in range(2018, 2025):
        query = f"cat:cs.LG AND submittedDate:[{year}03010000 TO {year}03312359]"
        jobs.append(
            (
                cache / f"march-{year}.xml",
                urlencode({"search_query": query, "start": 0, "max_results": 40}),
            )
        )
    for target, query in jobs:
        if target.exists():
            continue
        if not fetch(f"{ARXIV_URL}?{query}", target, timeout=35):
            raise RuntimeError(
                f"ArXiv response unavailable for {target.name}. Rerun to reuse successful requests."
            )
        time.sleep(3.2)


def fetch_openalex(cache: Path, arxiv_ids: tuple[str, ...]):
    record_directory = cache / "alex"
    record_directory.mkdir(exist_ok=True)
    api_key = os.getenv("OPENALEX_API_KEY", "")
    suffix = "?" + urlencode({"api_key": api_key}) if api_key else ""

    def get(identifier: str):
        return fetch(
            OPENALEX_URL + identifier + suffix, record_directory / f"{identifier}.json", timeout=15
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        tasks = []
        for identifier in arxiv_ids:
            if not (record_directory / f"{identifier}.json").exists():
                tasks.append(pool.submit(get, identifier))
                time.sleep(0.38)
        fetched = sum(job.result() for job in tasks)
    print(
        f"OpenAlex matches fetched this run: {fetched}/{len(tasks)}. arXiv records in scope: {len(arxiv_ids)}."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("raw-research"))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    fetch_arxiv(args.cache)
    fetch_openalex(args.cache, tuple(arxiv_rows(args.cache)))


if __name__ == "__main__":
    main()
