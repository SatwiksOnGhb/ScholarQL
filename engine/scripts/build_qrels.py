"""Freeze a small set of manually assigned arXiv-ID relevance judgments."""

import json

from scholarql.config import DATA
from scholarql.db import read_pilot

# 2: direct contribution; 1: closely related method or application.
JUDGMENTS = [
    (
        "Find papers about adapting language models on a small GPU published since 2023",
        {"2305.14314": 2, "2303.16199": 2, "2402.17764": 1, "2404.14219": 1},
    ),
    (
        "Find papers about adjusting a frozen language model using a few trainable parameters before 2023",
        {"2106.09685": 2, "2106.13884": 1},
    ),
    (
        "Find papers about training language models using human preferences in 2023",
        {"2305.18290": 2, "2310.12036": 2, "2307.09288": 1},
    ),
    (
        "Find papers about conditioning diffusion image generation on guidance in 2022",
        {"2207.12598": 2, "2205.11487": 1},
    ),
    (
        "Find papers about improving the quality or efficiency of denoising diffusion before 2022",
        {"2102.09672": 2, "2010.02502": 2, "2105.05233": 2, "2006.11239": 1},
    ),
    (
        "Find papers about attention with lower memory for long input sequences since 2023",
        {"2404.07143": 2, "2309.06180": 2, "2312.00752": 1, "2410.05258": 1},
    ),
    (
        "Find papers about long sequences with less memory before 2022",
        {"1904.10509": 2, "2112.05682": 2, "2009.06732": 2},
    ),
    (
        "Find papers about prompting language models to reason step by step in 2022",
        {"2201.11903": 2, "2210.03629": 1},
    ),
    (
        "Find papers about language model agents reasoning and acting in web tasks since 2023",
        {"2401.13649": 2, "2303.11366": 2, "2305.10601": 1},
    ),
    (
        "Find papers about sparse mixture-of-experts language models in 2024",
        {"2401.04088": 2, "2412.19437": 2, "2407.10671": 1},
    ),
    (
        'Find papers about large language models trained to follow user instructions tagged "cs.LG" before 2023',
        {"2203.02155": 2, "2210.11416": 2, "2211.01786": 1},
    ),
    (
        "Find papers about contrastive or paired-view self-supervision between 2018 and 2020",
        {"1807.03748": 2, "2006.07733": 2, "2004.11362": 1, "2011.10566": 1},
    ),
    (
        "Find papers about vision transformers for image classification in 2021",
        {"2103.14030": 2, "2106.10270": 2},
    ),
    (
        "Find papers about few-shot multimodal vision and language published between 2021 and 2022",
        {"2204.14198": 2, "2106.13884": 2},
    ),
    (
        "Find papers about quantization for language models in 2024",
        {"2402.17764": 2, "2404.14219": 1, "2412.19437": 1},
    ),
    (
        'Find papers about generating grounded answers using retrieved documents tagged "cs.CL" since 2023',
        {"2310.11511": 2},
    ),
    (
        "Find papers about retrieving documents to support generation",
        {"2005.11401": 2, "2310.11511": 2},
    ),
    (
        "Find papers about estimating how language model quality changes with more parameters and compute",
        {"2001.08361": 2, "2112.11446": 1, "2407.21783": 1},
    ),
    (
        "Find papers about image generation with iterative denoising",
        {
            "2006.11239": 2,
            "2102.09672": 2,
            "2010.02502": 2,
            "2105.05233": 2,
            "2205.11487": 1,
            "2302.05543": 1,
        },
    ),
    (
        "Find papers about training a language model to write computer programs",
        {"2107.03374": 2, "2412.19437": 1, "2407.10671": 1},
    ),
    (
        "Find papers about prompting a large language model to split reasoning into multiple steps",
        {"2201.11903": 2, "2305.10601": 2, "2402.03300": 1, "2210.03629": 1},
    ),
    ("Find papers about label smoothing and confidence calibration", {"1906.02629": 2}),
    (
        "Find papers about a style-controlled architecture for generating images",
        {"1812.04948": 2, "1805.08318": 1, "2302.05543": 1},
    ),
    ("Find papers about reinforcement learning exploration driven by novelty", {"1810.12894": 2}),
]


def main():
    snapshot = read_pilot()
    lookup = {paper[4]: paper[0] for paper in snapshot["entities"]["paper"]}
    rows = [
        {
            "id": f"R{i:02}",
            "group": "hybrid" if i <= 16 else "semantic",
            "question": question,
            "judgments": {lookup[arxiv]: grade for arxiv, grade in grades.items()},
            "arxiv_judgments": grades,
        }
        for i, (question, grades) in enumerate(JUDGMENTS, 1)
    ]
    (DATA / "retrieval_qrels.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
