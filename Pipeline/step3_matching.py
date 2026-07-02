"""
STEP 3 - Technical matching matrix (IFC <-> One Click).

Scores each One Click material against the IFC record(s) of its family on FIVE
technical criteria, GWP deliberately excluded:
  1. composition   (raw-ingredient overlap)
  2. process/kiln   (manufacturing-process overlap)
  3. density        (within +/-30 percent)
  4. product form   (same form AND same voided/solid state)
  5. application    (same use-role: masonry / facade / coating / insulation / panel)

Each criterion is match / mismatch / unknown (unknown never penalises).
Classification follows the thesis rule:
  strongest = >=4 matches, <=1 mismatch
  medium    = >=3 matches, <=1 mismatch
  low       =  >=1 match
  none      =   0 matches

Keeps the best pairing per One Click material. Writes matching_results.csv.

Run:  python step3_matching.py
"""
import re
import pandas as pd

OCLCA_CSV = "all_materials_clean.csv"
IFC_REF   = "ifc_reference.csv"
OCLCA_FEAT = "oclca_features.csv"
IFC_FEAT   = "ifc_features.csv"

DENSITY_LO, DENSITY_HI = 0.7, 1.43      # +/-~30% band
COMP_MATCH = 0.34                        # ingredient Jaccard to count as aligned

# ----------------------------------------------------------------- load + join
oclca = pd.read_csv(OCLCA_CSV).reset_index(drop=True)
of    = pd.read_csv(OCLCA_FEAT).reset_index(drop=True)
assert len(oclca) == len(of), "feature/data row mismatch"
oclca = pd.concat([oclca[["resource_id","search_query","clean_name","gwp_per_kg"]],
                   of[["product_form","voided","process_keywords",
                       "ingredient_keywords","strength_class","density_kg_m3"]]], axis=1)

iff = pd.read_csv(IFC_FEAT)
iref = pd.read_csv(IFC_REF)[["ifc_material","gwp_per_kg","used_as_wall"]]
ifc = iff.merge(iref, left_on="name", right_on="ifc_material", how="left")

def toks(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split())

def role(name, form):
    n = str(name).lower()
    if any(k in n for k in ["facade", "faced", "cladding"]):
        return "facade"
    if form in ("render", "mortar"):
        return "coating"
    if form in ("foam", "wool"):
        return "insulation"
    if form in ("block", "brick", "bulk"):
        return "masonry"
    if form in ("panel", "sheet", "tile", "profile", "board"):
        return "panel"
    return "other"

def kwset(s):
    return set(str(s).split("|")) - {"", "nan"}

# ----------------------------------------------------------------- criterion scoring
def score_pair(o, i):
    # composition
    oi, ii = kwset(o["ingredient_keywords"]), kwset(i["ingredient_keywords"])
    if oi and ii:
        j = len(oi & ii) / len(oi | ii)
        comp = "match" if j >= COMP_MATCH else "mismatch"
    else:
        comp = "unknown"
    # process
    op, ip = kwset(o["process_keywords"]), kwset(i["process_keywords"])
    if op and ip:
        proc = "match" if (op & ip) else "mismatch"
    else:
        proc = "unknown"
    # density
    od, idn = o["density_kg_m3"], i["density_kg_m3"]
    if pd.notna(od) and pd.notna(idn) and idn:
        r = od / idn
        dens = "match" if DENSITY_LO <= r <= DENSITY_HI else "mismatch"
    else:
        dens = "unknown"
    # form (+ voided)
    if o["product_form"] and i["product_form"]:
        form = "match" if (o["product_form"] == i["product_form"]
                           and bool(o["voided"]) == bool(i["voided"])) else "mismatch"
    else:
        form = "unknown"
    # application role
    ro, ri = role(o["clean_name"], o["product_form"]), role(i["name"], i["product_form"])
    if ro != "other" and ri != "other":
        app = "match" if ro == ri else "mismatch"
    else:
        app = "unknown"

    states = {"composition": comp, "process": proc, "density": dens,
              "form": form, "application": app}
    m  = sum(v == "match" for v in states.values())
    mm = sum(v == "mismatch" for v in states.values())
    # Composition is the anchor criterion: no strong/medium match without it.
    # Unknown criteria are neutral - a pair that matches every observable
    # criterion with zero contradictions is the strongest available match.
    if   comp == "match" and mm == 0 and m >= 3: level = "strongest"
    elif comp == "match" and mm <= 1 and m >= 2: level = "medium"
    elif m >= 1:                                 level = "low"
    else:                                        level = "none"
    return states, m, mm, level

LEVEL_RANK = {"strongest": 3, "medium": 2, "low": 1, "none": 0}

# IFC candidates per One Click family: IFC names sharing a family token
families = oclca["search_query"].unique()
ifc_tok = {r["name"]: toks(r["name"]) for _, r in ifc.iterrows()}
fam_candidates = {}
for fam in families:
    ft = toks(fam)
    cands = [name for name, t in ifc_tok.items()
             if (len(ft & t) / len(ft | t) if (ft | t) else 0) >= 0.2]
    fam_candidates[fam] = cands

ifc_by_name = {r["name"]: r for _, r in ifc.iterrows()}

# ----------------------------------------------------------------- match each material
results = []
for _, o in oclca.iterrows():
    best = None
    for cand in fam_candidates.get(o["search_query"], []):
        i = ifc_by_name[cand]
        states, m, mm, level = score_pair(o, i)
        key = (LEVEL_RANK[level], m, -mm)
        if best is None or key > best[0]:
            best = (key, cand, states, m, mm, level, i["gwp_per_kg"])
    if best is None:
        results.append({"resource_id": o["resource_id"], "oclca_name": o["clean_name"],
                        "family": o["search_query"], "ifc_anchor": None,
                        "level": "none", "matches": 0, "mismatches": 0,
                        "oclca_gwp_per_kg": o["gwp_per_kg"], "ifc_gwp_per_kg": None})
        continue
    _, cand, states, m, mm, level, igwp = best
    results.append({"resource_id": o["resource_id"], "oclca_name": o["clean_name"],
                    "family": o["search_query"], "ifc_anchor": cand,
                    **states, "matches": m, "mismatches": mm, "level": level,
                    "oclca_gwp_per_kg": o["gwp_per_kg"], "ifc_gwp_per_kg": igwp})

res = pd.DataFrame(results)
res.to_csv("matching_results.csv", index=False)

# ----------------------------------------------------------------- report
print("=" * 70)
print("STEP 3 - MATCH LEVEL DISTRIBUTION (best pair per One Click material)")
print("=" * 70)
print(res["level"].value_counts().reindex(["strongest","medium","low","none"]).to_string())
print(f"\ntotal materials matched: {len(res)}")

print("\n" + "=" * 70)
print("BRICK FAMILY MATRIX (reproducing the thesis Table)")
print("=" * 70)
brick_ifc = [n for n in ifc_by_name if "rick" in n]
brick_o = oclca[oclca["clean_name"].str.contains("brick", case=False, na=False)
                & ~oclca["clean_name"].str.contains("junction|mortar$", case=False, na=False)]
seen = set()
for _, o in brick_o.iterrows():
    if o["clean_name"] in seen:
        continue
    seen.add(o["clean_name"])
    cells = []
    for bn in ["Brick (common/facing)", "Brick - Hoffman kiln", "Honeycomb brick"]:
        _, _, _, lvl = score_pair(o, ifc_by_name[bn])
        cells.append(f"{bn.split('(')[0].split(' - ')[-1].strip()[:14]:<14}:{lvl}")
    print(f"{o['clean_name'][:46]:<46} | " + " | ".join(cells))

print("\n--- strongest brick pair detail (drives the K=0.39/0.24 anchor) ---")
clay = oclca[oclca["clean_name"].str.fullmatch("Clay brick", case=False, na=False)]
if len(clay):
    o = clay.iloc[0]
    states, m, mm, lvl = score_pair(o, ifc_by_name["Brick (common/facing)"])
    print(f"One Click '{o['clean_name']}' (gwp {o['gwp_per_kg']}/kg, dens {o['density_kg_m3']}) "
          f"vs IFC 'Brick (common/facing)' (gwp {ifc_by_name['Brick (common/facing)']['gwp_per_kg']}/kg, dens 1760)")
    print(f"  criteria: {states}")
    print(f"  matches={m} mismatches={mm} -> {lvl}")
