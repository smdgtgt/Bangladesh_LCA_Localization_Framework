"""
Note: A comparison between the One Click LCA database and the IFC database from India.
Compares the materials, their functional units and the technical specifications to assess the
feasibility of comparison.
"""
import re
import pandas as pd

# ---- PATHS (edit these two for your machine) -------------------------------
OCLCA_CSV = "all_materials_clean.csv"
IFC_CSV   = "ifc_reference.csv"
# ----------------------------------------------------------------------------

oclca = pd.read_csv(OCLCA_CSV)
ifc   = pd.read_csv(IFC_CSV)

# --- One Click side ---------------------------------------------------------
n_rows   = len(oclca)
n_unique = oclca["resource_id"].nunique()
has_kg   = oclca["gwp_per_kg"].notna().sum()
no_kg    = oclca["gwp_per_kg"].isna().sum()
families = sorted(oclca["search_query"].unique())

print("=" * 70)
print("ONE CLICK LCA (baseline)")
print("=" * 70)
print(f"rows: {n_rows}   unique materials (resource_id): {n_unique}")
print(f"search families: {len(families)}")
print(f"gwp_per_kg populated: {has_kg}/{n_rows}   missing: {no_kg}")
print(f"is_material = True:   {int(oclca['is_material'].sum())}")
print("normalization basis: gwp_per_kg (kg CO2e/kg) already computed in cleaning")
print(f"rows still without a per-kg value (need density or unusable): {no_kg}")

# --- IFC side ---------------------------------------------------------------
print()
print("=" * 70)
print("IFC INDIA (calibration)")
print("=" * 70)
print(f"materials: {len(ifc)}")
print("declared unit per methodology Section E = 1 kg  ->  GWP already per-kg")
print(f"with density: {ifc['density_kg_m3'].notna().sum()}   wall-applicable: {int(ifc['used_as_wall'].sum())}")
print(f"carbon-negative GWP: {(ifc['gwp_per_kg'] < 0).sum()}   "
      f"near-zero |GWP|<0.05: {(ifc['gwp_per_kg'].abs() < 0.05).sum()}")

# --- Family overlap (One Click search family <-> IFC material) --------------
def norm(s):
    return set(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split())

ifc_tokens = {m: norm(m) for m in ifc["ifc_material"]}

def best_ifc(query):
    q = norm(query)
    best, score = None, 0.0
    for m, t in ifc_tokens.items():
        j = len(q & t) / len(q | t) if (q | t) else 0
        if j > score:
            best, score = m, j
    return best, round(score, 2)

overlap = pd.DataFrame(
    [(f, *best_ifc(f)) for f in families],
    columns=["oclca_family", "best_ifc_match", "token_overlap"]
).sort_values("token_overlap", ascending=False)

strong  = overlap[overlap["token_overlap"] >= 0.4]
weak    = overlap[overlap["token_overlap"] <  0.4]

print()
print("=" * 70)
print("FAMILY OVERLAP  (One Click family -> nearest IFC material)")
print("=" * 70)
print(f"clear matches (overlap >= 0.4): {len(strong)} / {len(families)}")
print(f"need manual mapping (< 0.4):    {len(weak)} / {len(families)}")
print()
print("--- families needing a manual IFC mapping decision ---")
print(weak.to_string(index=False))
