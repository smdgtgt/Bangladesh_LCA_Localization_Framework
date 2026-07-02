"""
Clean scraped One Click LCA CSVs for embedding in the LCA workbench.

What it does (NON-destructive: it only adds columns and flags, never deletes data):
  1. Uses name_en as the clean base name (full_name keeps the specs jammed in).
  2. Parses tech_spec into structured numeric columns:
        density_kg_m3, mass_per_area_kg_m2, thickness_mm,
        lambda_w_mk, strength_class, per_unit_mass_kg
  3. Reconciles the mixed GWP units. Adds:
        gwp_basis        - the original unit (m3 / m2 / kg / unit / m)
        gwp_per_kg       - GWP normalized to 1 kg where conversion is possible
        gwp_per_m3       - GWP normalized to 1 m3 where possible
        norm_method      - how the normalization was done (or why it couldn't be)
  4. Flags rows for review instead of dropping them:
        is_material      - False for "per unit" MEP/equipment rows
        gwp_missing      - True where gwp_kgco2e is blank
        query_mismatch   - True where the family in name_en doesn't match search_query

Run (in VS Code terminal, from the folder with the CSVs):
    pip install pandas openpyxl
    python clean_oclca.py
Outputs: ./cleaned/all_materials_clean.csv  (+ per-file copies)
"""

import re
import glob
from pathlib import Path
import pandas as pd

OUT = Path("./cleaned")

# ----- tech_spec field extractors -------------------------------------------
def _num(pattern, text, group=1):
    m = re.search(pattern, text, re.IGNORECASE)
    return float(m.group(group)) if m else None

def parse_tech_spec(ts: str) -> dict:
    if not isinstance(ts, str):
        return {}
    out = {}
    out["density_kg_m3"]       = _num(r"(\d+(?:\.\d+)?)\s*kg/?\s*m\s*[3³]", ts)
    out["mass_per_area_kg_m2"] = _num(r"(\d+(?:\.\d+)?)\s*kg/?\s*m\s*2", ts)
    out["thickness_mm"]        = _num(r"(\d+(?:\.\d+)?)\s*mm\b", ts)
    out["lambda_w_mk"]         = _num(r"(?:L|Lambda)\s*=?\s*(\d+(?:\.\d+)?)\s*W", ts)
    out["per_unit_mass_kg"]    = _num(r"(\d+(?:\.\d+)?)\s*kg/unit", ts)
    sc = re.search(r"\b(C\d{2}/\d{2})\b", ts)
    out["strength_class"] = sc.group(1) if sc else None
    return out

# ----- GWP unit normalization -----------------------------------------------
def normalize_gwp(row) -> dict:
    gwp, unit = row.get("gwp_kgco2e"), row.get("unit_for_data")
    d  = row.get("density_kg_m3")
    ma = row.get("mass_per_area_kg_m2")
    res = {"gwp_per_kg": None, "gwp_per_m3": None, "norm_method": None}

    if pd.isna(gwp):
        res["norm_method"] = "no_gwp"
        return res
    gwp = float(gwp)

    if unit == "kg":
        res.update(gwp_per_kg=gwp, norm_method="native_kg")
        if d: res["gwp_per_m3"] = gwp * d
    elif unit == "m3":
        res.update(gwp_per_m3=gwp, norm_method="native_m3")
        if d: res["gwp_per_kg"] = gwp / d
    elif unit == "m2":
        if ma:
            res.update(gwp_per_kg=gwp / ma, norm_method="m2_via_mass_per_area")
            if d: res["gwp_per_m3"] = (gwp / ma) * d
        else:
            res["norm_method"] = "m2_no_mass_per_area"
    elif unit == "unit":
        pum = row.get("per_unit_mass_kg")
        if pum:
            res.update(gwp_per_kg=gwp / pum, norm_method="unit_via_per_unit_mass")
        else:
            res["norm_method"] = "unit_unconvertible"
    else:
        res["norm_method"] = f"unhandled_unit_{unit}"
    return res

# ----- row-level flags ------------------------------------------------------
def family_token(name: str) -> str:
    return re.split(r"[ ,]", str(name).strip().lower())[0] if isinstance(name, str) else ""

def main():
    OUT.mkdir(exist_ok=True)
    files = [f for f in sorted(glob.glob("*.csv")) if "_clean" not in f]
    if not files:
        print("No CSVs found in this folder."); return

    frames = []
    for f in files:
        df = pd.read_csv(f)
        df["source_file"] = f
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    print(f"Loaded {len(df)} rows from {len(files)} files.")

    df["clean_name"] = df["name_en"].str.strip()
    specs = df["tech_spec"].apply(parse_tech_spec).apply(pd.Series)
    df = pd.concat([df, specs], axis=1)

    norm = df.apply(normalize_gwp, axis=1).apply(pd.Series)
    df = pd.concat([df, norm], axis=1)

    df["gwp_basis"]    = df["unit_for_data"]
    df["gwp_missing"]  = df["gwp_kgco2e"].isna()
    df["is_material"]  = df["unit_for_data"] != "unit"
    # flag rows whose clean_name family differs from what the search asked for
    df["query_mismatch"] = [
        family_token(n) != family_token(q)
        for n, q in zip(df["clean_name"], df["search_query"])
    ]

    df.to_csv(OUT / "all_materials_clean.csv", index=False)
    for f in files:
        df[df.source_file == f].to_csv(OUT / f"{Path(f).stem}_clean.csv", index=False)

    # ---- report ----
    print("\n--- normalization ---")
    print(df["norm_method"].value_counts().to_string())
    print(f"\ngwp_per_kg populated : {df.gwp_per_kg.notna().sum()} / {len(df)}")
    print(f"gwp_per_m3 populated : {df.gwp_per_m3.notna().sum()} / {len(df)}")
    print("\n--- flags ---")
    print(f"non-material (per-unit) rows : {(~df.is_material).sum()}")
    print(f"missing gwp                  : {df.gwp_missing.sum()}")
    print(f"query/name family mismatch   : {df.query_mismatch.sum()}")
    print(f"\nWrote {OUT/'all_materials_clean.csv'}")

if __name__ == "__main__":
    main()
