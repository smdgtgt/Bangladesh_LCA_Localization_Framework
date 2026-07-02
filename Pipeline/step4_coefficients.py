"""
STEP 4 - Validated anchor coefficients.

For every strongest / medium pair from Step 3, compute the localization
coefficient as a RATIO:

    K = GWP_IFC / GWP_OneClick        (same per-kg basis; the 0.79 fuel-mix
                                        factor is NOT applied here)

Also reports the absolute difference and the % adjustment:
    delta = GWP_IFC - GWP_OneClick
    pct   = (K - 1) * 100

Carbon-negative / near-zero handling: a ratio is only meaningful when both
sides are safely positive. Where either side is < 0.05 kg CO2e/kg (negative
or near-zero, i.e. the biogenic timber/cork/earth materials), the ratio is
numerically unstable and physically meaningless as a multiplier, so K is
flagged 'biogenic_or_nearzero' and only the well-defined delta is reported.

Outputs:
  anchor_coefficients.csv  - one row per validated pair, with K / delta / pct
  family_anchors.csv       - representative K per family (input to Step 5)

Run:  python step4_coefficients.py
"""
import pandas as pd
import numpy as np

MATCHES = "matching_results.csv"
POS_EPS = 0.05      # below this (or negative) the ratio is not trustworthy

m = pd.read_csv(MATCHES)
anchors = m[m["level"].isin(["strongest", "medium"])].copy()

def coeff(row):
    o, i = row["oclca_gwp_per_kg"], row["ifc_gwp_per_kg"]
    if pd.isna(o) or pd.isna(i):
        return pd.Series([np.nan, np.nan, np.nan, "no_gwp"])
    delta = i - o
    if o >= POS_EPS and i >= POS_EPS:
        K = i / o
        return pd.Series([K, delta, (K - 1) * 100, "ratio"])
    return pd.Series([np.nan, delta, np.nan, "biogenic_or_nearzero"])

anchors[["K", "delta", "pct_adjustment", "coefficient_status"]] = anchors.apply(coeff, axis=1)
anchors.to_csv("anchor_coefficients.csv", index=False)

valid = anchors[anchors["coefficient_status"] == "ratio"]
flagged = anchors[anchors["coefficient_status"] == "biogenic_or_nearzero"]
nogwp = anchors[anchors["coefficient_status"] == "no_gwp"]

print("=" * 70)
print("STEP 4 - VALIDATED ANCHOR COEFFICIENTS")
print("=" * 70)
print(f"strongest + medium pairs: {len(anchors)}")
print(f"  valid ratio K:          {len(valid)}")
print(f"  flagged biogenic/near-0:{len(flagged)}")
print(f"  no One Click GWP:       {len(nogwp)}")

# --- identify each family's TRUE IFC counterpart (by name) ------------------
import re
iref = pd.read_csv("ifc_reference.csv")
ifc_gwp = dict(zip(iref["ifc_material"], iref["gwp_per_kg"]))
def toks(s): return set(re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split())
ifc_tok = {n: toks(n) for n in iref["ifc_material"]}
# Representative overrides where a generic family name is ambiguous by tokens.
# IFC report designates "common/facing" as the representative brick value.
FAMILY_IFC_OVERRIDE = {"Brick": "Brick (common/facing)"}
def primary_ifc(fam):
    if fam in FAMILY_IFC_OVERRIDE:
        return FAMILY_IFC_OVERRIDE[fam]
    ft = toks(fam); best, sc = None, 0.0
    for n, t in ifc_tok.items():
        j = len(ft & t) / len(ft | t) if (ft | t) else 0
        if j > sc: best, sc = n, j
    return best
fam_primary = {f: primary_ifc(f) for f in anchors["family"].unique()}

# --- per-family representative anchor, tied to the true IFC counterpart -----
def family_anchor(g):
    fam = g.name
    primary = fam_primary[fam]
    pg = ifc_gwp.get(primary)
    n_str = int((g["level"] == "strongest").sum())
    n_med = int((g["level"] == "medium").sum())
    base = {"n_strongest": n_str, "n_medium": n_med,
            "primary_ifc": primary, "primary_ifc_gwp": pg}
    # carbon-negative / near-zero counterpart -> flag the whole family
    if pg is None or pg < POS_EPS:
        return pd.Series({**base, "anchor_K": np.nan, "pct_adjustment": np.nan,
                          "anchor_source": "biogenic_or_nearzero"})
    # representative One Click value = median of positive strongest (else medium)
    for lvl, src in [("strongest", "strongest"), ("medium", "medium")]:
        o = g.loc[g["level"] == lvl, "oclca_gwp_per_kg"].dropna()
        o = o[o >= POS_EPS]
        if not o.empty:
            K = pg / o.median()
            return pd.Series({**base, "anchor_K": round(K, 3),
                              "pct_adjustment": round((K - 1) * 100, 1),
                              "anchor_source": src})
    return pd.Series({**base, "anchor_K": np.nan, "pct_adjustment": np.nan,
                      "anchor_source": "no_positive_oclca"})

fam = anchors.groupby("family").apply(family_anchor, include_groups=False).reset_index()
fam.to_csv("family_anchors.csv", index=False)

with_anchor = fam[fam["anchor_K"].notna()]
biogenic_fam = fam[fam["anchor_source"] == "biogenic_or_nearzero"]
print(f"\nfamilies with a usable positive anchor: {len(with_anchor)} / {len(fam)}")
print(f"families flagged biogenic/near-zero:    {len(biogenic_fam)}")
print("(both groups still get coefficients via similarity transfer in Step 5)")

print("\n--- per-family anchor coefficients (sorted by K) ---")
show = with_anchor.sort_values("anchor_K", ascending=False)
print(show[["family", "primary_ifc_gwp", "n_strongest", "n_medium",
            "anchor_K", "pct_adjustment", "anchor_source"]].to_string(index=False))

if len(biogenic_fam):
    print("\n--- families flagged biogenic / near-zero (ratio not defined) ---")
    print(biogenic_fam[["family", "primary_ifc", "primary_ifc_gwp"]].to_string(index=False))

print("\n--- BRICK anchor check (should be ~1.65, i.e. IFC ~65% above One Click) ---")
brk = valid[(valid["family"].str.contains("rick", case=False)) &
            (valid["oclca_name"].str.fullmatch("Clay brick", case=False, na=False))]
if len(brk):
    r = brk.iloc[0]
    print(f"  Clay brick {r['oclca_gwp_per_kg']:.3f}  ->  IFC {r['ifc_anchor']} {r['ifc_gwp_per_kg']:.2f}")
    print(f"  K = {r['K']:.3f}   delta = {r['delta']:+.3f}   adjustment = {r['pct_adjustment']:+.1f}%")

if len(flagged):
    print("\n--- flagged (ratio not defined - biogenic / near-zero), delta still reported ---")
    print(flagged[["oclca_name", "family", "oclca_gwp_per_kg", "ifc_gwp_per_kg", "delta"]]
          .drop_duplicates("oclca_name").head(20).to_string(index=False))
