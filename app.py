"""
HydroStar — Biogas Model Calculator
Thermodynamic equilibrium model for hydrogen injection in anaerobic digestion.
"""

import math
import base64
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

# ──────────────────────────────────────────────────────────────────────────────
# CONSTANTS & BRANDING
# ──────────────────────────────────────────────────────────────────────────────

PRIMARY_GREEN   = "#a7d730"
SECONDARY_GREEN = "#499823"
DARK_BG         = "#30343c"
LIGHT_GREY      = "#8c919a"
CARD_BG         = "#3a3f49"
H2_CO2_RATIO    = 4        # Stoichiometric: CO₂ + 4H₂ → CH₄ + 2H₂O
PH_UPPER_LIMIT  = 8.2      # Safety cap — methanogen inhibition above this

# ──────────────────────────────────────────────────────────────────────────────
# FEEDSTOCK DATABASES
# ──────────────────────────────────────────────────────────────────────────────

SCENARIO1_FEEDSTOCKS = {
    "Animal slurry and manure": {
        "smp": 0.19, "ch4_baseline": 0.60, "co2_baseline": 0.40,
        "ph_baseline": 7.5, "ph_change": 0.5, "vs": 0.10,
    },
    "Energy crop": {
        "smp": 0.35, "ch4_baseline": 0.55, "co2_baseline": 0.45,
        "ph_baseline": 7.5, "ph_change": 0.5, "vs": 0.30,
    },
    "Food waste": {
        "smp": 0.45, "ch4_baseline": 0.55, "co2_baseline": 0.45,
        "ph_baseline": 7.9, "ph_change": 0.5, "vs": 0.20,
    },
    "Sewage sludge": {
        "smp": 0.26, "ch4_baseline": 0.65, "co2_baseline": 0.35,
        "ph_baseline": 7.5, "ph_change": 0.5, "vs": 0.06,
    },
}

EXTENDED_FEEDSTOCKS = {
    "Cattle slurry":           {"smp_l": 185, "ch4_pp": 0.63, "ph": 7.8, "ph_change": 0.5, "vs": 0.07},
    "Swine slurry":            {"smp_l": 250, "ch4_pp": 0.68, "ph": 7.2, "ph_change": 0.5, "vs": 0.04},
    "Poultry layers manure":   {"smp_l": 325, "ch4_pp": 0.59, "ph": 8.0, "ph_change": 0.5, "vs": 0.23},
    "Poultry broilers manure": {"smp_l": 300, "ch4_pp": 0.62, "ph": 8.3, "ph_change": 0.5, "vs": 0.45},
    "Fodder beet":             {"smp_l": 367, "ch4_pp": 0.63, "ph": 7.8, "ph_change": 0.5, "vs": 0.20},
    "Grass silage":            {"smp_l": 315, "ch4_pp": 0.55, "ph": 7.9, "ph_change": 0.5, "vs": 0.23},
    "Maize silage":            {"smp_l": 343, "ch4_pp": 0.59, "ph": 7.6, "ph_change": 0.5, "vs": 0.33},
    "Ryegrass":                {"smp_l": 393, "ch4_pp": 0.54, "ph": 7.9, "ph_change": 0.5, "vs": 0.18},
    "Wheat crop":              {"smp_l": 283, "ch4_pp": 0.53, "ph": 8.2, "ph_change": 0.5, "vs": 0.35},
}

# ──────────────────────────────────────────────────────────────────────────────
# CORE CALCULATION FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def calc_pKw(temp_c: float) -> float:
    return 0.09018 + 2729.92 / (273.15 + temp_c)


def calc_max_ph(ph_baseline: float, ph_change_allowed: float) -> float:
    return min(ph_baseline + ph_change_allowed, PH_UPPER_LIMIT)


def calc_co2_pp_after(co2_pp_baseline: float, ph_baseline: float,
                      ph_max: float, pKw: float) -> float:
    ten_neg_pKw = 10 ** (-pKw)
    ten_neg_phM = 10 ** (-ph_max)
    ten_neg_phB = 10 ** (-ph_baseline)
    numerator   = co2_pp_baseline * (ten_neg_phM ** 2) / (ten_neg_pKw + ten_neg_phM)
    denominator = (ten_neg_phB ** 2) / (ten_neg_pKw + ten_neg_phB)
    return numerator / denominator


def calc_co2_converted(biogas_daily: float, co2_pp_baseline: float,
                       exog_co2: float, co2_pp_after: float) -> float:
    raw = biogas_daily * co2_pp_baseline + exog_co2 - (biogas_daily + exog_co2) * co2_pp_after
    return max(raw, 0.0)


# ──────────────────────────────────────────────────────────────────────────────
# SCENARIO FUNCTIONS
# ──────────────────────────────────────────────────────────────────────────────

def run_scenario1_single(feedstock_key: str, temp_c: float,
                         biogas_daily: float, exog_co2: float) -> dict:
    fs = SCENARIO1_FEEDSTOCKS[feedstock_key]
    pKw = calc_pKw(temp_c)
    co2_baseline = fs["co2_baseline"]
    ph_baseline  = fs["ph_baseline"]
    ph_max       = calc_max_ph(ph_baseline, fs["ph_change"])
    co2_after    = calc_co2_pp_after(co2_baseline, ph_baseline, ph_max, pKw)
    ch4_after    = 1.0 - co2_after
    co2_converted = calc_co2_converted(biogas_daily, co2_baseline, exog_co2, co2_after)
    return {
        "feedstock": feedstock_key,
        "smp": fs["smp"],
        "ch4_baseline": fs["ch4_baseline"],
        "co2_baseline": co2_baseline,
        "ph_baseline": ph_baseline,
        "ph_change": fs["ph_change"],
        "ph_max": ph_max,
        "pKw": pKw,
        "co2_after": co2_after,
        "ch4_after": ch4_after,
        "co2_converted": co2_converted,
        "h2_max": co2_converted * H2_CO2_RATIO,
        "ch4_increase": co2_converted,
        "ch4_to_co2": ch4_after / co2_after if co2_after > 0 else float("inf"),
    }


def run_scenario1_mix(feedstock_pcts: dict, temp_c: float,
                      biogas_daily: float, exog_co2: float) -> dict | None:
    pKw  = calc_pKw(temp_c)
    keys = [k for k, v in feedstock_pcts.items() if v > 0]
    fracs = {k: feedstock_pcts[k] for k in keys}
    total_frac = sum(fracs.values())
    if total_frac == 0:
        return None
    norm = {k: v / total_frac for k, v in fracs.items()}
    y_vs  = sum(norm[k] * SCENARIO1_FEEDSTOCKS[k]["vs"] for k in keys)
    if y_vs == 0:
        return None
    n_smp = sum(norm[k] * SCENARIO1_FEEDSTOCKS[k]["vs"] * SCENARIO1_FEEDSTOCKS[k]["smp"]
                for k in keys) / y_vs
    z_co2 = sum(
        norm[k] * SCENARIO1_FEEDSTOCKS[k]["vs"] * SCENARIO1_FEEDSTOCKS[k]["smp"]
        * SCENARIO1_FEEDSTOCKS[k]["co2_baseline"] / SCENARIO1_FEEDSTOCKS[k]["ch4_baseline"]
        for k in keys
    ) / y_vs
    co2_baseline = z_co2 / (n_smp + z_co2)
    ph_baseline  = -math.log10(sum(10 ** (-SCENARIO1_FEEDSTOCKS[k]["ph_baseline"]) * norm[k] for k in keys))
    ph_change    = sum(SCENARIO1_FEEDSTOCKS[k]["ph_change"] * norm[k] for k in keys)
    ph_max       = calc_max_ph(ph_baseline, ph_change)
    co2_after    = calc_co2_pp_after(co2_baseline, ph_baseline, ph_max, pKw)
    ch4_after    = 1.0 - co2_after
    co2_converted = calc_co2_converted(biogas_daily, co2_baseline, exog_co2, co2_after)
    ch4_baseline  = 1.0 - co2_baseline
    return {
        "feedstock": "Feed mix",
        "smp": n_smp,
        "ch4_baseline": ch4_baseline,
        "co2_baseline": co2_baseline,
        "ph_baseline": ph_baseline,
        "ph_change": ph_change,
        "ph_max": ph_max,
        "pKw": pKw,
        "co2_after": co2_after,
        "ch4_after": ch4_after,
        "co2_converted": co2_converted,
        "h2_max": co2_converted * H2_CO2_RATIO,
        "ch4_increase": co2_converted,
        "ch4_to_co2": ch4_after / co2_after if co2_after > 0 else float("inf"),
    }


def run_scenario2(temp_c: float, ph_baseline: float, co2_pp_baseline: float,
                  biogas_daily: float, exog_co2: float,
                  ph_change_allowed: float = 0.5) -> dict:
    pKw           = calc_pKw(temp_c)
    ph_max        = calc_max_ph(ph_baseline, ph_change_allowed)
    co2_after     = calc_co2_pp_after(co2_pp_baseline, ph_baseline, ph_max, pKw)
    ch4_after     = 1.0 - co2_after
    co2_converted = calc_co2_converted(biogas_daily, co2_pp_baseline, exog_co2, co2_after)
    return {
        "pKw": pKw,
        "ph_change_allowed": ph_change_allowed,
        "ph_max": ph_max,
        "co2_after": co2_after,
        "ch4_after": ch4_after,
        "co2_converted": co2_converted,
        "h2_max": co2_converted * H2_CO2_RATIO,
        "ch4_increase": co2_converted,
        "ch4_to_co2": (1 - co2_after) / co2_after if co2_after > 0 else float("inf"),
    }


def calc_extended_db(temp_c: float) -> list[dict]:
    pKw  = calc_pKw(temp_c)
    rows = []
    for name, props in EXTENDED_FEEDSTOCKS.items():
        co2_pp = 1.0 - props["ch4_pp"]
        ph     = props["ph"]
        ph_max = calc_max_ph(ph, props["ph_change"])
        if ph > PH_UPPER_LIMIT:
            rows.append({
                "Feedstock": name,
                "SMP (L/kg VS)": props["smp_l"],
                "CH₄ baseline": f"{props['ch4_pp']:.0%}",
                "CO₂ baseline": f"{co2_pp:.0%}",
                "pH": ph,
                "Max pH": "—",
                "CO₂ after": "N/A",
                "CH₄ after": "N/A",
                "VS": f"{props['vs']:.0%}",
            })
            continue
        co2_after = calc_co2_pp_after(co2_pp, ph, ph_max, pKw)
        ch4_after = 1.0 - co2_after
        rows.append({
            "Feedstock": name,
            "SMP (L/kg VS)": props["smp_l"],
            "CH₄ baseline": f"{props['ch4_pp']:.0%}",
            "CO₂ baseline": f"{co2_pp:.0%}",
            "pH": ph,
            "Max pH": f"{ph_max:.1f}",
            "CO₂ after": f"{co2_after:.2%}",
            "CH₄ after": f"{ch4_after:.2%}",
            "VS": f"{props['vs']:.0%}",
        })
    return rows


# ──────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ──────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="HydroStar — Biogas Simulation Model",
    page_icon="logo.png",
    layout="wide",
    initial_sidebar_state="collapsed",
)

LOGO_PATH = Path(__file__).parent / "logo.png"
logo_b64  = base64.b64encode(LOGO_PATH.read_bytes()).decode() if LOGO_PATH.exists() else ""

# ──────────────────────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────────────────────

st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="st-"] {{
        font-family: 'Inter', sans-serif;
    }}

    /* ── Base ── */
    .stApp {{
        background-color: {DARK_BG};
        color: #e8e8e8;
    }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background-color: #272b33;
    }}
    section[data-testid="stSidebar"] .stMarkdown p,
    section[data-testid="stSidebar"] .stMarkdown li {{
        color: #c8c8c8;
        font-size: 1rem;
    }}

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
        border-bottom: 2px solid #3a3f49;
    }}
    .stTabs [data-baseweb="tab"] {{
        background-color: #3a3f49;
        color: {LIGHT_GREY};
        border-radius: 10px 10px 0 0;
        padding: 14px 30px;
        font-weight: 600;
        font-size: 1.05rem;
        border: none;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {SECONDARY_GREEN};
        color: #ffffff;
    }}
    .stTabs [data-baseweb="tab-highlight"] {{
        background-color: {PRIMARY_GREEN} !important;
    }}

    /* ── Metric cards ── */
    div[data-testid="stMetric"] {{
        background: {CARD_BG};
        border-left: 5px solid {PRIMARY_GREEN};
        border-radius: 12px;
        padding: 20px 22px;
    }}
    div[data-testid="stMetric"] label {{
        color: {LIGHT_GREY} !important;
        font-size: 0.9rem !important;
        font-weight: 500;
        letter-spacing: 0.3px;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        color: {PRIMARY_GREEN} !important;
        font-size: 2rem !important;
        font-weight: 700;
        line-height: 1.2;
    }}

    /* ── Headers ── */
    h1, h2, h3, h4 {{
        color: #f0f0f0 !important;
        font-family: 'Inter', sans-serif !important;
    }}

    /* ── Inputs ── */
    .stSelectbox label, .stNumberInput label, .stSlider label, .stRadio label {{
        color: #d8d8d8 !important;
        font-size: 1rem !important;
        font-weight: 500;
    }}
    input[type="number"] {{
        font-size: 1.05rem !important;
    }}

    /* ── Expander ── */
    details[data-testid="stExpander"] summary {{
        color: {PRIMARY_GREEN} !important;
        font-size: 1rem !important;
        font-weight: 600;
    }}
    details[data-testid="stExpander"] summary span[data-testid="stExpanderToggleIcon"] svg {{
        fill: {PRIMARY_GREEN} !important;
    }}
    /* Hide the raw arrow text that bleeds through in some Streamlit builds */
    details[data-testid="stExpander"] summary p {{
        display: inline !important;
        overflow: hidden !important;
    }}
    details[data-testid="stExpander"] summary::before {{
        content: none !important;
    }}

    /* ── Dividers ── */
    hr {{
        border-color: #4a4f59;
    }}

    /* ── Header banner ── */
    .hs-header {{
        display: flex;
        align-items: center;
        gap: 20px;
        padding: 16px 0 14px 0;
        border-bottom: 2px solid {SECONDARY_GREEN};
        margin-bottom: 24px;
    }}
    .hs-header img {{
        height: 56px;
    }}
    .hs-header .hs-title {{
        font-size: 1.9rem;
        font-weight: 800;
        color: #ffffff;
        line-height: 1.15;
    }}
    .hs-header .hs-sub {{
        font-size: 1rem;
        color: {LIGHT_GREY};
        margin-top: 3px;
    }}

    /* ── Section headers ── */
    .sec-head {{
        font-size: 0.8rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1.8px;
        color: {PRIMARY_GREEN};
        margin: 28px 0 12px 0;
        padding-bottom: 6px;
        border-bottom: 1px solid #4a4f59;
    }}

    /* ── Info / callout boxes ── */
    .callout {{
        background: {CARD_BG};
        border-radius: 10px;
        padding: 16px 20px;
        margin: 10px 0 18px 0;
        border: 1px solid #4a4f59;
        font-size: 1rem;
        color: #c8c8c8;
        line-height: 1.6;
    }}
    .callout strong {{
        color: {PRIMARY_GREEN};
    }}

    /* ── Tag badge ── */
    .badge {{
        display: inline-block;
        background: {SECONDARY_GREEN};
        color: #fff;
        border-radius: 6px;
        padding: 2px 10px;
        font-size: 0.82rem;
        font-weight: 700;
        letter-spacing: 0.5px;
        margin-right: 6px;
    }}
    .badge-grey {{
        background: #4a4f59;
        color: #c8c8c8;
    }}

    /* ── Table ── */
    .stDataFrame {{
        border-radius: 10px;
        overflow: hidden;
    }}

    /* ── Radio pills ── */
    .stRadio [role="radiogroup"] {{
        gap: 10px;
    }}

    /* ── Footer ── */
    .hs-footer {{
        text-align: center;
        color: {LIGHT_GREY};
        font-size: 0.88rem;
        padding: 16px 0 8px 0;
    }}

    /* ── Responsive tweaks ── */
    @media (max-width: 768px) {{
        .hs-header .hs-title {{ font-size: 1.4rem; }}
        div[data-testid="stMetricValue"] {{ font-size: 1.6rem !important; }}
        .stTabs [data-baseweb="tab"] {{ padding: 10px 16px; font-size: 0.9rem; }}
    }}
</style>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────────────────────

logo_html = f'<img src="data:image/png;base64,{logo_b64}" />' if logo_b64 else ""
st.markdown(f"""
<div class="hs-header">
    {logo_html}
    <div>
        <div class="hs-title">AD Simulation Model</div>
        <div class="hs-sub">Hydrogen injection optimisation &nbsp;·&nbsp; Anaerobic digestion thermodynamic model</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────────────────
# GLOBAL TEMPERATURE INPUT (top of page, always visible)
# ──────────────────────────────────────────────────────────────────────────────

with st.container():
    tcol1, tcol2, tcol3 = st.columns([1, 2, 2])
    with tcol1:
        temp_c = st.number_input(
            "Digester temperature (°C)",
            min_value=20.0, max_value=60.0, value=37.0, step=0.5,
            help=(
                "Operating temperature of the digester. Most AD systems run at 37 °C "
                "(mesophilic). This affects the water dissociation constant (pKw) used "
                "in all thermodynamic calculations. Typical range: 30–55 °C."
            ),
        )
    with tcol2:
        pKw_val = calc_pKw(temp_c)
        st.markdown(f"""
        <div class="callout" style="margin-top:28px; padding: 12px 18px;">
            <strong>pKw</strong> at {temp_c:.1f} °C &nbsp;=&nbsp; <span style="color:{PRIMARY_GREEN}; font-size:1.15rem; font-weight:700;">{pKw_val:.4f}</span>
            <br/><span style="font-size:0.88rem; color:{LIGHT_GREY};">Temperature-dependent water dissociation constant used in CO₂ equilibrium calculations</span>
        </div>
        """, unsafe_allow_html=True)
    with tcol3:
        st.markdown(f"""
        <div class="callout" style="margin-top:28px; padding: 12px 18px;">
            <strong>H₂ : CO₂ stoichiometric ratio</strong> &nbsp;=&nbsp; <span style="color:{PRIMARY_GREEN}; font-size:1.15rem; font-weight:700;">4</span>
            <br/><span style="font-size:0.88rem; color:{LIGHT_GREY};">CO₂ + 4H₂ → CH₄ + 2H₂O &nbsp;·&nbsp; 4 m³ of H₂ consumed per 1 m³ of CO₂ converted</span>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs([
    "  Feedstock-based  ",
    "  Operational data  ",
    "  Feedstock reference  ",
])


# ──────────────────────────────────────────────────────────────────────────────
# RESULTS RENDERER
# ──────────────────────────────────────────────────────────────────────────────

def render_results(res: dict):
    """Render a clean output panel for any scenario result dict."""

    if res.get("co2_converted", 0) == 0 and res.get("co2_after", 0) > res.get("co2_baseline", 0):
        st.warning(
            "No net CO₂ conversion is possible at these inputs — "
            "the equilibrium CO₂ partial pressure exceeds the available CO₂. "
            "Try increasing biogas volume, adding exogenous CO₂, or adjusting pH.",
            icon="⚠️",
        )

    # ── Key outputs ──
    st.markdown('<div class="sec-head">Results</div>', unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    k1.metric(
        "Max H₂ injection",
        f"{res['h2_max']:,.0f} m³/d",
        help=(
            "Maximum volume of hydrogen that can be injected per day (STP m³/day). "
            "This is the amount of H₂ needed to convert all available CO₂ to methane. "
            "Calculated as: CO₂ converted × 4 (stoichiometric ratio). "
            "Do not exceed this — excess H₂ would remain unconverted in the biogas."
        ),
    )
    k2.metric(
        "Max CH₄ increase",
        f"{res['ch4_increase']:,.0f} m³/d",
        help=(
            "Additional methane produced per day (STP m³/day) from H₂ injection. "
            "Equal to the volume of CO₂ converted, since the reaction produces 1 m³ CH₄ "
            "per 1 m³ CO₂. This is the potential uplift in biomethane output."
        ),
    )
    k3.metric(
        "CH₄ : CO₂ ratio (after)",
        f"{res['ch4_to_co2']:.1f}",
        help=(
            "Ratio of methane to CO₂ in the biogas at equilibrium after H₂ injection. "
            "A higher ratio means richer biomethane. Calculated as: "
            "CH₄ partial pressure ÷ CO₂ partial pressure at equilibrium."
        ),
    )

    # ── Gas composition ──
    st.markdown('<div class="sec-head">Equilibrium gas composition</div>', unsafe_allow_html=True)
    g1, g2, g3 = st.columns(3)
    g1.metric(
        "CH₄ after injection",
        f"{res['ch4_after']:.1%}",
        help=(
            "Methane fraction in the biogas at thermodynamic equilibrium after H₂ injection. "
            "This is the theoretical maximum CH₄ concentration achievable at these conditions. "
            "Real performance depends on mixing efficiency and microbial activity."
        ),
    )
    g2.metric(
        "CO₂ after injection",
        f"{res['co2_after']:.1%}",
        help=(
            "Residual CO₂ fraction in the biogas at equilibrium. As H₂ is injected, "
            "CO₂ is converted to CH₄ and this value decreases. The model calculates "
            "the new equilibrium based on the pH shift and temperature."
        ),
    )
    g3.metric(
        "CO₂ converted to CH₄",
        f"{res.get('co2_converted', 0):,.0f} m³/d",
        help=(
            "Volume of CO₂ converted to methane per day (STP m³/day). "
            "This drives both the H₂ requirement and the CH₄ increase. "
            "Includes CO₂ from the biogas plus any externally supplied CO₂."
        ),
    )

    # ── pH panel ──
    st.markdown('<div class="sec-head">Process conditions</div>', unsafe_allow_html=True)
    p1, p2, p3 = st.columns(3)
    if "ph_baseline" in res:
        p1.metric(
            "Baseline pH",
            f"{res['ph_baseline']:.2f}",
            help=(
                "The measured (or assumed) pH of the digester before H₂ injection. "
                "pH affects CO₂ solubility — higher pH means more CO₂ dissolves into "
                "the liquid phase, shifting the equilibrium."
            ),
        )
    p2.metric(
        "Max pH after injection",
        f"{res['ph_max']:.2f}",
        help=(
            "The maximum permitted pH after H₂ injection. Calculated as baseline pH + "
            f"allowed pH rise, capped at {PH_UPPER_LIMIT}. Exceeding pH {PH_UPPER_LIMIT} "
            "risks inhibiting the methanogenic microorganisms responsible for CH₄ production. "
            "The default allowed rise is 0.5 pH units."
        ),
    )
    p3.metric(
        "pKw",
        f"{res['pKw']:.4f}",
        help=(
            "Water dissociation constant at the current digester temperature. "
            "Used in the CO₂ equilibrium calculation. Higher temperature → lower pKw. "
            "Formula: 0.09018 + 2729.92 / (273.15 + T°C)"
        ),
    )

    # ── Donut chart ──
    fig = go.Figure(data=[go.Pie(
        labels=["CH₄", "CO₂"],
        values=[res["ch4_after"], res["co2_after"]],
        hole=0.60,
        marker_colors=[PRIMARY_GREEN, "#4a4f59"],
        textinfo="label+percent",
        textfont_size=15,
        textfont_color="#ffffff",
        hovertemplate="%{label}: %{value:.2%}<extra></extra>",
    )])
    fig.update_layout(
        title_text="Biogas composition at equilibrium",
        title_font_size=16,
        title_font_color="#e0e0e0",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#c8c8c8",
        height=340,
        margin=dict(t=50, b=20, l=20, r=20),
        legend=dict(font_color="#c8c8c8", font_size=14),
        annotations=[dict(
            text=f"<b>{res['ch4_after']:.1%}</b><br>CH₄",
            x=0.5, y=0.5,
            font_size=20,
            font_color=PRIMARY_GREEN,
            showarrow=False,
        )],
    )
    st.plotly_chart(fig, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 1 — FEEDSTOCK-BASED (SCENARIO 1)
# ──────────────────────────────────────────────────────────────────────────────

with tab1:
    st.markdown("""
    <div class="callout">
        <strong>Feedstock-based mode</strong> — Estimate hydrogen injection limits from your feedstock type.
        Best used for <em>new or planned digesters</em> where you know the feedstock but don't yet have
        operational measurements. For existing plants, use the <strong>Operational data</strong> tab for more accurate results.
    </div>
    """, unsafe_allow_html=True)

    mode = st.radio(
        "Input mode",
        ["Single feedstock", "Feedstock mix (two types)"],
        horizontal=True,
        help=(
            "Choose 'Single feedstock' if your digester uses one type of material. "
            "Choose 'Feedstock mix' to blend two categories and see the combined result."
        ),
    )

    st.markdown('<div class="sec-head">Inputs</div>', unsafe_allow_html=True)

    if mode == "Single feedstock":
        col_fs, col_bg, col_ex = st.columns([2, 1, 1])
        with col_fs:
            fs_choice = st.selectbox(
                "Feedstock type",
                list(SCENARIO1_FEEDSTOCKS.keys()),
                index=1,
                help=(
                    "Select the primary feedstock category for your digester. "
                    "Each feedstock has different methane yield, CO₂ content, pH, and "
                    "volatile solids — all sourced from standard AD reference data. "
                    "See the 'Feedstock reference' tab for full details."
                ),
            )
        with col_bg:
            biogas_s1 = st.number_input(
                "Daily biogas production (m³/d)",
                min_value=0.0, value=1000.0, step=50.0,
                key="bg_s1_single",
                help=(
                    "Total volume of biogas produced by your digester per day, "
                    "measured at standard conditions (0 °C, 1 atm). This is the "
                    "starting point for calculating how much CO₂ is available to convert."
                ),
            )
        with col_ex:
            exog_s1 = st.number_input(
                "External CO₂ supply (m³/d)",
                min_value=0.0, value=0.0, step=50.0,
                key="ex_s1_single",
                help=(
                    "Additional CO₂ from an external source (e.g. captured from flue gas "
                    "or another process), injected alongside the H₂. Set to 0 if no "
                    "external CO₂ is available. More CO₂ means more H₂ can be converted "
                    "and more CH₄ can be produced."
                ),
            )

        fs_data = SCENARIO1_FEEDSTOCKS[fs_choice]
        with st.expander("View feedstock properties"):
            pc1, pc2, pc3, pc4, pc5 = st.columns(5)
            pc1.metric(
                "Specific methane yield",
                f"{fs_data['smp']} m³/kg VS",
                help="Specific methane production (SMP) — volume of CH₄ produced per kg of volatile solids. Higher values mean more energy-dense feedstock.",
            )
            pc2.metric(
                "CH₄ baseline",
                f"{fs_data['ch4_baseline']:.0%}",
                help="Methane fraction in the biogas before H₂ injection. This is the starting CH₄ concentration.",
            )
            pc3.metric(
                "CO₂ baseline",
                f"{fs_data['co2_baseline']:.0%}",
                help="CO₂ fraction in the biogas before H₂ injection. This CO₂ is the feedstock for the biomethanisation reaction.",
            )
            pc4.metric(
                "Digester pH",
                f"{fs_data['ph_baseline']}",
                help="Typical operating pH for this feedstock. pH affects CO₂ solubility and methanogen activity.",
            )
            pc5.metric(
                "Volatile solids",
                f"{fs_data['vs']:.0%}",
                help="Volatile solids (VS) fraction of the feedstock — the biodegradable portion that produces biogas. Used in blending calculations.",
            )

        res = run_scenario1_single(fs_choice, temp_c, biogas_s1, exog_s1)
        render_results(res)

    else:
        st.markdown("""
        <div class="callout" style="font-size:0.95rem;">
            Select two feedstock types and set their proportions. The model blends pH, volatile solids,
            and gas composition using weighted averages to calculate a combined equilibrium result.
        </div>
        """, unsafe_allow_html=True)

        fs_names = list(SCENARIO1_FEEDSTOCKS.keys())
        col_a, col_b = st.columns(2)
        with col_a:
            fs1  = st.selectbox("Feedstock A", fs_names, index=0, key="fs_mix_a",
                                help="First feedstock type in the blend.")
            pct1 = st.slider(
                "Proportion A", 0.0, 1.0, 0.5, 0.05, key="pct_mix_a",
                help="Fraction of feedstock A in the mix (0 = none, 1 = 100%). The two fractions are normalised automatically.",
            )
        with col_b:
            fs2  = st.selectbox("Feedstock B", fs_names, index=1, key="fs_mix_b",
                                help="Second feedstock type in the blend.")
            pct2 = st.slider(
                "Proportion B", 0.0, 1.0, 0.5, 0.05, key="pct_mix_b",
                help="Fraction of feedstock B in the mix (0 = none, 1 = 100%). The two fractions are normalised automatically.",
            )

        col_bg2, col_ex2 = st.columns(2)
        with col_bg2:
            biogas_mix = st.number_input(
                "Daily biogas production (m³/d)",
                min_value=0.0, value=1000.0, step=50.0,
                key="bg_s1_mix",
                help="Total biogas volume per day from the digester at standard conditions.",
            )
        with col_ex2:
            exog_mix = st.number_input(
                "External CO₂ supply (m³/d)",
                min_value=0.0, value=200.0, step=50.0,
                key="ex_s1_mix",
                help="Additional CO₂ from an external source. Set to 0 if not applicable.",
            )

        mix_pcts = {fs1: pct1 + pct2 if fs1 == fs2 else pct1, fs2: pct2} if fs1 != fs2 else {fs1: pct1 + pct2}
        res_mix = run_scenario1_mix(mix_pcts, temp_c, biogas_mix, exog_mix)
        if res_mix:
            render_results(res_mix)
        else:
            st.warning("Set at least one feedstock proportion above zero.", icon="⚠️")


# ──────────────────────────────────────────────────────────────────────────────
# TAB 2 — OPERATIONAL DATA (SCENARIO 2)
# ──────────────────────────────────────────────────────────────────────────────

with tab2:
    st.markdown("""
    <div class="callout">
        <strong>Operational data mode</strong> — Use measured parameters from your existing digester.
        This is the <strong>most reliable approach</strong> because it uses actual pH, CO₂ content,
        and flow rates rather than feedstock assumptions. Ideal for optimising H₂ injection on a running plant.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sec-head">Inputs</div>', unsafe_allow_html=True)

    row1_c1, row1_c2, row1_c3 = st.columns(3)
    row2_c1, row2_c2, _ = st.columns(3)

    with row1_c1:
        ph_s2 = st.number_input(
            "Digester pH",
            min_value=5.0, max_value=9.0, value=7.5, step=0.1,
            help=(
                "Measured pH of the digester liquid before hydrogen injection. "
                "Typical AD digesters operate between pH 7.0 and 8.0. "
                "pH directly affects CO₂ solubility and the activity of methanogens. "
                "Read this from your online pH monitor or lab sample."
            ),
        )
    with row1_c2:
        co2_pp_s2 = st.number_input(
            "CO₂ in biogas (fraction 0–1)",
            min_value=0.01, max_value=0.99, value=0.40, step=0.01,
            format="%.2f",
            help=(
                "The CO₂ fraction in your current biogas, measured before H₂ injection. "
                "Enter as a decimal: 0.40 means 40% CO₂. Typical biogas is 35–45% CO₂. "
                "Read this from your biogas analyser. This is the key driver of how much "
                "H₂ you can inject and how much extra CH₄ you can produce."
            ),
        )
    with row1_c3:
        ph_change_s2 = st.number_input(
            "Permitted pH rise",
            min_value=0.0, max_value=2.0, value=0.5, step=0.1,
            help=(
                "The maximum pH increase you are willing to allow during H₂ injection. "
                "The default of 0.5 is a conservative safe limit. As CO₂ is consumed by "
                "the biomethanisation reaction, dissolved carbonic acid decreases and pH rises. "
                f"The model caps the maximum pH at {PH_UPPER_LIMIT} regardless of this setting."
            ),
        )
    with row2_c1:
        biogas_s2 = st.number_input(
            "Daily biogas production (m³/d)",
            min_value=0.0, value=1000.0, step=50.0,
            key="bg_s2",
            help=(
                "Total biogas produced per day at standard conditions (0 °C, 1 atm). "
                "Check your flow meter. This determines the total CO₂ available for conversion."
            ),
        )
    with row2_c2:
        exog_s2 = st.number_input(
            "External CO₂ supply (m³/d)",
            min_value=0.0, value=100.0, step=50.0,
            key="ex_s2",
            help=(
                "Extra CO₂ fed in from an external source (e.g. captured CO₂ from "
                "combined heat and power exhaust or another industrial process). "
                "This increases the amount of H₂ that can be usefully injected. "
                "Set to 0 if no external CO₂ is available."
            ),
        )

    res2 = run_scenario2(temp_c, ph_s2, co2_pp_s2, biogas_s2, exog_s2, ph_change_s2)
    render_results({**res2, "ph_baseline": ph_s2, "co2_baseline": co2_pp_s2})

    # ── Sensitivity chart ──
    st.markdown('<div class="sec-head">Sensitivity: how outputs change with CO₂ content</div>',
                unsafe_allow_html=True)
    st.markdown(
        '<p style="color:#a0a0a0; font-size:0.95rem; margin-bottom:12px;">'
        'Shows how H₂ injection capacity and CH₄ gain change as the CO₂ fraction in your biogas varies '
        'from 20% to 60% — all other inputs held constant. The orange marker shows your current value.'
        '</p>',
        unsafe_allow_html=True,
    )

    co2_range = [round(x * 0.01, 2) for x in range(20, 61)]
    h2_vals, ch4_vals = [], []
    for co2_val in co2_range:
        r = run_scenario2(temp_c, ph_s2, co2_val, biogas_s2, exog_s2, ph_change_s2)
        h2_vals.append(r["h2_max"])
        ch4_vals.append(r["ch4_increase"])

    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=co2_range, y=h2_vals,
        name="Max H₂ injection (m³/d)",
        line=dict(color=PRIMARY_GREEN, width=3),
        hovertemplate="CO₂: %{x:.0%}<br>H₂: %{y:,.0f} m³/d<extra></extra>",
    ))
    fig2.add_trace(go.Scatter(
        x=co2_range, y=ch4_vals,
        name="Max CH₄ increase (m³/d)",
        line=dict(color=SECONDARY_GREEN, width=3),
        hovertemplate="CO₂: %{x:.0%}<br>CH₄ gain: %{y:,.0f} m³/d<extra></extra>",
    ))
    fig2.update_layout(
        xaxis_title="CO₂ fraction in biogas",
        yaxis_title="Volume (STP m³/day)",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#c8c8c8",
        font_size=13,
        height=400,
        margin=dict(t=30, b=60, l=20, r=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
            font_color="#c8c8c8", font_size=13,
        ),
        xaxis=dict(
            gridcolor="#3a3f49", zeroline=False,
            tickformat=".0%",
        ),
        yaxis=dict(gridcolor="#3a3f49", zeroline=False),
    )
    fig2.add_vline(
        x=co2_pp_s2, line_dash="dot", line_color="#ff8c00", line_width=2,
        annotation_text=f"Your value: {co2_pp_s2:.0%}",
        annotation_font_color="#ff8c00",
        annotation_font_size=13,
    )
    st.plotly_chart(fig2, use_container_width=True)


# ──────────────────────────────────────────────────────────────────────────────
# TAB 3 — FEEDSTOCK REFERENCE DATABASE
# ──────────────────────────────────────────────────────────────────────────────

with tab3:
    st.markdown("""
    <div class="callout">
        <strong>Feedstock reference data</strong> — Thermodynamic equilibrium properties calculated
        at the current digester temperature. Feedstocks where the baseline pH already exceeds
        the safety cap of 8.2 (e.g. poultry broilers manure) cannot be assessed for biomethanisation
        — their pH would rise further and risk inhibiting methanogens.
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sec-head">Extended feedstock database</div>', unsafe_allow_html=True)
    db_rows = calc_extended_db(temp_c)
    st.dataframe(db_rows, use_container_width=True, hide_index=True)

    st.markdown('<div class="sec-head">Simplified categories (used in Feedstock-based tab)</div>',
                unsafe_allow_html=True)
    pKw = calc_pKw(temp_c)
    simple_rows = []
    for name, fs in SCENARIO1_FEEDSTOCKS.items():
        ph_max    = calc_max_ph(fs["ph_baseline"], fs["ph_change"])
        co2_after = calc_co2_pp_after(fs["co2_baseline"], fs["ph_baseline"], ph_max, pKw)
        ch4_after = 1.0 - co2_after
        simple_rows.append({
            "Category": name,
            "SMP (m³/kg VS)": fs["smp"],
            "CH₄ baseline": f"{fs['ch4_baseline']:.0%}",
            "CO₂ baseline": f"{fs['co2_baseline']:.0%}",
            "pH": fs["ph_baseline"],
            "Max pH": f"{ph_max:.1f}",
            "CO₂ after": f"{co2_after:.2%}",
            "CH₄ after": f"{ch4_after:.2%}",
            "VS": f"{fs['vs']:.0%}",
        })
    st.dataframe(simple_rows, use_container_width=True, hide_index=True)

    with st.expander("Notes on feedstock data"):
        st.markdown(f"""
**Food waste — volatile solids (20%):**
Applies to source-segregated household food waste only, not commercial food waste which varies significantly.

**Sewage sludge — volatile solids (6%):**
Highly dependent on the dewatering process used. Sites with more advanced dewatering may see higher VS.

**Poultry broilers manure (pH 8.3):**
Baseline pH already exceeds the {PH_UPPER_LIMIT} safety cap. No biomethanisation calculation is possible
because pH would rise further, inhibiting the methanogens. Shown as N/A in the table.

**pH upper limit ({PH_UPPER_LIMIT}):**
Above this pH, methanogenic microorganisms are inhibited and process stability is compromised.
Both the allowed pH rise (default 0.5) and this hard cap protect against over-alkalinity.

**H₂ : CO₂ ratio (4):**
Based on stoichiometry of CO₂ + 4H₂ → CH₄ + 2H₂O. In practice, mass-transfer limitations
may mean slightly more H₂ is needed to achieve the same conversion. This model gives the theoretical minimum.
""")


# ──────────────────────────────────────────────────────────────────────────────
# FOOTER
# ──────────────────────────────────────────────────────────────────────────────

st.markdown("---")
st.markdown(
    f'<div class="hs-footer">'
    f'© HydroStar Europe Ltd. &nbsp;·&nbsp; '
    f'Equilibrium model only — does not include kinetics or mass-transfer effects'
    f'</div>',
    unsafe_allow_html=True,
)
