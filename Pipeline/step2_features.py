"""
Note: This step is created to make table-based on features. So that in the next step the
features can be compared in the next step.

Features come from each material's name + technical spec/notes. IFC names are
terse, so a small notes table fills in composition the name omits (e.g. float
glass = sand/soda/dolomite), drawn from the methodology report Section V.

Outputs oclca_features.csv and ifc_features.csv, then prints a coverage report.
"""
import re
import pandas as pd

OCLCA_CSV = "all_materials_clean.csv"
IFC_CSV   = "ifc_reference.csv"

# ---------------------------------------------------------------- dictionaries
# Each maps a canonical token -> list of substrings to look for in the text.
INGREDIENTS = {
    "clay":["clay","terracotta","fired earth"], "cement":["cement","opc","clinker"],
    "fly_ash":["fly ash","fly-ash","pfa","pozzolan","pozzolana","falg","fal-g"],
    "slag":["slag","ggbs","ggbfs"], "lime":["lime"], "gypsum":["gypsum","phosphogypsum"],
    "sand":["sand","silica"], "aggregate":["aggregate","gravel","crushed stone"],
    "glass":["glass"], "aluminum":["aluminum","aluminium"],
    "steel":["steel","iron","rebar","ferro"], "copper":["copper"], "zinc":["zinc","galvani"],
    "wood":["timber","wood","plywood","particle board","chipboard","mdf","veneer"],
    "bamboo":["bamboo"], "cork":["cork"], "straw":["straw"],
    "cellulose":["cellulose","paper"],
    "polymer":["pvc","polyurethane","polystyrene","eps","epoxy","polymer","acrylic",
               "vinyl","resin","bitumen","asphalt","rubber","latex"],
    "soil":["soil","earth","mud","adobe"], "stone":["stone","marble","granite"],
    "mineral_wool":["mineral wool","stone wool","rock wool","glass wool"],
}
PROCESSES = {
    "fired":["fired","firing","kiln","burnt"], "extruded":["extrud"],
    "aerated":["aerated","autoclaved","aac","aircrete"], "cast":["cast","precast","mould","mold"],
    "rolled":["rolled","sheet","coil"], "galvanized":["galvani"], "smelted":["smelt","ingot"],
    "float":["float"], "calcined":["calcin","plaster of paris"], "pressed":["press","compress"],
    "sun_dried":["sun dried","sun-dried","air dried","air-dried"], "rammed":["rammed"],
    "sawn":["sawn","sawmill"], "kiln_dried":["kiln dried","kiln-dried"],
    "spun":["spun","centrifug","fiber","fibre"], "blown":["blown","foam"],
    "stabilized":["stabilized","stabilised"],
}
FORM_PRIORITY = [  # first match wins
    ("panel",["panel"]),("board",["board"]),("cladding",["cladding"]),
    ("sheet",["sheet","corrugated"]),("foam",["foam"]),("wool",["wool"]),
    ("block",["block"]),("brick",["brick"]),("tile",["tile"]),
    ("render",["render","plaster","mortar","screed"]),
    ("profile",["profile","section","stud","frame","rebar","reinforcement"]),
    ("bulk",["concrete","cement","aggregate","sand","soil","earth"]),
]
VOIDED = ["hollow","aerated","autoclaved","aircrete","honeycomb","perforated","cellular",
          "voided","lightweight","chamber"]

def extract(text):
    t = " " + str(text).lower() + " "
    ingredients = sorted({k for k, subs in INGREDIENTS.items() if any(s in t for s in subs)})
    processes   = sorted({k for k, subs in PROCESSES.items()   if any(s in t for s in subs)})
    form = ""
    for label, subs in FORM_PRIORITY:
        if any(s in t for s in subs):
            form = label; break
    voided = any(v in t for v in VOIDED)
    m = re.search(r"(\d{1,3})\s*%?\s*recycl", t)
    recycled = int(m.group(1)) if m else (0 if "recycl" not in t else None)
    return ingredients, processes, form, voided, recycled

def featurize(df, name_col, group_col, density_col, text_cols, extra_notes=None):
    out = []
    for _, r in df.iterrows():
        text = " ".join(str(r.get(c, "")) for c in text_cols)
        if extra_notes:
            text += " " + extra_notes.get(r[name_col], "")
        ing, proc, form, voided, rec = extract(text)
        out.append({
            "name": r[name_col],
            "family_or_group": r.get(group_col, ""),
            "density_kg_m3": r.get(density_col, None),
            "product_form": form,
            "voided": voided,
            "process_keywords": "|".join(proc),
            "ingredient_keywords": "|".join(ing),
            "strength_class": r.get("strength_class", None),
            "recycled_pct": rec,
        })
    return pd.DataFrame(out)

# IFC names are terse - fill composition the name omits (methodology report Sec. V)
IFC_NOTES = {
    "Float glass":"sand soda ash dolomite limestone float melt",
    "Plasterboard":"calcined gypsum paper liner",
    "Gypsum panel":"calcined gypsum glass fiber",
    "Cement (ordinary Portland cement, OPC)":"clinker gypsum kiln fired",
    "Portland slag cement":"clinker slag ggbs gypsum",
    "PFA (pulverized fuel ash)/fly ash cement (also known as pozzolana)":"clinker fly ash pozzolana gypsum",
    "Ready mix concrete with ordinary Portland cement (OPC)":"cement gravel aggregate sand cast",
    "Ready mix concrete with fly-ash (30% pozzolana)":"cement fly ash gravel aggregate sand cast",
    "Ready mix concrete with Portland slag cement (25% GGBS)":"cement slag ggbs gravel aggregate sand cast",
    "Dense concrete block":"cement gravel sand cast",
    "Medium density concrete block":"cement expanded clay sand cast",
    "Lightweight concrete block":"cement expanded clay sand cast lightweight",
    "Aircrete (autoclaved aerated concrete)":"fly ash cement lime aerated autoclaved",
    "FaLG (fly ash/lime/gypsum) block":"fly ash lime gypsum",
    "Fiber cement board":"cement silica sand cellulose fiber",
    "Glass reinforced concrete":"cement sand fly ash glass fiber",
    "Brick (common/facing)":"clay fired kiln", "Honeycomb brick":"clay fired kiln hollow",
    "Brick - Bulls trench kiln":"clay fired kiln", "Brick - Clamp kiln":"clay fired kiln",
    "Brick - High draught/zigzag kiln":"clay fired kiln", "Brick - Hoffman kiln":"clay fired kiln",
    "Steel section":"steel iron rolled", "Steel reinforcement (steel rebar)":"steel iron rolled",
    "Galvanized steel stud":"steel iron galvanized", "Aluminum sheet":"aluminum rolled sheet",
    "Aluminum profiled cladding":"aluminum rolled cladding",
    "Polished stone cladding":"stone limestone", "Mud plaster":"clay sand soil straw lime",
    "Rammed earth":"sand clay soil straw rammed",
    "OPC stabilized soil block":"soil cement stabilized",
    "PFA stabilized soil block":"soil fly ash stabilized",
    "Portland slag cement stabilized soil blocks":"soil slag cement stabilized",
}

oclca = pd.read_csv(OCLCA_CSV)
ifc   = pd.read_csv(IFC_CSV)

oclca_f = featurize(oclca, "clean_name", "search_query", "density_kg_m3",
                    ["clean_name","tech_spec","description"])
ifc_f   = featurize(ifc, "ifc_material", "material_group", "density_kg_m3",
                    ["ifc_material"], extra_notes=IFC_NOTES)

oclca_f.to_csv("oclca_features.csv", index=False)
ifc_f.to_csv("ifc_features.csv", index=False)

def coverage(df, label):
    n = len(df)
    print(f"\n--- {label}  ({n} rows) ---")
    print(f"density:            {df['density_kg_m3'].notna().sum()}/{n}")
    print(f"product_form set:   {(df['product_form']!='').sum()}/{n}")
    print(f"voided=True:        {int(df['voided'].sum())}/{n}")
    print(f"process keywords:   {(df['process_keywords']!='').sum()}/{n}")
    print(f"ingredient keywords:{(df['ingredient_keywords']!='').sum()}/{n}")
    print(f"strength_class:     {df['strength_class'].notna().sum()}/{n}")

print("=" * 70)
print("STEP 2 - FEATURE COVERAGE")
print("=" * 70)
coverage(oclca_f, "ONE CLICK")
coverage(ifc_f, "IFC INDIA")

print("\n--- sample: IFC brick family features ---")
print(ifc_f[ifc_f["name"].str.contains("rick")].to_string(index=False))
print("\n--- sample: One Click brick-family features (first 6) ---")
brick = oclca_f[oclca_f["family_or_group"].str.contains("Brick", case=False, na=False)]
print(brick.head(6).to_string(index=False))
