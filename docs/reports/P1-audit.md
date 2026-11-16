# Claim audit metrics

Generated from `python scripts/audit_validate.py --audit eval\audit\claims_audit_v1.csv --overlap eval\audit\claims_audit_v1_overlap_labelled.csv`.

## Overall

- Labelled claims: **200**
- Correct: **193**
- Precision: **96.5%** (Wilson 95% CI 93.0% to 98.3%)
- Not yet labelled: **0**

## Failure breakdown

| Label | Count |
| :-- | --: |
| `CORRECT` | 193 |
| `NOT_A_CLAIM` | 7 |
| `DISTORTED` | 0 |
| `UNSUPPORTED_SPAN` | 0 |
| `DUPLICATE` | 0 |

## Paper-level cluster bootstrap

Claims within a paper are not independent. This interval resamples
whole papers with replacement.

- Clusters (papers): **45**
- Resamples: **2000** (seed 20261114)
- Precision CI: **94.0% to 98.6%**

## Precision by section

| Section | n | Precision |
| :-- | --: | --: |
| 1. Introduction | 2 | 100.0% |
| 10.2.1. Chloroquine and Hydroxychloroquine | 1 | 100.0% |
| 10.2.2. Lopinavir/Ritonavir | 1 | 100.0% |
| 2.1.3. Production of Interferons (Figure 1a III) | 1 | 100.0% |
| 2.1.5. Activation of Dendritic Cells, Macrophages, and Neutrophils (Figure 1a V) | 1 | 100.0% |
| 3. Results | 5 | 100.0% |
| 3.1.1. ACE2 Density and Distribution Changes with Age | 1 | 100.0% |
| 3.2. Disease Severity | 1 | 100.0% |
| 3.2. Model Estimates | 5 | 100.0% |
| 3.3. Correlation between Cervicitis Complicated with HPV Type Infection and the Expression | 2 | 100.0% |
| 3.4. Association between Blood Groups and SARS-CoV-2 Infection | 4 | 100.0% |
| 3.4. ICU Admission | 1 | 100.0% |
| 3.4.1. Diagnostic Value of Patients with High-Risk HPV Infection | 1 | 100.0% |
| 3.5. Any Side Effects after Taking the COVID-19 Vaccine | 4 | 100.0% |
| 3.5. Correlation Analysis of Expression in Patients with Cervicitis Complicated by HPV | 2 | 100.0% |
| 3.7. Factors Associated with the Outcomes | 2 | 100.0% |
| 3.8. Relationship between the Initial Viral Load and the Outcomes | 1 | 100.0% |
| 4.1. Limitation of the Study | 1 | 0.0% |
| 4.1. Summary of Main Results | 1 | 100.0% |
| 4.2. Which Machine Learning Techniques and Compartmental Models Have Been Used for Predicting the Future Course of COVID-19? | 3 | 100.0% |
| 4.5. Are the Vaccines Developed So Far Effective against All the Mutant COVID-19 Strains? | 1 | 100.0% |
| 4.6. Is the Proliferation of COVID-19 an Open Issue to Continue the Research Path? | 1 | 100.0% |
| 6.1. Antivirals | 1 | 100.0% |
| 6.2. Chloroquine and Hydroxychloroquine | 1 | 100.0% |
| Abstract | 27 | 100.0% |
| Adverse events | 1 | 100.0% |
| Antithrombotic therapy in COVID-19 | 2 | 100.0% |
| Antiviral, immunomodulatory, and anti-inflammatory therapy in COVID-19 | 1 | 100.0% |
| Análisis de los objetivos y modelos de predicción clínica | 1 | 100.0% |
| Attitude of healthcare workers towards COVID-19 vaccine | 1 | 100.0% |
| BMP and vesicular/endosomal trafficking | 1 | 100.0% |
| Baseline hematological and inflammatory values predictive of responsive disease | 1 | 0.0% |
| Biomarkers of response to treatment | 1 | 100.0% |
| Body | 9 | 88.9% |
| COVID‐19 and endocrinology | 2 | 100.0% |
| COVID‐19 and gynecology | 1 | 100.0% |
| COVID‐19 and nephrology | 1 | 100.0% |
| COVID‐19 and urology | 1 | 100.0% |
| CQ-induced phospholipidosis and BMP accumulation | 2 | 100.0% |
| Carbohydrates | 1 | 100.0% |
| Case presentation | 4 | 75.0% |
| Clinical characteristics | 2 | 100.0% |
| Combining remdesivir with MBP431 enhances protective efficacy and extends the window of treatment for lethal EVD. | 2 | 100.0% |
| Comparison of possible involved systems in SARS-CoV-2, SARS-CoV, and MERS-CoV infections | 2 | 100.0% |
| Comparison of the effects of SARS-CoV-2, SARS-CoV, and MERS-CoV infection on the immune cell response and cytokine expression in humans | 1 | 100.0% |
| Computational Molecular Modeling of SLL-0197800 as a Prospective Anti-RdRp/Anti-ExoN (Anti-SARS-CoV-2/Anticoronaviral) Drug | 1 | 100.0% |
| Correlation between knowledge, attitude and practice | 1 | 0.0% |
| DISCUSSION | 2 | 100.0% |
| Diagnostic criteria | 1 | 100.0% |
| Discrimination | 2 | 100.0% |
| Discussion | 9 | 100.0% |
| Disturbances of hemostasis and coagulation system among patients with COVID-19 | 2 | 100.0% |
| Dual behaviour of BMP in viral infection and antiviral effects | 1 | 100.0% |
| Effect of socio-economic factors on the KAP level of DF and its prevention | 2 | 100.0% |
| Elective surgery during the COVID-19 pandemic | 2 | 100.0% |
| Experimental challenge of rhesus macaques with SUDV and treatment with remdesivir at 5 dpi. | 1 | 100.0% |
| Factors associated with COVID-19 vaccine hesitancy | 2 | 100.0% |
| Hepato-pancreatico-biliary surgery | 1 | 100.0% |
| How COVID-19 affects the general pediatric population | 1 | 100.0% |
| INTRODUCTION | 2 | 100.0% |
| Introduction | 7 | 100.0% |
| JAK-STAT inhibitors | 1 | 100.0% |
| Knowledge and awareness about signs and symptoms of DF | 1 | 100.0% |
| Laboratory findings | 1 | 100.0% |
| Limitations | 1 | 100.0% |
| Lopinavir/ritonavir | 1 | 100.0% |
| Neurological Manifestations of COVID-19 | 3 | 100.0% |
| Other drugs inducing BMP accumulation | 1 | 100.0% |
| Outcomes | 1 | 100.0% |
| P2X purinoceptor 7 (P2X7) | 1 | 100.0% |
| Pathological Results | 5 | 80.0% |
| Pathophysiology | 2 | 100.0% |
| Postoperative complications in surgical patients with COVID-19 | 1 | 100.0% |
| Prevalence of HPV 16, 18, and 33 DNA in tumor tissues | 5 | 100.0% |
| Radiografía de tórax versus ecografía pulmonar | 3 | 100.0% |
| Reporting descriptive findings | 4 | 75.0% |
| Results | 19 | 100.0% |
| The Neurological Sequelae of COVID-19 | 1 | 100.0% |
| Transmembrane protease serine 2 (TMPRSSS-2) | 1 | 100.0% |
| Venous Thromboembolism (VTE) | 1 | 100.0% |
| Vitamin C | 1 | 100.0% |
| Vitamin D | 1 | 100.0% |

## Agreement (independent second labeler)

- Paired claims: **40**
- Raw agreement: **100.0%**
- Cohen's κ: **not estimable** (both label sets used a single label; raw agreement is degenerate).
## Limitations

- The overlap contains only one label class, so it does not estimate
  agreement on any error class; κ is undefined.
- Precision comes from the primary labeler; agreement is inter-annotator
  agreement on the seeded overlap subset.
- Precision only: no recall is measurable without an exhaustive gold set.
- Claims within a paper are not independent: the Wilson interval treats them
  as independent and is therefore too narrow. Report the paper-level cluster
  bootstrap alongside it; it is still limited by the number of papers audited.
- Agreement is measured on a seeded subset and may not contain examples of
  every error class.
- See `docs/eval/AUDIT_RUBRIC.md` for label definitions and sampling rules.
