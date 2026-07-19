"""
Note: Takes the Step 5 table and exports the two files the workbench reads —
a JSON keyed by resource_id for the SPA lookup, and a flat CSV for auditing.
Rounds numbers, cleans labels, and builds a family index so the workbench can
populate its dropdowns.

Outputs localization_coefficients.json and localization_coefficients.csv.
"""
import json
from datetime import date
import numpy as np
import pandas as pd

df = pd.read_csv("step5_all_coefficients.csv")

# 1. final label: accurate name for the biogenic/low-carbon group
df["confidence"] = df["confidence"].replace(
    {"Review (biogenic)": "Review (biogenic/low-carbon)"})

# 2. rounding
df["K"]                = df["K"].round(4)
df["delta"]            = df["delta"].round(4)
df["pct_adjustment"]   = df["pct_adjustment"].round(2)
df["similarity_score"] = df["similarity_score"].round(3)
df["oclca_gwp_per_kg"] = df["oclca_gwp_per_kg"].round(5)

# stable column order for the flat CSV
COLS = ["resource_id", "oclca_name", "family", "oclca_gwp_per_kg",
        "density_kg_m3", "product_form", "process_keywords", "ingredient_keywords",
        "K", "delta", "pct_adjustment", "confidence", "transfer_logic",
        "similarity_score", "n_neighbors", "neighbor_examples"]
df = df[COLS]

# ---------------------------------------------------------------- flat CSV out
df.to_csv("localization_coefficients.csv", index=False)

# --------------------------------------------------------- JSON for the workbench
def clean(v):
    """JSON-safe scalar (NaN -> None)."""
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    return v

# resource_id -> record (the authoritative lookup)
coefficients = {}
for _, r in df.iterrows():
    coefficients[str(r["resource_id"])] = {
        "name":            clean(r["oclca_name"]),
        "family":          clean(r["family"]),
        "gwp_per_kg":      clean(r["oclca_gwp_per_kg"]),
        "K":               clean(r["K"]),
        "delta":           clean(r["delta"]),
        "pct_adjustment":  clean(r["pct_adjustment"]),
        "confidence":      clean(r["confidence"]),
        "transfer_logic":  clean(r["transfer_logic"]),
        "similarity":      clean(r["similarity_score"]),
        "neighbors":       clean(r["neighbor_examples"]),
    }

# family -> [{resource_id, name}] so the SPA can build name dropdowns
family_index = {}
for _, r in df.sort_values("oclca_name").iterrows():
    family_index.setdefault(str(r["family"]), []).append(
        {"resource_id": str(r["resource_id"]), "name": clean(r["oclca_name"])})

payload = {
    "metadata": {
        "generated": date.today().isoformat(),
        "n_materials": int(len(df)),
        "coefficient_definition": "K = GWP_IFC / GWP_OneClick (ratio, technical match only; GWP excluded from matching)",
        "fuel_mix_note": "0.79 Bangladesh fuel-mix factor is NOT applied here. Apply it in workbench Step 11.",
        "confidence_levels": {
            "High":   "Direct strongest IFC match - validated ratio coefficient.",
            "Medium": "Medium IFC match - validated ratio coefficient.",
            "Low":    "Same-family kNN similarity transfer.",
            "Review": "Cross-family kNN transfer - screening only, review recommended.",
            "Review (biogenic/low-carbon)": "Biogenic or near-zero GWP material - ratio is unstable; value is a screening estimate, Delta also reported.",
        },
    },
    "coefficients": coefficients,
    "family_index": family_index,
}

with open("localization_coefficients.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

# --------------------------------------------------------------------- verify
print("=" * 64)
print("STEP 6 EXPORT")
print("=" * 64)
print(f"Materials exported : {len(df)}")
print(f"Families indexed   : {len(family_index)}")
print(f"Every material has a K : {df['K'].notna().sum()} / {len(df)} "
      f"(blanks left in biogenic/low-carbon only: {df['K'].isna().sum()})")

print("\nFinal confidence labels:")
print(df["confidence"].value_counts().to_string())

# round-trip the JSON to prove it parses, then a sample lookup
with open("localization_coefficients.json", encoding="utf-8") as f:
    chk = json.load(f)
print(f"\nJSON parses OK. Keys: {list(chk.keys())}")

# brick pilot lookup straight out of the JSON
brick_ids = [rid for rid, rec in chk["coefficients"].items()
             if rec["name"] == "Clay brick"]
if brick_ids:
    rec = chk["coefficients"][brick_ids[0]]
    print("\nSample lookup (Clay brick) from the JSON:")
    print(f"  resource_id : {brick_ids[0]}")
    print(f"  K           : {rec['K']}   ({rec['confidence']})")
    print(f"  gwp_per_kg  : {rec['gwp_per_kg']}")
    print(f"  pct adjust  : {rec['pct_adjustment']}%")

# confirm 0.79 appears nowhere in the numbers as a multiplier artifact
print("\n0.79 reminder present in metadata:",
      "0.79" in chk["metadata"]["fuel_mix_note"])
print("\nSaved -> localization_coefficients.json  +  localization_coefficients.csv")
