"""Curated Medical Conditions & Symptoms Knowledge Base for MeetAdr Discovery."""
from typing import List, Dict, Any, Optional

HEALTH_CONDITIONS: List[Dict[str, Any]] = [
    # A
    {
        "id": "allergies-asthma",
        "letter": "A",
        "name": "Allergies & Asthma",
        "specialist": "Allergist / Immunologist",
        "specialty": "Pulmonology",
        "description": "Seasonal allergic rhinitis, bronchospasm, asthma flare-ups and wheezing.",
        "symptoms": ["Shortness of breath", "Wheezing", "Sneezing", "Chest tightness", "Runny nose"],
        "causes": ["Pollen, dust mites, pet dander", "Airborne mold spores", "Cold dry air", "Respiratory viral infections"],
        "risk_factors": ["Family history of atopy", "Urban air pollution", "Occupational chemical exposure"],
        "prevention": ["HEPA air filtration", "Dust mite covers", "Pollen count monitoring", "Annual influenza vaccine"],
        "management": ["Inhaled corticosteroids", "Short-acting beta agonists (albuterol)", "Sublingual immunotherapy"],
    },
    {
        "id": "anxiety-depression",
        "letter": "A",
        "name": "Anxiety & Depression",
        "specialist": "Psychiatrist / Psychologist",
        "specialty": "Psychiatry",
        "description": "Chronic stress, generalized anxiety disorder, panic attacks and depressive episodes.",
        "symptoms": ["Persistent worry", "Restlessness", "Fatigue", "Sleep disturbances", "Loss of interest"],
        "causes": ["Neurochemical imbalances", "Chronic psychosocial stress", "Traumatic life events"],
        "risk_factors": ["Family history of mood disorders", "Chronic illness", "Substance misuse"],
        "prevention": ["Regular aerobic exercise", "Mindfulness meditation", "Adequate sleep hygiene"],
        "management": ["Cognitive behavioral therapy (CBT)", "SSRIs / SNRIs", "Structured stress reduction routines"],
    },
    {
        "id": "arthritis-joint-inflammation",
        "letter": "A",
        "name": "Arthritis & Joint Inflammation",
        "specialist": "Rheumatologist",
        "specialty": "Rheumatology",
        "description": "Osteoarthritis, rheumatoid arthritis, gout and chronic morning joint stiffness.",
        "symptoms": ["Joint pain and swelling", "Morning stiffness >30 mins", "Reduced range of motion", "Warmth around joints"],
        "causes": ["Cartilage wear and tear", "Autoimmune synovial inflammation", "Uric acid crystal deposition"],
        "risk_factors": ["Advanced age", "Previous joint injury", "Obesity", "Repetitive joint stress"],
        "prevention": ["Low-impact exercise (swimming, cycling)", "Weight management", "Ergonomic joint protection"],
        "management": ["NSAIDs", "DMARDs", "Physical therapy", "Hyaluronic acid injections"],
    },
    {
        "id": "acid-reflux-gerd",
        "letter": "A",
        "name": "Acid Reflux & GERD",
        "specialist": "Gastroenterologist",
        "specialty": "Gastroenterology",
        "description": "Gastroesophageal reflux disease, persistent heartburn, regurgitation and chest discomfort.",
        "symptoms": ["Substernal burning sensation", "Acidic regurgitation", "Difficulty swallowing (dysphagia)", "Chronic dry cough"],
        "causes": ["Lower esophageal sphincter laxity", "Hiatal hernia", "Delayed gastric emptying"],
        "risk_factors": ["Obesity", "Pregnancy", "Smoking", "Late-night heavy meals"],
        "prevention": ["Elevating bed headrest 15cm", "Avoiding trigger foods (coffee, citrus, mint)", "Not lying down for 3h post-meal"],
        "management": ["Proton pump inhibitors (PPIs)", "H2 receptor antagonists", "Dietary modification"],
    },

    # B
    {
        "id": "back-pain-sciatica",
        "letter": "B",
        "name": "Back Pain & Sciatica",
        "specialist": "Orthopedic Surgeon / Physiotherapist",
        "specialty": "Orthopedics",
        "description": "Lumbar disc herniation, lower back muscle spasm, sciatica and radiating leg numbness.",
        "symptoms": ["Lower lumbar aching", "Shooting leg pain along sciatic nerve", "Numbness in foot or toes"],
        "causes": ["Herniated intervertebral disc", "Spinal stenosis", "Poor postural mechanics"],
        "risk_factors": ["Sedentary occupation", "Heavy lifting without core engagement", "Smoking", "Obesity"],
        "prevention": ["Core musculature stabilization", "Ergonomic workspace", "Proper lifting technique"],
        "management": ["Targeted physical therapy", "Epidural corticosteroid injections", "Anti-inflammatory medications"],
    },
    {
        "id": "bronchitis-cough",
        "letter": "B",
        "name": "Bronchitis & Chronic Cough",
        "specialist": "Pulmonologist / General Physician",
        "specialty": "General Medicine",
        "description": "Acute bronchial inflammation, persistent mucus-producing cough and chest soreness.",
        "symptoms": ["Productive cough with clear/yellow mucus", "Fatigue", "Low-grade fever", "Chest tightness"],
        "causes": ["Respiratory viruses", "Bacterial superinfection", "Tobacco smoke and aerosol exposure"],
        "risk_factors": ["Active or passive smoking", "Chronic sinus infection", "Immunocompromise"],
        "prevention": ["Smoking cessation", "Frequent handwashing", "Air filtration"],
        "management": ["Hydration and humidified air", "Bronchodilators", "Expectorants"],
    },

    # C
    {
        "id": "chronic-migraine",
        "letter": "C",
        "name": "Chronic Migraine & Cephalea",
        "specialist": "Neurologist",
        "specialty": "Neurology",
        "description": "Severe throbbing unilateral headaches with visual aura, photophobia and nausea.",
        "symptoms": ["Pulsating unilateral head pain", "Visual aura (flashes, zigzag lines)", "Nausea and vomiting", "Light sensitivity"],
        "causes": ["Trigeminovascular pathway activation", "Neurotransmitter fluctuations", "Cortical spreading depression"],
        "risk_factors": ["Female gender", "Hormonal shifts", "High caffeine withdrawal", "Irregular sleep"],
        "prevention": ["Consistent sleep schedule", "Adequate hydration", "Stress management"],
        "management": ["Triptans for acute abortive therapy", "CGRP receptor antagonists", "Prophylactic therapy"],
    },
    {
        "id": "coronary-artery-disease",
        "letter": "C",
        "name": "Coronary Artery Disease & Angina",
        "specialist": "Cardiologist",
        "specialty": "Cardiology",
        "description": "Atherosclerotic plaque accumulation in coronary arteries causing exertional chest pain.",
        "symptoms": ["Exertional chest pressure / squeezing", "Pain radiating to jaw or left arm", "Dyspnea on exertion"],
        "causes": ["Atherosclerotic lipid plaque rupture", "Endothelial dysfunction", "Arterial calcification"],
        "risk_factors": ["Elevated LDL cholesterol", "Hypertension", "Diabetes mellitus", "Tobacco use"],
        "prevention": ["Cardioprotective diet", "Cardiovascular exercise 150 min/week", "Lipid management"],
        "management": ["Statins and antiplatelet agents", "Beta-blockers", "Coronary angioplasty with stent"],
    },

    # D
    {
        "id": "diabetes-mellitus",
        "letter": "D",
        "name": "Diabetes Mellitus (Type 1 & 2)",
        "specialist": "Endocrinologist",
        "specialty": "Endocrinology",
        "description": "Impaired glucose regulation due to pancreatic beta-cell dysfunction or peripheral insulin resistance.",
        "symptoms": ["Polydipsia (excessive thirst)", "Polyuria (frequent urination)", "Unexplained weight loss", "Fatigue"],
        "causes": ["Autoimmune pancreatic islet destruction (T1D)", "Peripheral insulin receptor resistance (T2D)"],
        "risk_factors": ["Sedentary lifestyle", "Obesity", "Family history", "Hypertension"],
        "prevention": ["Low glycemic index nutrition", "Daily moderate exercise", "Annual HbA1c screening"],
        "management": ["Insulin replacement therapy", "Metformin & SGLT2 inhibitors", "Continuous glucose monitoring (CGM)"],
    },
    {
        "id": "dermatitis-eczema",
        "letter": "D",
        "name": "Dermatitis & Eczema",
        "specialist": "Dermatologist",
        "specialty": "Dermatology",
        "description": "Chronic inflammatory epidermal barrier breakdown with erythema, pruritus and flaking.",
        "symptoms": ["Intense itching (pruritus)", "Erythematous scaly patches", "Lichenification from scratching", "Skin fissures"],
        "causes": ["Filaggrin gene mutation", "Skin microbiome dysbiosis", "Allergen hyper-reactivity"],
        "risk_factors": ["Atopic triad history", "Low ambient humidity", "Harsh surfactant detergents"],
        "prevention": ["Ceramide-rich emollient application", "Lukewarm short showers", "Fragrance-free clothing"],
        "management": ["Topical corticosteroids", "Calcineurin inhibitors", "Phototherapy", "Biologics (dupilumab)"],
    },

    # E
    {
        "id": "ear-infections-otitis",
        "letter": "E",
        "name": "Ear Infections & Otitis Media",
        "specialist": "ENT Specialist",
        "specialty": "ENT",
        "description": "Acute or serous inflammation of the middle ear with tympanic effusion and otalgia.",
        "symptoms": ["Severe sharp ear pain", "Muffled hearing", "Aural fullness", "Tympanic membrane erythema"],
        "causes": ["Eustachian tube dysfunction", "Streptococcus pneumoniae infection", "Post-viral nasopharyngeal edema"],
        "risk_factors": ["Young age", "Daycare attendance", "Bottle feeding lying down"],
        "prevention": ["Pneumococcal vaccination", "Upright infant feeding", "Prompt upper respiratory care"],
        "management": ["Analgesic ear drops", "Targeted oral antibiotics", "Myringotomy with tympanostomy tubes"],
    },

    # H
    {
        "id": "hypertension-blood-pressure",
        "letter": "H",
        "name": "Hypertension (High Blood Pressure)",
        "specialist": "Cardiologist / Internal Medicine",
        "specialty": "Cardiology",
        "description": "Sustained arterial systemic vascular resistance exceeding 130/80 mmHg.",
        "symptoms": ["Often asymptomatic ('silent killer')", "Morning occipital headaches", "Visual blurring", "Epistaxis"],
        "causes": ["Renal sodium retention", "Arterial stiffness", "Sympathetic nervous overactivity"],
        "risk_factors": ["Excess dietary sodium (>2g/day)", "Chronic stress", "Obesity", "Sleep apnea"],
        "prevention": ["DASH dietary pattern", "Sodium restriction (<1500mg/day)", "Daily brisk walking"],
        "management": ["ACE inhibitors / ARBs", "Calcium channel blockers", "Thiazide diuretics", "Home BP monitoring"],
    },

    # K
    {
        "id": "kidney-stones-nephrolithiasis",
        "letter": "K",
        "name": "Kidney Stones (Nephrolithiasis)",
        "specialist": "Urologist",
        "specialty": "Urology",
        "description": "Crystalline mineral deposits forming within renal calyces causing severe flank pain.",
        "symptoms": ["Colicky flank pain radiating to groin", "Gross hematuria", "Nausea and vomiting", "Dysuria"],
        "causes": ["Calcium oxalate supersaturation", "Hyperuricosuria", "Low urinary citrate concentration"],
        "risk_factors": ["Chronic dehydration in hot climates (UAE)", "High animal protein intake", "Family history"],
        "prevention": ["High fluid intake (>3L/day)", "Dietary sodium reduction", "Lemonade/citrate supplementation"],
        "management": ["Alpha-blockers for stone expulsion", "Extracorporeal shock wave lithotripsy (ESWL)", "Ureteroscopy"],
    },

    # T
    {
        "id": "thyroid-disorders",
        "letter": "T",
        "name": "Thyroid Disorders (Hypo/Hyperthyroidism)",
        "specialist": "Endocrinologist",
        "specialty": "Endocrinology",
        "description": "Autoimmune or functional dysregulation of thyroid hormone secretion impacting metabolic rate.",
        "symptoms": ["Cold intolerance & weight gain (Hypo)", "Heat intolerance & tremors (Hyper)", "Fatigue", "Hair thinning"],
        "causes": ["Hashimoto's thyroiditis (autoimmune hypo)", "Graves' disease (autoimmune hyper)", "Thyroid nodules"],
        "risk_factors": ["Female gender", "Postpartum state", "Family history of autoimmune disease"],
        "prevention": ["Adequate dietary iodine", "Periodic TSH screening"],
        "management": ["Levothyroxine sodium (Hypo)", "Antithyroid medications (Methimazole)", "Radioactive iodine"],
    },
]

def get_conditions_alphabet() -> List[str]:
    """Return distinct uppercase letters available in the directory."""
    return sorted(list(set(c["letter"] for c in HEALTH_CONDITIONS)))

def filter_conditions(letter: Optional[str] = None, search: Optional[str] = None) -> List[Dict[str, Any]]:
    """Filter health conditions by A-Z letter and search keyword."""
    results = HEALTH_CONDITIONS

    if letter and letter.upper() != "ALL":
        target_letter = letter.upper().strip()
        results = [c for c in results if c["letter"] == target_letter]

    if search:
        q = search.lower().strip()
        results = [
            c for c in results
            if (
                q in c["name"].lower() or
                q in c["specialty"].lower() or
                q in c["specialist"].lower() or
                q in c["description"].lower() or
                any(q in s.lower() for s in c.get("symptoms", []))
            )
        ]

    return results

def get_condition_by_id(condition_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve single condition by unique identifier."""
    norm_id = condition_id.lower().strip()
    for c in HEALTH_CONDITIONS:
        if c["id"] == norm_id:
            return c
    return None
