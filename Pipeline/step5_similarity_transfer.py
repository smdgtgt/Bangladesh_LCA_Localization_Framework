"""
Note: Fills in every material that didn't get a direct K from Step 4 using
k-nearest-neighbors on Gower distance (mixes numeric and categorical features
on one scale). Same-family neighbours are tried first; cross-family is the
fallback. Biogenic/near-zero materials get a number too but are flagged for
review.

Outputs step5_all_coefficients.csv — one row per distinct material, no blanks.
"""
import numpy as np
import pandas as pd

K_NEIGHBORS   = 5        # how many neighbours to consult
CROSS_PENALTY = 0.70     # similarity penalty applied to cross-family transfers
BIO_GWP_EPS   = 0.05     # |gwp_per_kg| at/below this is treated as near-zero

LEVEL_RANK = {"strongest": 3, "medium": 2, "low": 1, "none": 0}

# ----------------------------------------------------------------- load inputs
clean   = pd.read_csv("all_materials_clean.csv")
feats   = pd.read_csv("oclca_features.csv")
match   = pd.read_csv("matching_results.csv")
anchors = pd.read_csv("anchor_coefficients.csv")
fam_anc = pd.read_csv("family_anchors.csv")

# oclca_features is row-aligned 1:1 with all_materials_clean -> reattach the key
assert (clean["clean_name"].reset_index(drop=True)
        == feats["name"].reset_index(drop=True)).all(), "feature/clean misalignment"
feats = feats.copy()
feats["resource_id"] = clean["resource_id"].values

# one feature record per distinct material (intrinsic props; keep first)
FEAT_COLS = ["density_kg_m3", "product_form", "voided",
             "process_keywords", "ingredient_keywords",
             "strength_class", "recycled_pct"]
mat = (feats.drop_duplicates("resource_id")
            .set_index("resource_id")[FEAT_COLS])

# best match row per material -> gives family, display name, gwp, level
match = match.copy()
match["lvl_rank"] = match["level"].map(LEVEL_RANK).fillna(0)
best = (match.sort_values(["lvl_rank", "matches"], ascending=False)
             .drop_duplicates("resource_id")
             .set_index("resource_id"))
universe = best.index.unique()   # 1,173 distinct materials

# biogenic families (from Step 4 family table)
BIO_FAMILIES = set(fam_anc.loc[fam_anc["anchor_source"] == "biogenic_or_nearzero",
                               "family"])

# ----------------------------------------------------------------- labeled set
# trusted K = validated ratio coefficients; keep best K per material
ratio = anchors[anchors["coefficient_status"] == "ratio"].copy()
ratio["lvl_rank"] = ratio["level"].map(LEVEL_RANK).fillna(0)
labeled = (ratio.sort_values(["lvl_rank", "matches"], ascending=False)
                .drop_duplicates("resource_id")
                .set_index("resource_id"))
labeled_ids = list(labeled.index)
print(f"Materials in universe : {len(universe)}")
print(f"Labeled (trusted K)   : {len(labeled_ids)}")
print(f"Need transfer         : {len(universe) - len(labeled_ids)}")

# ----------------------------------------------------------- Gower distance kit
def kw_set(v):
    if pd.isna(v):
        return None
    return frozenset(t.strip() for t in str(v).split("|") if t.strip())

# precompute feature views for speed
DENS = mat["density_kg_m3"].to_dict()
RECY = mat["recycled_pct"].to_dict()
FORM = mat["product_form"].to_dict()
VOID = mat["voided"].astype("object").to_dict()
STRC = mat["strength_class"].to_dict()
PROC = {i: kw_set(v) for i, v in mat["process_keywords"].items()}
INGR = {i: kw_set(v) for i, v in mat["ingredient_keywords"].items()}

# numeric ranges for normalization
def rng(d):
    vals = [v for v in d.values() if pd.notna(v)]
    return (min(vals), max(vals)) if vals else (0.0, 1.0)
DEN_MIN, DEN_MAX = rng(DENS); DEN_R = (DEN_MAX - DEN_MIN) or 1.0
REC_MIN, REC_MAX = rng(RECY); REC_R = (REC_MAX - REC_MIN) or 1.0

def jacc(a, b):
    if a is None or b is None or (not a and not b):
        return None
    u = a | b
    return 1.0 - (len(a & b) / len(u)) if u else None

def cat(a, b):
    if pd.isna(a) or pd.isna(b):
        return None
    return 0.0 if a == b else 1.0

def num(a, b, r):
    if pd.isna(a) or pd.isna(b):
        return None
    return abs(a - b) / r

def gower(i, j):
    """Mean per-feature distance over the features both materials share."""
    ds = []
    for d in (num(DENS[i], DENS[j], DEN_R),
              num(RECY[i], RECY[j], REC_R),
              cat(FORM[i], FORM[j]),
              cat(VOID[i], VOID[j]),
              cat(STRC[i], STRC[j]),
              jacc(PROC[i], PROC[j]),
              jacc(INGR[i], INGR[j])):
        if d is not None:
            ds.append(d)
    return float(np.mean(ds)) if ds else 1.0

# group labeled ids by family for the same-family tier
lab_by_family = {}
for rid in labeled_ids:
    fam = best.loc[rid, "family"]
    lab_by_family.setdefault(fam, []).append(rid)

def knn_estimate(rid, candidate_ids):
    """Distance-weighted K from the k nearest candidates. Returns dict or None."""
    if not candidate_ids:
        return None
    dists = [(c, gower(rid, c)) for c in candidate_ids if c != rid]
    if not dists:
        return None
    dists.sort(key=lambda x: x[1])
    chosen = dists[:K_NEIGHBORS]
    ids   = [c for c, _ in chosen]
    dd    = np.array([d for _, d in chosen])
    ks    = np.array([labeled.loc[c, "K"] for c in ids], dtype=float)
    w     = 1.0 / (dd + 1e-6)
    Kest  = float(np.sum(w * ks) / np.sum(w))
    sim   = float(1.0 - dd.mean())
    names = [best.loc[c, "oclca_name"] for c in ids[:3]]
    return {"K": Kest, "similarity": sim, "n": len(ids),
            "neighbors": "; ".join(names)}

# --------------------------------------------------------------- build results
rows = []
for rid in universe:
    fam   = best.loc[rid, "family"]
    name  = best.loc[rid, "oclca_name"]
    gwp   = best.loc[rid, "oclca_gwp_per_kg"]
    is_bio = (fam in BIO_FAMILIES) or (pd.notna(gwp) and abs(gwp) <= BIO_GWP_EPS)

    if rid in labeled.index:                      # already has a trusted K
        K   = float(labeled.loc[rid, "K"])
        lvl = labeled.loc[rid, "level"]
        conf  = "High" if lvl == "strongest" else "Medium"
        logic = f"validated_{lvl}"
        sim, nn, neigh = 1.0, 1, best.loc[rid, "ifc_anchor"]
    else:
        same = [c for c in lab_by_family.get(fam, []) if c != rid]
        est = knn_estimate(rid, same)
        if est:                                   # same-family transfer
            logic, conf = "same_family_knn", "Low"
        else:                                     # cross-family fallback
            est = knn_estimate(rid, labeled_ids)
            logic, conf = "cross_family_knn", "Review"
            if est:
                est["similarity"] *= CROSS_PENALTY
        if est is None:                           # no labeled material at all
            est = {"K": np.nan, "similarity": 0.0, "n": 0, "neighbors": ""}
            conf, logic = "Review", "no_neighbor"
        K, sim, nn, neigh = est["K"], est["similarity"], est["n"], est["neighbors"]
        if is_bio:
            conf  = "Review (biogenic)"
            logic = logic + "_biogenic"

    # delta / % adjustment expressed against the One Click value (localized = K*gwp)
    if pd.notna(K) and pd.notna(gwp):
        delta = K * gwp - gwp
        pct   = (K - 1.0) * 100.0
    else:
        delta = pct = np.nan

    rows.append({
        "resource_id": rid, "oclca_name": name, "family": fam,
        "oclca_gwp_per_kg": gwp,
        "density_kg_m3": DENS[rid], "product_form": FORM[rid],
        "process_keywords": mat.loc[rid, "process_keywords"],
        "ingredient_keywords": mat.loc[rid, "ingredient_keywords"],
        "K": K, "delta": delta, "pct_adjustment": pct,
        "confidence": conf, "transfer_logic": logic,
        "similarity_score": round(sim, 3), "n_neighbors": nn,
        "neighbor_examples": neigh,
    })

out = pd.DataFrame(rows)
out.to_csv("step5_all_coefficients.csv", index=False)

# --------------------------------------------------------------------- summary
print("\n" + "=" * 64)
print("STEP 5 RESULT")
print("=" * 64)
print(f"Total materials with a K : {out['K'].notna().sum()} / {len(out)}")
print(f"Blank K (no neighbour)   : {out['K'].isna().sum()}")
print("\nConfidence breakdown:")
print(out["confidence"].value_counts().to_string())
print("\nTransfer logic breakdown:")
print(out["transfer_logic"].value_counts().to_string())

print("\nBRICK PILOT CHECK (should stay K ~= 1.648):")
brick = out[out["family"] == "Brick"][
    ["oclca_name", "K", "confidence", "transfer_logic"]]
print(brick.head(8).to_string(index=False))

print("\nSample transferred estimates (Low / Review):")
samp = out[out["confidence"].isin(["Low", "Review", "Review (biogenic)"])][
    ["oclca_name", "family", "K", "confidence", "similarity_score",
     "neighbor_examples"]]
print(samp.head(10).to_string(index=False))

print(f"\nK range across all materials: {out['K'].min():.3f} to {out['K'].max():.3f}"
      f"  (median {out['K'].median():.3f})")
print("\nSaved -> step5_all_coefficients.csv")
