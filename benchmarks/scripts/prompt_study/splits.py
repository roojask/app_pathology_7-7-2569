"""
splits.py  --  test set A (the thesis 300 cases) + a disjoint dev set.

select_stratified_cases() is copied verbatim from
benchmarks/scripts/run_controlled_ablation_300cases.py so that TEST == the
same 300 cases (seed 42, 30 per category) used in the thesis tables.

DEV = cases NOT in TEST, 20 per category (seed 7). Use DEV only to choose or
tune prompts. Report final numbers on TEST only.

NOTE: DEV and TEST come from the same generator/templates. This split guards
against tuning on the reported cases; it does NOT remove template overlap.
That needs a free-form test set (Test B).
"""
import random


def select_stratified_cases(gt_data, cases_per_cat=30, core_per_cat=10, seed=42):
    random.seed(seed)
    cats = {}
    for cid, d in gt_data.items():
        c_id = d.get("cat_idx") or d.get("category_id", 1)
        cats.setdefault(c_id, []).append(cid)

    selected = []
    for c_id in sorted(cats.keys()):
        c_list = sorted(cats[c_id])
        sampled = random.sample(c_list, min(cases_per_cat, len(c_list)))
        for rank, cid in enumerate(sampled):
            selected.append((cid, c_id, rank < core_per_cat))

    random.seed(seed + 100)
    random.shuffle(selected)
    return selected


def cat_of(d):
    return d.get("cat_idx") or d.get("category_id", 1)


def get_split(gt_data, split):
    """Return list of (case_id, category). split in {'test', 'dev'}."""
    test = select_stratified_cases(gt_data, cases_per_cat=30, core_per_cat=10, seed=42)
    test_ids = {cid for cid, _, _ in test}
    if split == "test":
        return [(cid, c) for cid, c, _ in test]
    if split == "dev":
        rng = random.Random(7)
        by_cat = {}
        for cid, d in gt_data.items():
            if cid not in test_ids:
                by_cat.setdefault(cat_of(d), []).append(cid)
        dev = []
        for c in sorted(by_cat):
            pool = sorted(by_cat[c])
            dev += [(cid, c) for cid in rng.sample(pool, min(20, len(pool)))]
        rng.shuffle(dev)
        assert not ({cid for cid, _ in dev} & test_ids), "dev/test overlap"
        return dev
    raise ValueError(split)


if __name__ == "__main__":
    import json, sys
    from pathlib import Path
    base = Path(__file__).resolve().parent.parent
    gt = json.load(open(base / "data" / "dataset_1000" / "ground_truth_1000_pure.json", encoding="utf-8"))
    for s in ("test", "dev"):
        print(s, len(get_split(gt, s)))
