"""Shared placeholder catalog for the walking skeleton.

Real paper titles and authors, but FAKE ids (1xxx papers, 2xxx venues, 3xxx institutions,
4xxx topics, 5xxx authors), citation counts and TLDRs. Every placeholder router reads from
here, so a search hit links to a paper page that exists. Delete this file once all
routers use the real databases.
"""

VENUES = {
    2001: {"venue_id": 2001, "name": "NAACL", "type": "conference"},
    2002: {"venue_id": 2002, "name": "NeurIPS", "type": "conference"},
    2003: {"venue_id": 2003, "name": "ICLR", "type": "conference"},
}

INSTITUTIONS = {
    3001: {"institution_id": 3001, "name": "Google", "country": "US"},
    3002: {"institution_id": 3002, "name": "OpenAI", "country": "US"},
    3003: {"institution_id": 3003, "name": "UC Berkeley", "country": "US"},
    3004: {"institution_id": 3004, "name": "Microsoft", "country": "US"},
}

TOPICS = {
    4001: {"topic_id": 4001, "name": "Natural language processing"},
    4002: {"topic_id": 4002, "name": "Computer vision"},
    4003: {"topic_id": 4003, "name": "Generative models"},
    4004: {"topic_id": 4004, "name": "Reinforcement learning"},
}

AUTHORS = {
    5001: {"author_id": 5001, "name": "Jacob Devlin", "institution_id": 3001},
    5002: {"author_id": 5002, "name": "Ming-Wei Chang", "institution_id": 3001},
    5003: {"author_id": 5003, "name": "Tom B. Brown", "institution_id": 3002},
    5004: {"author_id": 5004, "name": "Jonathan Ho", "institution_id": 3003},
    5005: {"author_id": 5005, "name": "Pieter Abbeel", "institution_id": 3003},
    5006: {"author_id": 5006, "name": "Alexey Dosovitskiy", "institution_id": 3001},
    5007: {"author_id": 5007, "name": "Lili Chen", "institution_id": 3003},
    5008: {"author_id": 5008, "name": "Edward J. Hu", "institution_id": 3004},
}

PAPERS = {
    1001: {
        "paper_id": 1001,
        "title": "BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding",
        "year": 2019,
        "venue_id": 2001,
        "author_ids": [5001, 5002],
        "topic_ids": [4001],
        "citation_count": 412,
        "tldr": "A bidirectional Transformer pre-trained on masked words, then fine-tuned.",
    },
    1002: {
        "paper_id": 1002,
        "title": "Language Models are Few-Shot Learners",
        "year": 2020,
        "venue_id": 2002,
        "author_ids": [5003],
        "topic_ids": [4001, 4003],
        "citation_count": 388,
        "tldr": "A very large language model solves new tasks from a few examples in the prompt.",
    },
    1003: {
        "paper_id": 1003,
        "title": "Denoising Diffusion Probabilistic Models",
        "year": 2020,
        "venue_id": 2002,
        "author_ids": [5004, 5005],
        "topic_ids": [4003, 4002],
        "citation_count": 301,
        "tldr": "Generates images by learning to reverse a gradual noising process.",
    },
    1004: {
        "paper_id": 1004,
        "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
        "year": 2021,
        "venue_id": 2003,
        "author_ids": [5006],
        "topic_ids": [4002],
        "citation_count": 276,
        "tldr": "A plain Transformer on image patches matches CNNs when pre-trained at scale.",
    },
    1005: {
        "paper_id": 1005,
        "title": "Decision Transformer: Reinforcement Learning via Sequence Modeling",
        "year": 2021,
        "venue_id": 2002,
        "author_ids": [5007, 5005],
        "topic_ids": [4004],
        "citation_count": 97,
        "tldr": "Treats reinforcement learning as predicting actions in a sequence of returns.",
    },
    1006: {
        "paper_id": 1006,
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "year": 2022,
        "venue_id": 2003,
        "author_ids": [5008],
        "topic_ids": [4001],
        "citation_count": 154,
        "tldr": "Fine-tunes large models by training small low-rank matrices beside frozen "
        "weights.",
    },
}

# (citing_id, cited_id)
CITATIONS = [
    (1002, 1001),
    (1004, 1001),
    (1005, 1001),
    (1005, 1002),
    (1006, 1001),
    (1006, 1002),
]
