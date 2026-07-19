# Bangladesh_LCA_Localization_Framework
Open-source framework for estimating cradle-to-gate embodied carbon (A1-A3) of construction materials in data-scarce contexts along with transportation (A4) based on projects. It contains the LCA Localization Workbench (an interactive tool) and the Python analysis pipeline used to derive localized carbon coefficients, developed for the case of Bangladesh.
This repository accompanies the M.S. thesis Decarbonizing the Built Environment of Bangladesh: Building a Framework to Calculate Embodied Carbon in Data-Scarce Contexts (Smita Sabnam, 2026), and publishes the source code from its appendices.
This repository includes the source code and a standalone LCA Workbench. Separate raw, cleaned, intermediate, and final CSV datasets are not redistributed here. The code documents the full method and can be run against your own equivalent inputs.

 1. Workbench/ — the LCA Localization Workbench, a single-file interactive tool (thesis Appendix A). Its coefficients are embedded in the file, so it runs standalone with no data or setup.
 2. Global Data Cleaning Process/ — clean_oclca.py, which compiles and cleans raw material exports into a single normalized table   (thesis Appendix D).
 3. Pipeline/ — six numbered scripts that take the cleaned data and derive the localization coefficients (thesis Appendices E–J).

## Method
The core localization equation is:
```
GWP_BD(A1–A3) = GWP_OCL × K × F
```
Here, 
GWP_OCL = Carbon emission data from One Click LCA 
K = India-side A1–A3 GWP value for material family m/ One Click LCA A1–A3 GWP value for material family m
F = Fuel mix factor (Bangladesh fuel-carbon intensity / India fuel-carbon intensity)
  = I_fuel,BD / I_fuel,IN

For Carbon emission (transportation to site), 
```
GWP_BD A4 = Qm x D x FCmode x EFfuel
```
Here, 
Qm = Transported quantity of material m
D = Route Distance 
FCmode = Fuel-consumption rate for the selected transport mode, expressed per tonne-kilometer
EFfuel = Emission factor of the selected fuel

For, Carbon emission (Cradle to transportation to site),
For 
```
GWP_BD(A1–A4) = GWP_BD(A1–A3) + GWP_BD A4
```

## Repository structure
Bangladesh_LCA_Localization_Framework/
├── README.md
├── LICENSE
├── Workbench/
│   └── LCA_Workbench_Tool.html      # interactive tool (Appendix A)
├── Global Data Cleaning Process/
│   └── clean_oclca.py               # compile + clean material records (Appendix D)
└── Pipeline/
    ├── step1_load_normalize.py      # load + normalize units (Appendix E)
    ├── step2_features.py            # feature extraction (Appendix F)
    ├── step3_matching.py            # material matching matrix (Appendix G)
    ├── step4_coefficients.py        # coefficient derivation (Appendix H)
    ├── step5_similarity_transfer.py # kNN similarity transfer (Appendix I)
    └── step6_export.py              # final export (Appendix J)

## Using the Workbench
Download `Workbench/LCA_Workbench_Tool.html` and open it in any modern web browser. No installation, server, or separate CSV files are required.

## Running the pipeline
The scripts read and write plain CSVs in the current working directory, and run in order.
  1. Cleaning stage. Copy clean_oclca.py into a local folder containing the authorized raw CSV exports, then run: `python clean_oclca.py.` It produces all_materials_clean.csv:
     `python "Global Data Cleaning Process/clean_oclca.py"`
  2. Analysis stage. With all_materials_clean.csv and your ifc_reference.csv in the working directory, run the pipeline in sequence:
     `python Pipeline/step1_load_normalize.py`
     `python Pipeline/step2_features.py`
     `python Pipeline/step3_matching.py`
     `python Pipeline/step4_coefficients.py`
     `python Pipeline/step5_similarity_transfer.py`
     `python Pipeline/step6_export.py`

The final step writes localization_coefficients.csv (and .json), the coefficient table consumed by the Workbench.
Dependencies: pandas, numpy, and scikit-learn.

## Citation: 
If you use this code, please cite the software:
Sabnam, S. (2026). Bangladesh LCA Localization Framework (Version 1.0.1) [Computer software]. Zenodo. https://doi.org/10.5281/zenodo.21140237

And the accompanying thesis:
CITATION: Sabnam, S. (2026). Decarbonizing the Built Environment of Bangladesh: Building a Framework to Calculate Embodied Carbon in Data-Scarce Contexts [M.S. thesis, Iowa State University]

