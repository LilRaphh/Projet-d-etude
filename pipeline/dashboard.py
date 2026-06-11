# =============================================================
#  pipeline/dashboard.py — Interface Streamlit SmartWear Pipeline
#
#  Lancer :
#    cd /chemin/projet && .venv/bin/streamlit run pipeline/dashboard.py
# =============================================================
from __future__ import annotations
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ── Chemins ────────────────────────────────────────────────────────
PIPELINE_DIR = Path(__file__).parent
PROJECT_ROOT = PIPELINE_DIR.parent
OUTPUT_DIR   = PIPELINE_DIR / "output"
LOG_DIR      = PIPELINE_DIR / "logs"
DB_FILE      = OUTPUT_DIR / "SmartWear_DB.json"
STATS_FILE   = OUTPUT_DIR / "stats.json"
VENV_PYTHON  = str(PROJECT_ROOT / ".venv" / "bin" / "python")

ALL_SCRAPERS = [
    "mango", "lecoqsportif", "tacchini", "kappa", "lotto",
    "apc", "balzac", "maisonlabiche",
    "rouje", "cabaia", "bonnegueule", "merci", "isabelmarant", "amiparis",
    "stussy", "karhu", "fillingpieces", "palace",
    "nike", "jules", "gymshark", "asos",
]

# ── Config page ────────────────────────────────────────────────────
st.set_page_config(
    page_title="SmartWear Pipeline",
    page_icon="👔",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    /* Métriques : fond semi-transparent neutre, compatible light et dark */
    [data-testid="metric-container"] {
        background: rgba(99, 102, 241, 0.10);
        border: 1px solid rgba(99, 102, 241, 0.25);
        border-radius: 10px;
        padding: 16px 20px;
    }
    [data-testid="stMetricValue"] { font-size: 2rem !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { opacity: 0.7; font-size: 0.82rem; }
    code { font-size: 12px !important; }
</style>
""", unsafe_allow_html=True)

# Palette commune pour les graphiques
PALETTE   = ["#6366f1","#06b6d4","#10b981","#f59e0b","#ef4444",
             "#8b5cf6","#ec4899","#14b8a6","#f97316","#84cc16"]
CHART_BG  = "rgba(0,0,0,0)"   # fond transparent → suit le thème Streamlit
GRID_COL  = "rgba(150,150,150,0.15)"

def _layout(fig, title="", height=None):
    """Applique le style commun à un graphique Plotly."""
    kw = dict(
        title_text=title,
        paper_bgcolor=CHART_BG,
        plot_bgcolor=CHART_BG,
        font_color="#e2e8f0",
        title_font_size=15,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis=dict(gridcolor=GRID_COL, zerolinecolor=GRID_COL),
        yaxis=dict(gridcolor=GRID_COL, zerolinecolor=GRID_COL),
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )
    if height:
        kw["height"] = height
    fig.update_layout(**kw)
    return fig

# ── Session state ──────────────────────────────────────────────────
for key, default in [("pid", None), ("run_log", None),
                     ("audit_stats", None), ("check_anomalies", None)]:
    if key not in st.session_state:
        st.session_state[key] = default


def is_running(pid) -> bool:
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


@st.cache_data(ttl=30)
def load_db() -> list:
    if not DB_FILE.exists():
        return []
    with open(DB_FILE, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(ttl=30)
def load_stats() -> dict:
    if not STATS_FILE.exists():
        return {}
    with open(STATS_FILE, encoding="utf-8") as f:
        return json.load(f)


def get_log_files() -> list:
    return sorted(LOG_DIR.glob("pipeline_*.jsonl"), reverse=True)


def parse_run_progress(log_file: Path) -> dict:
    """
    Parse un fichier de log JSONL et extrait la progression page par page.
    Retourne: pages terminées, page courante, produits, erreurs, timestamps.
    """
    import re as _re
    from datetime import timezone

    pages: list = []
    current: dict | None = None
    total_errors = 0
    run_start_ts: str | None = None
    scraper_name: str | None = None

    for line in read_log_lines(log_file, last_n=100_000):
        msg   = line.get("msg", "")
        ts    = line.get("ts", "")
        level = line.get("level", "INFO")

        # Démarrage du run
        m = _re.search(r"Lancement\s*:\s*(\S+)", msg)
        if m:
            scraper_name  = m.group(1)
            run_start_ts  = ts

        # Nouvelle page : "[ASOS] Adulte/Homme/Vêtement — chemises"
        m = _re.search(r"\[\w+\]\s+\w+/\w+/\w+\s+[—–]\s+(.+)", msg)
        if m:
            if current is not None:
                pages.append(current)
            current = {
                "label":    m.group(1).strip(),
                "urls":     0,
                "products": 0,
                "errors":   0,
                "start_ts": ts,
                "end_ts":   ts,
                "done":     False,
            }

        # Nombre d'URLs trouvées
        m = _re.search(r"(\d+)\s+URLs?\s+trouv", msg)
        if m and current is not None:
            current["urls"] = int(m.group(1))

        # Produit OK
        if "✓" in msg and current is not None:
            current["products"] += 1
            current["end_ts"]    = ts

        # Erreur sur un produit
        if level == "WARNING" and "Erreur sur" in msg and current is not None:
            current["errors"] += 1
            total_errors       += 1

        # Pause entre pages (signe que la page précédente est finie)
        if "Total" in msg and scraper_name and scraper_name.lower() in msg.lower():
            if current is not None:
                current["done"] = True
                pages.append(current)
                current = None

    # La page en cours n'est pas encore dans pages
    return {
        "scraper":        scraper_name or "?",
        "run_start":      run_start_ts,
        "pages_done":     len(pages),
        "pages_total":    48,   # ASOS : 15 catégories + 33 marques
        "pages":          pages,
        "current_page":   current,
        "total_products": sum(p["products"] for p in pages) + (current["products"] if current else 0),
        "total_errors":   total_errors,
        "last_ts":        (current or (pages[-1] if pages else {})).get("end_ts", ""),
    }


def read_log_lines(log_file: Path, last_n: int = 300) -> list[dict]:
    lines = []
    try:
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        lines.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return lines[-last_n:]


# ── Données globales (utilisées par plusieurs pages) ───────────────
import re as _re

SCRAPERS_META = {
    "mango":         {"label": "Mango",          "brand": "Mango",            "tech": "requests"},
    "lecoqsportif":  {"label": "Le Coq Sportif", "brand": "Le Coq Sportif",   "tech": "requests"},
    "tacchini":      {"label": "Tacchini",        "brand": "Sergio Tacchini",  "tech": "requests"},
    "kappa":         {"label": "Kappa",           "brand": "Kappa",            "tech": "requests"},
    "lotto":         {"label": "Lotto",           "brand": "Lotto",            "tech": "requests"},
    "apc":           {"label": "A.P.C.",          "brand": "A.P.C.",           "tech": "requests"},
    "balzac":        {"label": "Balzac Paris",    "brand": "Balzac Paris",     "tech": "requests"},
    "maisonlabiche": {"label": "Maison Labiche",  "brand": "Maison Labiche",   "tech": "requests"},
    "rouje":         {"label": "Rouje",           "brand": "Rouje",            "tech": "requests"},
    "cabaia":        {"label": "Cabaïa",          "brand": "Cabaïa",           "tech": "requests"},
    "bonnegueule":   {"label": "BonneGueule",     "brand": "BonneGueule",      "tech": "requests"},
    "merci":         {"label": "Merci",           "brand": "Merci",            "tech": "requests"},
    "isabelmarant":  {"label": "Isabel Marant",   "brand": "Isabel Marant",    "tech": "requests"},
    "amiparis":      {"label": "AMI Paris",       "brand": "AMI Paris",        "tech": "requests"},
    "stussy":        {"label": "Stüssy",          "brand": "Stüssy",           "tech": "requests"},
    "karhu":         {"label": "Karhu",           "brand": "Karhu",            "tech": "requests"},
    "fillingpieces": {"label": "Filling Pieces",  "brand": "Filling Pieces",   "tech": "requests"},
    "palace":        {"label": "Palace",          "brand": "Palace",           "tech": "requests"},
    "nike":          {"label": "Nike",            "brand": "Nike",             "tech": "playwright"},
    "jules":         {"label": "Jules",           "brand": "Jules",            "tech": "playwright"},
    "gymshark":      {"label": "Gymshark",        "brand": "Gymshark",         "tech": "playwright"},
    "asos":          {"label": "ASOS",            "brand": "ASOS",             "tech": "playwright"},
}


@st.cache_data(ttl=60)
def scraper_stats_from_logs() -> dict:
    stats: dict = {}
    for log_file in get_log_files():
        lines = read_log_lines(log_file, last_n=5000)
        current = None
        for line in lines:
            msg = line.get("msg", "")
            ts  = line.get("ts", "")[:10]
            lvl = line.get("level", "INFO")
            m   = _re.search(r"Lancement\s*:\s*(\S+)", msg)
            if m:
                current = m.group(1).upper()
            if current:
                m_ok = _re.search(r"(\d+)\s+produits", msg)
                if m_ok and ("terminé" in msg.lower() or "total" in msg.lower()):
                    stats[current] = {"date": ts, "count": int(m_ok.group(1)), "status": "ok"}
                    current = None
                elif lvl == "ERROR":
                    stats.setdefault(current, {}).update({"date": ts, "status": "error"})
    return stats


@st.cache_data(ttl=60)
def products_by_brand() -> dict:
    out: dict = {}
    for p in load_db():
        b = p.get("brand_source") or "?"
        out[b] = out.get(b, 0) + 1
    return out


log_stats = scraper_stats_from_logs()
brand_cnt = products_by_brand()


# ── Sidebar ────────────────────────────────────────────────────────
st.sidebar.title("👔 SmartWear")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigation",
    ["📊 Dashboard", "🔄 Pipeline", "🚀 Lancer", "📋 Logs", "🗄️ Produits", "🔬 Qualité"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
running = is_running(st.session_state.pid)
if running:
    st.sidebar.success(f"🟢 Pipeline actif (PID {st.session_state.pid})")
    if st.sidebar.button("⏹ Arrêter le pipeline"):
        try:
            os.kill(st.session_state.pid, 15)
        except Exception:
            pass
        st.session_state.pid = None
        st.rerun()
else:
    st.sidebar.info("⚪ Pipeline inactif")

products_count = len(load_db())
st.sidebar.markdown(f"**Base :** {products_count:,} produits")


# ══════════════════════════════════════════════════════════════════
#  PAGE : DASHBOARD
# ══════════════════════════════════════════════════════════════════
if page == "📊 Dashboard":
    st.title("📊 Tableau de bord")

    products = load_db()
    if not products:
        st.warning("Base vide — lance un scraper d'abord.")
        st.stop()

    df = pd.DataFrame(products)
    prices = df["price_value"].dropna()
    SEX_COLORS = {"Homme": "#6366f1", "Femme": "#ec4899",
                  "Mixte": "#06b6d4", "Fille": "#f59e0b", "Garçon": "#10b981"}

    # ── KPIs ──────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6, c7 = st.columns(7)
    c1.metric("Total produits",   f"{len(products):,}")
    c2.metric("Marques",          df["brand_source"].nunique())
    c3.metric("Prix moyen",       f"{prices.mean():.1f} €"   if len(prices) else "—")
    c4.metric("Prix médian",      f"{prices.median():.1f} €" if len(prices) else "—")
    c5.metric("Avec image",       f"{df['image'].notna().sum():,}")
    c6.metric("Avec rating",      f"{df['rating'].notna().sum():,}")
    rated = df[df["rating"].notna()]["rating"]
    c7.metric("Note moyenne",     f"{rated.mean():.2f} ⭐"   if len(rated) else "—")

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(
        ["🏷️ Vue globale", "💰 Prix & Marques", "🗂️ Catalogue", "⭐ Top produits"]
    )

    # ══ TAB 1 : Vue globale ════════════════════════════════════════
    with tab1:
        col_l, col_r = st.columns(2)

        with col_l:
            by_brand = df["brand_source"].value_counts().head(20).reset_index()
            by_brand.columns = ["Marque", "Produits"]
            fig = px.bar(
                by_brand, x="Produits", y="Marque", orientation="h",
                color="Produits",
                color_continuous_scale=[[0, "#312e81"], [0.5, "#6366f1"], [1, "#06b6d4"]],
            )
            fig.update_layout(yaxis={"categoryorder": "total ascending"},
                              coloraxis_showscale=False)
            _layout(fig, "Top 20 marques", height=540)
            st.plotly_chart(fig, use_container_width=True)

        with col_r:
            by_sex = df["sexe"].value_counts().reset_index()
            by_sex.columns = ["Sexe", "Nb"]
            fig2 = px.pie(
                by_sex, values="Nb", names="Sexe", hole=0.45,
                color="Sexe", color_discrete_map=SEX_COLORS,
            )
            fig2.update_traces(textposition="outside", textinfo="percent+label",
                               marker=dict(line=dict(color="#0f172a", width=2)))
            _layout(fig2, "Répartition par sexe")
            st.plotly_chart(fig2, use_container_width=True)

            by_style = df["style"].value_counts().head(12).reset_index()
            by_style.columns = ["Style", "Nb"]
            fig3 = px.bar(by_style, x="Style", y="Nb",
                          color_discrete_sequence=["#10b981"])
            _layout(fig3, "Top 12 styles")
            st.plotly_chart(fig3, use_container_width=True)

        # Répartition type × sexe côte à côte
        col_a, col_b = st.columns(2)
        with col_a:
            by_type = df["type"].value_counts().reset_index()
            by_type.columns = ["Type", "Nb"]
            fig_t = px.pie(by_type, values="Nb", names="Type", hole=0.4,
                           color_discrete_sequence=["#6366f1", "#06b6d4", "#10b981"])
            fig_t.update_traces(textinfo="percent+label",
                                marker=dict(line=dict(color="#0f172a", width=2)))
            _layout(fig_t, "Vêtements vs Chaussures")
            st.plotly_chart(fig_t, use_container_width=True)

        with col_b:
            by_cat = df["categorie"].value_counts().reset_index()
            by_cat.columns = ["Catégorie", "Nb"]
            fig_c = px.bar(by_cat, x="Catégorie", y="Nb",
                           color="Nb",
                           color_continuous_scale=[[0,"#312e81"],[1,"#06b6d4"]])
            fig_c.update_layout(coloraxis_showscale=False)
            _layout(fig_c, "Répartition par catégorie")
            st.plotly_chart(fig_c, use_container_width=True)

    # ══ TAB 2 : Prix & Marques ═════════════════════════════════════
    with tab2:
        # Distribution des prix
        df_price = df[df["price_value"].notna() & (df["price_value"] < 500)]
        fig_h = px.histogram(
            df_price, x="price_value", nbins=60,
            labels={"price_value": "Prix (€)"},
            color_discrete_sequence=["#6366f1"], opacity=0.85,
        )
        fig_h.update_traces(marker_line_color="#312e81", marker_line_width=0.5)
        _layout(fig_h, "Distribution des prix (< 500 €)")
        st.plotly_chart(fig_h, use_container_width=True)

        col_l2, col_r2 = st.columns(2)

        with col_l2:
            # Prix moyen par marque
            avg_p = (
                df[df["price_value"].notna()]
                .groupby("brand_source")["price_value"]
                .mean().sort_values(ascending=False).head(20).reset_index()
            )
            avg_p.columns = ["Marque", "Prix moyen (€)"]
            fig4 = px.bar(
                avg_p, x="Marque", y="Prix moyen (€)",
                color="Prix moyen (€)",
                color_continuous_scale=[[0,"#f59e0b"],[0.5,"#ef4444"],[1,"#7c3aed"]],
            )
            fig4.update_layout(coloraxis_showscale=False)
            _layout(fig4, "Prix moyen par marque (top 20)")
            st.plotly_chart(fig4, use_container_width=True)

        with col_r2:
            # Box plot prix par catégorie
            df_box = df[df["price_value"].notna() & (df["price_value"] < 500)
                        & df["categorie"].notna()]
            fig_box = px.box(
                df_box, x="categorie", y="price_value",
                color="categorie", color_discrete_sequence=PALETTE,
                labels={"price_value": "Prix (€)", "categorie": "Catégorie"},
            )
            fig_box.update_layout(showlegend=False)
            _layout(fig_box, "Distribution des prix par catégorie")
            st.plotly_chart(fig_box, use_container_width=True)

        # Prix moyen vs médian par marque (top 15)
        pm = (
            df[df["price_value"].notna()]
            .groupby("brand_source")["price_value"]
            .agg(moyenne="mean", mediane="median")
            .sort_values("moyenne", ascending=False).head(15).reset_index()
        )
        fig_mm = px.bar(
            pm.melt(id_vars="brand_source", var_name="Mesure", value_name="Prix (€)"),
            x="brand_source", y="Prix (€)", color="Mesure", barmode="group",
            color_discrete_map={"moyenne": "#6366f1", "mediane": "#06b6d4"},
            labels={"brand_source": "Marque"},
        )
        _layout(fig_mm, "Prix moyen vs médian par marque (top 15)")
        st.plotly_chart(fig_mm, use_container_width=True)

        # Fourchettes de prix
        buckets = {"< 20€": 0, "20–50€": 0, "50–100€": 0,
                   "100–200€": 0, "> 200€": 0}
        for v in prices:
            if v < 20:    buckets["< 20€"]    += 1
            elif v < 50:  buckets["20–50€"]   += 1
            elif v < 100: buckets["50–100€"]  += 1
            elif v < 200: buckets["100–200€"] += 1
            else:         buckets["> 200€"]   += 1
        df_bk = pd.DataFrame(list(buckets.items()), columns=["Fourchette", "Nb"])
        fig_bk = px.bar(df_bk, x="Fourchette", y="Nb",
                        color="Nb",
                        color_continuous_scale=[[0,"#10b981"],[0.5,"#f59e0b"],[1,"#ef4444"]])
        fig_bk.update_layout(coloraxis_showscale=False)
        _layout(fig_bk, "Produits par fourchette de prix")
        st.plotly_chart(fig_bk, use_container_width=True)

    # ══ TAB 3 : Catalogue ══════════════════════════════════════════
    with tab3:
        # Heatmap marque × catégorie
        top_brands = df["brand_source"].value_counts().head(18).index.tolist()
        df_heat = df[df["brand_source"].isin(top_brands) & df["categorie"].notna()]
        pivot = df_heat.pivot_table(
            index="brand_source", columns="categorie",
            values="name", aggfunc="count", fill_value=0,
        )
        import plotly.graph_objects as go
        fig_hm = go.Figure(data=go.Heatmap(
            z=pivot.values,
            x=pivot.columns.tolist(),
            y=pivot.index.tolist(),
            colorscale=[[0,"#1e1b4b"],[0.3,"#4338ca"],[0.7,"#6366f1"],[1,"#06b6d4"]],
            text=pivot.values,
            texttemplate="%{text}",
            hoverongaps=False,
        ))
        _layout(fig_hm, "Nombre de produits par marque × catégorie", height=500)
        fig_hm.update_layout(xaxis_title="Catégorie", yaxis_title="Marque")
        st.plotly_chart(fig_hm, use_container_width=True)

        col_c1, col_c2 = st.columns(2)

        with col_c1:
            # Top 20 couleurs
            colors_raw = df["color"].dropna().str.strip().str.lower()
            top_colors = colors_raw.value_counts().head(20).reset_index()
            top_colors.columns = ["Couleur", "Nb"]
            fig_col = px.bar(
                top_colors, x="Nb", y="Couleur", orientation="h",
                color="Nb",
                color_continuous_scale=[[0,"#312e81"],[1,"#ec4899"]],
            )
            fig_col.update_layout(yaxis={"categoryorder": "total ascending"},
                                  coloraxis_showscale=False)
            _layout(fig_col, "Top 20 couleurs", height=500)
            st.plotly_chart(fig_col, use_container_width=True)

        with col_c2:
            # Distribution des tailles (vêtements)
            tailles_all = []
            for t in df["taille"].dropna():
                if isinstance(t, list):
                    tailles_all.extend(t)
                elif isinstance(t, str) and t.startswith("["):
                    try:
                        tailles_all.extend(json.loads(t))
                    except Exception:
                        pass
            if tailles_all:
                df_taille = pd.Series(tailles_all).value_counts().reset_index()
                df_taille.columns = ["Taille", "Nb"]
                ORDER = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
                df_taille["order"] = df_taille["Taille"].map(
                    lambda x: ORDER.index(x) if x in ORDER else 99
                )
                df_taille = df_taille.sort_values("order")
                fig_sz = px.bar(df_taille, x="Taille", y="Nb",
                                color="Nb",
                                color_continuous_scale=[[0,"#4338ca"],[1,"#06b6d4"]])
                fig_sz.update_layout(coloraxis_showscale=False)
                _layout(fig_sz, "Distribution des tailles (vêtements)")
                st.plotly_chart(fig_sz, use_container_width=True)
            else:
                st.info("Aucune donnée de taille disponible.")

        # Marque × sexe (stacked bar)
        df_ms = (
            df[df["brand_source"].isin(top_brands) & df["sexe"].notna()]
            .groupby(["brand_source", "sexe"])
            .size().reset_index(name="Nb")
        )
        fig_ms = px.bar(
            df_ms, x="brand_source", y="Nb", color="sexe",
            barmode="stack", color_discrete_map=SEX_COLORS,
            labels={"brand_source": "Marque", "Nb": "Produits"},
        )
        _layout(fig_ms, "Répartition Homme / Femme par marque")
        st.plotly_chart(fig_ms, use_container_width=True)

    # ══ TAB 4 : Top produits ═══════════════════════════════════════
    with tab4:
        col_t1, col_t2 = st.columns(2)

        with col_t1:
            st.subheader("⭐ Mieux notés")
            top_rated = (
                df[df["rating"].notna() & df["name"].notna()]
                .sort_values("rating", ascending=False)
                .head(20)[["brand_source", "name", "price_value", "rating", "sexe", "url"]]
            )
            st.dataframe(
                top_rated.rename(columns={
                    "brand_source": "Marque", "name": "Nom",
                    "price_value": "Prix (€)", "rating": "Note",
                    "sexe": "Sexe", "url": "URL",
                }),
                use_container_width=True,
                height=480,
                column_config={
                    "Note":    st.column_config.NumberColumn(format="%.2f ⭐"),
                    "Prix (€)":st.column_config.NumberColumn(format="%.2f €"),
                    "URL":     st.column_config.LinkColumn(),
                },
            )

        with col_t2:
            st.subheader("💸 Moins chers (avec stock)")
            cheapest = (
                df[df["price_value"].notna() & df["name"].notna()
                   & (df["price_value"] > 0)]
                .sort_values("price_value")
                .head(20)[["brand_source", "name", "price_value", "categorie", "sexe", "url"]]
            )
            st.dataframe(
                cheapest.rename(columns={
                    "brand_source": "Marque", "name": "Nom",
                    "price_value": "Prix (€)", "categorie": "Catégorie",
                    "sexe": "Sexe", "url": "URL",
                }),
                use_container_width=True,
                height=480,
                column_config={
                    "Prix (€)": st.column_config.NumberColumn(format="%.2f €"),
                    "URL":      st.column_config.LinkColumn(),
                },
            )

        st.subheader("💎 Plus chers")
        most_exp = (
            df[df["price_value"].notna() & df["name"].notna()]
            .sort_values("price_value", ascending=False)
            .head(20)[["brand_source", "name", "price_value", "categorie", "sexe", "url"]]
        )
        st.dataframe(
            most_exp.rename(columns={
                "brand_source": "Marque", "name": "Nom",
                "price_value": "Prix (€)", "categorie": "Catégorie",
                "sexe": "Sexe", "url": "URL",
            }),
            use_container_width=True,
            height=380,
            column_config={
                "Prix (€)": st.column_config.NumberColumn(format="%.2f €"),
                "URL":      st.column_config.LinkColumn(),
            },
        )

        # Note moyenne par marque (celles qui ont des ratings)
        avg_rating = (
            df[df["rating"].notna()]
            .groupby("brand_source")["rating"]
            .agg(note_moy="mean", nb_avis="count")
            .query("nb_avis >= 5")
            .sort_values("note_moy", ascending=False)
            .head(15).reset_index()
        )
        if len(avg_rating):
            fig_r = px.bar(
                avg_rating, x="brand_source", y="note_moy",
                color="note_moy",
                color_continuous_scale=[[0,"#f59e0b"],[0.5,"#10b981"],[1,"#06b6d4"]],
                labels={"brand_source": "Marque", "note_moy": "Note moyenne"},
                hover_data={"nb_avis": True},
            )
            fig_r.update_layout(coloraxis_showscale=False)
            _layout(fig_r, "Note moyenne par marque (≥ 5 avis)")
            st.plotly_chart(fig_r, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
#  PAGE : PIPELINE
# ══════════════════════════════════════════════════════════════════
elif page == "🔄 Pipeline":
    import plotly.graph_objects as go


    st.title("🔄 Vue du pipeline")

    # ────────────────────────────────────────────────────────────────
    tab_prog, tab_flow, tab_scrapers, tab_sankey, tab_model = st.tabs(
        ["📈 Progression", "🗺️ Architecture", "🕷️ Scrapers", "🌊 Flux de données", "🧱 Modèle Product"]
    )

    # ══ TAB : PROGRESSION ═════════════════════════════════════════
    with tab_prog:

        from datetime import datetime, timezone

        log_files = get_log_files()
        if not log_files:
            st.info("Aucun log disponible.")
        else:
            # Sélecteur de run
            col_sel, col_ref = st.columns([4, 1])
            with col_sel:
                chosen_log = st.selectbox(
                    "Run à afficher",
                    log_files,
                    format_func=lambda p: p.name,
                    label_visibility="collapsed",
                )
            with col_ref:
                auto = st.checkbox("Auto-refresh", value=running)

            prog = parse_run_progress(chosen_log)
            pages_done  = prog["pages_done"]
            pages_total = prog["pages_total"]
            cur         = prog["current_page"]
            pages       = prog["pages"]
            total_prods = prog["total_products"]

            # ── Barre de progression ──────────────────────────────
            pct = pages_done / pages_total if pages_total else 0
            st.markdown(f"### Scraper : **{prog['scraper']}**")

            # Barre custom HTML
            bar_color  = "#6366f1" if running else "#10b981"
            bar_pct    = min(pct * 100, 100)
            st.markdown(
                f"""<div style="background:#1e293b;border-radius:8px;height:28px;
                    width:100%;margin-bottom:8px;overflow:hidden">
                  <div style="background:{bar_color};height:100%;width:{bar_pct:.1f}%;
                    display:flex;align-items:center;justify-content:center;
                    font-size:13px;font-weight:700;color:#fff;transition:width 0.5s">
                    {pages_done} / {pages_total} pages — {bar_pct:.0f}%
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

            # ── KPIs ─────────────────────────────────────────────
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Pages terminées",  f"{pages_done} / {pages_total}")
            c2.metric("Produits collectés", f"{total_prods:,}")
            c3.metric("Erreurs produits",   prog["total_errors"])

            # Vitesse et ETA depuis les timestamps
            if prog["run_start"] and prog["last_ts"]:
                try:
                    t0   = datetime.fromisoformat(prog["run_start"].replace("Z", "+00:00"))
                    t1   = datetime.fromisoformat(prog["last_ts"].replace("Z", "+00:00"))
                    elapsed_s = (t1 - t0).total_seconds()
                    speed = total_prods / (elapsed_s / 3600) if elapsed_s > 0 else 0
                    c4.metric("Vitesse", f"{speed:.0f} prod/h")

                    if pct > 0.01 and pct < 1.0 and elapsed_s > 0:
                        eta_s    = elapsed_s / pct - elapsed_s
                        eta_min  = int(eta_s / 60)
                        eta_h, eta_m = divmod(eta_min, 60)
                        c5.metric("ETA", f"{eta_h}h{eta_m:02d}m")
                    elif pct >= 1.0:
                        c5.metric("ETA", "Terminé ✅")
                    else:
                        c5.metric("ETA", "calcul…")
                except Exception:
                    c4.metric("Vitesse", "—")
                    c5.metric("ETA", "—")
            else:
                c4.metric("Vitesse", "—")
                c5.metric("ETA", "—")

            st.divider()

            # ── Page en cours ─────────────────────────────────────
            if cur and running:
                done_in_cur = cur["products"]
                urls_in_cur = cur["urls"] or 1
                cur_pct     = min(done_in_cur / urls_in_cur * 100, 100)
                st.markdown(f"**⏳ En cours :** `{cur['label']}`")
                st.markdown(
                    f"""<div style="background:#1e293b;border-radius:6px;
                        height:18px;width:100%;overflow:hidden;margin-bottom:12px">
                      <div style="background:#06b6d4;height:100%;width:{cur_pct:.1f}%;"></div>
                    </div>
                    <span style="font-size:12px;color:#94a3b8">
                      {done_in_cur} / {urls_in_cur} produits
                      ({cur['errors']} erreurs)
                    </span>""",
                    unsafe_allow_html=True,
                )

            # ── Timeline des pages ────────────────────────────────
            st.subheader("Pages terminées")
            if pages:
                def _dur(p):
                    try:
                        t0 = datetime.fromisoformat(p["start_ts"].replace("Z", "+00:00"))
                        t1 = datetime.fromisoformat(p["end_ts"].replace("Z", "+00:00"))
                        return int((t1 - t0).total_seconds() / 60)
                    except Exception:
                        return 0

                df_pages = pd.DataFrame([
                    {
                        "Page":       p["label"],
                        "URLs":       p["urls"],
                        "✓ Produits": p["products"],
                        "✗ Erreurs":  p["errors"],
                        "Durée (min)":_dur(p),
                        "Heure début":p["start_ts"][11:19] if p["start_ts"] else "—",
                    }
                    for p in pages
                ])

                # Graphique barres horizontales
                fig_p = px.bar(
                    df_pages, x="✓ Produits", y="Page", orientation="h",
                    color="✓ Produits",
                    color_continuous_scale=[[0,"#312e81"],[0.5,"#6366f1"],[1,"#06b6d4"]],
                    hover_data=["URLs", "✗ Erreurs", "Durée (min)"],
                    height=max(300, len(pages) * 24),
                )
                fig_p.update_layout(
                    yaxis={"categoryorder": "trace"},
                    coloraxis_showscale=False,
                )
                _layout(fig_p, "Produits collectés par page")
                st.plotly_chart(fig_p, use_container_width=True)

                # Tableau détaillé
                with st.expander("Tableau détaillé"):
                    st.dataframe(
                        df_pages,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "✓ Produits":  st.column_config.NumberColumn(),
                            "✗ Erreurs":   st.column_config.NumberColumn(),
                            "Durée (min)": st.column_config.NumberColumn(format="%d min"),
                        },
                    )
            else:
                st.info("Aucune page terminée pour l'instant.")

            # ── Derniers logs ─────────────────────────────────────
            st.subheader("Dernières lignes")
            last_lines = read_log_lines(chosen_log, last_n=30)
            LEVELS = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3}
            recent = [l for l in last_lines if LEVELS.get(l.get("level","INFO"),1) >= 1]
            log_txt = "\n".join(
                "[{ts}] [{lvl:7}] {msg}".format(
                    ts=l.get("ts","")[:19], lvl=l.get("level","?"), msg=l.get("msg","")
                )
                for l in recent
            )
            st.code(log_txt, language=None)

            if auto and running:
                time.sleep(5)
                st.rerun()

    # ══ TAB : ARCHITECTURE ════════════════════════════════════════
    with tab_flow:
        st.subheader("Architecture du pipeline")

        STAGES = [
            {
                "id": "scrapers", "x": 0.05, "y": 0.5, "w": 0.13, "h": 0.55,
                "title": "Scrapers",
                "color": "#312e81", "border": "#6366f1",
                "lines": [
                    "22 scrapers",
                    "18 × requests/BS4",
                    "4 × Playwright",
                    "Airflow DAG (3h UTC)",
                ],
            },
            {
                "id": "pipeline", "x": 0.28, "y": 0.5, "w": 0.13, "h": 0.55,
                "title": "SmartWearPipeline",
                "color": "#1e3a5f", "border": "#06b6d4",
                "lines": [
                    "validate_and_clean()",
                    "Filtre sous-vêtements",
                    "Filtre non-fashion",
                    "→ SmartWear_DB.json",
                ],
            },
            {
                "id": "audit", "x": 0.50, "y": 0.5, "w": 0.13, "h": 0.55,
                "title": "Audit",
                "color": "#14532d", "border": "#10b981",
                "lines": [
                    "Déduplique",
                    "Corrige catégories",
                    "Nettoie descriptions",
                    "Infère sexe manquant",
                ],
            },
            {
                "id": "check", "x": 0.72, "y": 0.5, "w": 0.13, "h": 0.55,
                "title": "Check",
                "color": "#78350f", "border": "#f59e0b",
                "lines": [
                    "Anomalies style/cat",
                    "T-shirt ≠ Haut ?",
                    "Chaussures type ?",
                    "→ rapport anomalies",
                ],
            },
            {
                "id": "output", "x": 0.93, "y": 0.5, "w": 0.10, "h": 0.55,
                "title": "Outputs",
                "color": "#4c1d95", "border": "#8b5cf6",
                "lines": [
                    "SmartWear_DB.json",
                    "stats.json",
                    "Flask app",
                    "Streamlit",
                ],
            },
        ]

        shapes, annotations = [], []
        for s in STAGES:
            x0 = s["x"] - s["w"] / 2
            x1 = s["x"] + s["w"] / 2
            y0 = s["y"] - s["h"] / 2
            y1 = s["y"] + s["h"] / 2
            shapes.append(dict(
                type="rect", x0=x0, y0=y0, x1=x1, y1=y1,
                fillcolor=s["color"], line=dict(color=s["border"], width=2),
                xref="paper", yref="paper",
            ))
            annotations.append(dict(
                x=s["x"], y=y1 - 0.04,
                text=f"<b>{s['title']}</b>",
                showarrow=False, xref="paper", yref="paper",
                font=dict(color=s["border"], size=13),
            ))
            for i, line in enumerate(s["lines"]):
                annotations.append(dict(
                    x=s["x"], y=y1 - 0.13 - i * 0.09,
                    text=line, showarrow=False,
                    xref="paper", yref="paper",
                    font=dict(color="#cbd5e1", size=10),
                ))

        ARROWS = [
            ("scrapers", "pipeline"),
            ("pipeline", "audit"),
            ("audit", "check"),
            ("check", "output"),
        ]
        stage_map = {s["id"]: s for s in STAGES}
        for src_id, dst_id in ARROWS:
            src = stage_map[src_id]
            dst = stage_map[dst_id]
            shapes.append(dict(
                type="line",
                x0=src["x"] + src["w"] / 2, y0=src["y"],
                x1=dst["x"] - dst["w"] / 2, y1=dst["y"],
                line=dict(color="#475569", width=2),
                xref="paper", yref="paper",
            ))

        fig_arch = go.Figure()
        fig_arch.update_layout(
            shapes=shapes, annotations=annotations,
            xaxis=dict(visible=False, range=[0, 1]),
            yaxis=dict(visible=False, range=[0, 1]),
            height=340, margin=dict(l=0, r=0, t=20, b=0),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_arch, use_container_width=True)

        # Descriptions détaillées des étapes
        st.divider()
        cols = st.columns(5)
        details = [
            ("🕷️ Scrapers", "#6366f1",
             "22 scrapers collectent les produits sur les sites marchands. "
             "18 utilisent **requests + BeautifulSoup**, 4 utilisent **Playwright** "
             "(headless=False pour ASOS, Nike, Jules, Gymshark). "
             "Orchestrés par un **DAG Airflow** quotidien à 3h UTC."),
            ("⚙️ Pipeline", "#06b6d4",
             "Chaque `Product` passe par `validate_and_clean()` : normalisation des prix, "
             "tailles, catégories, styles. Filtrage des **sous-vêtements** et **non-fashion** "
             "(tabac, skateboard, etc.). Sortie : `SmartWear_DB.json`."),
            ("🔍 Audit", "#10b981",
             "Déduplique par `(name, color, brand_source)`. Corrige les catégories "
             "incohérentes avec le style (`T-shirt → Haut`). Nettoie les retours à la ligne "
             "dans les descriptions. Infère le sexe manquant depuis le nom."),
            ("⚠️ Check", "#f59e0b",
             "4 règles de cohérence : T-shirt ≠ Haut, Pantalon/Short ≠ Bas, "
             "Veste/Manteau ≠ Manteau-Veste, Sneakers ≠ Chaussures. "
             "Retourne les anomalies avec échantillons pour correction manuelle."),
            ("📦 Outputs", "#8b5cf6",
             "`SmartWear_DB.json` (~20k produits) consommé par la **Flask app** "
             "et ce dashboard Streamlit. `stats.json` au format Grafana Infinity "
             "pour dashboards de monitoring."),
        ]
        for col, (title, color, desc) in zip(cols, details):
            col.markdown(
                f"""<div style="border:1px solid {color};border-radius:8px;
                padding:12px;height:200px;overflow:auto">
                <b style="color:{color}">{title}</b><br><br>
                <span style="font-size:12px;color:#cbd5e1">{desc}</span></div>""",
                unsafe_allow_html=True,
            )

    # ══ TAB : SCRAPERS ═════════════════════════════════════════════
    with tab_scrapers:
        st.subheader("État des scrapers")

        total_in_db = sum(brand_cnt.values())
        n_ok  = sum(1 for v in log_stats.values() if v.get("status") == "ok")
        n_err = sum(1 for v in log_stats.values() if v.get("status") == "error")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Scrapers actifs",    len(SCRAPERS_META))
        c2.metric("Derniers runs OK",   n_ok)
        c3.metric("Derniers runs KO",   n_err)
        c4.metric("Produits en base",   f"{total_in_db:,}")

        st.divider()

        # Grille de cartes — 4 par ligne
        scraper_items = list(SCRAPERS_META.items())
        for row_start in range(0, len(scraper_items), 4):
            row = scraper_items[row_start:row_start + 4]
            cols = st.columns(4)
            for col, (key, meta) in zip(cols, row):
                brand  = meta["brand"]
                tech   = meta["tech"]
                run    = log_stats.get(key.upper(), {})
                count  = brand_cnt.get(brand, 0)
                status = run.get("status", "unknown")
                last_d = run.get("date", "—")
                log_count = run.get("count", 0)

                if status == "ok":
                    badge_color, badge_bg, icon = "#10b981", "#052e16", "🟢"
                elif status == "error":
                    badge_color, badge_bg, icon = "#ef4444", "#450a0a", "🔴"
                else:
                    badge_color, badge_bg, icon = "#94a3b8", "#1e293b", "⚪"

                tech_color = "#8b5cf6" if tech == "playwright" else "#06b6d4"
                tech_icon  = "🎭" if tech == "playwright" else "🌐"

                col.markdown(
                    f"""<div style="border:1px solid {badge_color};border-radius:10px;
                    padding:12px;margin-bottom:8px;background:{badge_bg}22">
                    <div style="font-size:14px;font-weight:700;color:#f1f5f9">
                      {icon} {meta['label']}
                    </div>
                    <div style="font-size:11px;color:{tech_color};margin-top:4px">
                      {tech_icon} {tech}
                    </div>
                    <div style="font-size:11px;color:#94a3b8;margin-top:6px">
                      📦 <b style="color:#e2e8f0">{count:,}</b> produits en base
                    </div>
                    <div style="font-size:11px;color:#94a3b8">
                      🕒 Dernier run : <b style="color:#e2e8f0">{last_d}</b>
                    </div>
                    {"<div style='font-size:11px;color:#94a3b8'>✅ " + str(log_count) + " collectés</div>" if log_count else ""}
                    </div>""",
                    unsafe_allow_html=True,
                )

        st.divider()
        st.subheader("Couverture par scraper")
        df_cov = pd.DataFrame([
            {
                "Scraper": meta["label"],
                "Produits en base": brand_cnt.get(meta["brand"], 0),
                "Technologie": meta["tech"],
                "Dernier run": log_stats.get(key.upper(), {}).get("date", "—"),
                "Statut": log_stats.get(key.upper(), {}).get("status", "unknown"),
            }
            for key, meta in SCRAPERS_META.items()
        ]).sort_values("Produits en base", ascending=False)

        fig_cov = px.bar(
            df_cov, x="Scraper", y="Produits en base",
            color="Technologie",
            color_discrete_map={"playwright": "#8b5cf6", "requests": "#06b6d4"},
            hover_data=["Dernier run", "Statut"],
        )
        _layout(fig_cov, "Produits en base par scraper")
        st.plotly_chart(fig_cov, use_container_width=True)

    # ══ TAB : SANKEY ══════════════════════════════════════════════
    with tab_sankey:
        st.subheader("Flux de données — Sankey")
        st.caption("Visualise combien de produits chaque scraper contribue à la base finale.")

        brands_sorted = sorted(brand_cnt.items(), key=lambda x: -x[1])
        brand_labels  = [b for b, _ in brands_sorted]
        brand_counts  = [c for _, c in brands_sorted]
        total_all     = sum(brand_counts)

        # Nœuds : scrapers + "Pipeline" + "DB"
        node_labels = brand_labels + ["⚙️ Pipeline", "🗄️ SmartWear_DB.json"]
        pipeline_idx = len(brand_labels)
        db_idx       = len(brand_labels) + 1

        sources = list(range(len(brand_labels))) + [pipeline_idx] * len(brand_labels)
        targets = [pipeline_idx] * len(brand_labels) + [db_idx] * len(brand_labels)
        values  = brand_counts + brand_counts

        node_colors = (
            [f"rgba(99,102,241,0.8)"] * len(brand_labels)
            + ["rgba(6,182,212,0.9)", "rgba(139,92,246,0.9)"]
        )
        link_colors = (
            [f"rgba(99,102,241,0.3)"] * len(brand_labels)
            + [f"rgba(6,182,212,0.3)"] * len(brand_labels)
        )

        fig_sk = go.Figure(go.Sankey(
            arrangement="snap",
            node=dict(
                label=node_labels,
                color=node_colors,
                pad=12, thickness=18,
                line=dict(color="#0f172a", width=0.5),
            ),
            link=dict(source=sources, target=targets, value=values, color=link_colors),
        ))
        fig_sk.update_layout(
            height=max(450, len(brand_labels) * 22),
            paper_bgcolor="rgba(0,0,0,0)",
            font_color="#e2e8f0",
            margin=dict(l=10, r=10, t=30, b=10),
        )
        st.plotly_chart(fig_sk, use_container_width=True)

    # ══ TAB : MODÈLE PRODUCT ══════════════════════════════════════
    with tab_model:
        st.subheader("Modèle `Product`")
        st.caption("Dataclass Python — chaque scraper remplit ces champs.")

        FIELDS = [
            ("name",         "str",            "Obligatoire",  "Nom complet du produit",                       "Nike Air Force 1"),
            ("price_value",  "float | None",   "Recommandé",   "Prix numérique",                               "89.99"),
            ("currency",     "str | None",     "Recommandé",   "EUR / USD / GBP",                              "EUR"),
            ("description",  "str | None",     "Optionnel",    "Description produit (max 500 car.)",            "T-shirt en coton bio..."),
            ("genre",        "str | None",     "Recommandé",   "Enfant | Adolescent | Adulte",                  "Adulte"),
            ("sexe",         "str | None",     "Recommandé",   "Homme | Femme | Fille | Garçon",                "Homme"),
            ("sizes",        "List[int]",      "Chaussures",   "Pointures numériques (39, 40, 41…)",            "[40, 41, 42]"),
            ("taille",       "List[str]",      "Vêtements",    "XS / S / M / L / XL / XXL / XXXL",             "['S', 'M', 'L']"),
            ("color",        "str | None",     "Optionnel",    "Couleur principale",                            "Blanc"),
            ("rating",       "float | None",   "Optionnel",    "Note client (1.0–5.0)",                         "4.3"),
            ("type",         "str | None",     "Recommandé",   "Vêtement | Chaussures | Autre",                 "Vêtement"),
            ("categorie",    "str | None",     "Recommandé",   "Haut | Bas | Robe/Combinaison | Manteau/Veste", "Haut"),
            ("style",        "str | None",     "Recommandé",   "T-shirt | Jean | Robe | Sneakers | …",          "T-shirt"),
            ("image",        "str | None",     "Recommandé",   "URL de l'image principale",                     "https://…"),
            ("url",          "str | None",     "Recommandé",   "URL du produit",                                "https://…"),
            ("brand_source", "str | None",     "Auto",         "Nom de la marque — positionné par le scraper",  "Nike"),
        ]

        df_model = pd.DataFrame(
            FIELDS, columns=["Champ", "Type Python", "Statut", "Description", "Exemple"]
        )

        STATUS_COLORS = {
            "Obligatoire": "🔴", "Recommandé": "🟡",
            "Optionnel": "⚪", "Chaussures": "🔵",
            "Vêtements": "🟢", "Auto": "🟣",
        }
        df_model["Statut"] = df_model["Statut"].map(
            lambda s: f"{STATUS_COLORS.get(s, '')} {s}"
        )

        st.dataframe(
            df_model, use_container_width=True, hide_index=True, height=560,
            column_config={
                "Champ":       st.column_config.TextColumn(width="small"),
                "Type Python": st.column_config.TextColumn(width="medium"),
                "Statut":      st.column_config.TextColumn(width="small"),
                "Description": st.column_config.TextColumn(width="large"),
                "Exemple":     st.column_config.TextColumn(width="medium"),
            },
        )

        st.divider()
        st.subheader("Complétude actuelle par champ")
        products_raw = load_db()
        if products_raw:
            df_raw = pd.DataFrame(products_raw)
            fields_check = ["name", "price_value", "description", "genre", "sexe",
                            "color", "rating", "type", "categorie", "style", "image", "url"]
            comp = {
                f: round(df_raw[f].notna().mean() * 100, 1)
                for f in fields_check if f in df_raw.columns
            }
            df_comp = pd.DataFrame(list(comp.items()), columns=["Champ", "Complétude (%)"])
            df_comp = df_comp.sort_values("Complétude (%)")
            fig_comp = px.bar(
                df_comp, x="Complétude (%)", y="Champ", orientation="h",
                color="Complétude (%)",
                color_continuous_scale=[[0,"#ef4444"],[0.5,"#f59e0b"],[1,"#10b981"]],
                range_color=[0, 100],
                text="Complétude (%)",
            )
            fig_comp.update_traces(texttemplate="%{text}%", textposition="outside")
            fig_comp.update_layout(coloraxis_showscale=False)
            _layout(fig_comp, "Complétude par champ (% de valeurs non-null)", height=380)
            st.plotly_chart(fig_comp, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
#  PAGE : LANCER — Centre de contrôle scraping
# ══════════════════════════════════════════════════════════════════
elif page == "🚀 Lancer":

    from datetime import datetime

    st.title("🚀 Centre de contrôle — Scraping")

    # ── Groupes de scrapers ────────────────────────────────────────
    GROUPS = {
        "🛍️ Multimarques":        {"scrapers": ["asos", "mango"],                                    "color": "#6366f1"},
        "🇫🇷 Marques françaises":  {"scrapers": ["apc","balzac","maisonlabiche","rouje","cabaia",
                                                   "bonnegueule","merci","isabelmarant","amiparis","jules"], "color": "#06b6d4"},
        "💪 Sport & Fitness":      {"scrapers": ["nike","gymshark","kappa","lotto","tacchini","lecoqsportif"], "color": "#10b981"},
        "🎭 Streetwear & Premium": {"scrapers": ["stussy","palace","fillingpieces","karhu"],            "color": "#f59e0b"},
    }
    SCRAPER_TECH = {
        **{s: "playwright" for s in ["asos","nike","gymshark","jules"]},
        **{s: "requests"   for s in ALL_SCRAPERS if s not in ["asos","nike","gymshark","jules"]},
    }

    # ── Parser statut multi-scrapers ───────────────────────────────
    def parse_multi_status(log_file: Path, selected_scrapers: list) -> dict:
        status = {s: {"status": "pending", "products": 0, "errors": 0} for s in selected_scrapers}
        current = None
        for line in read_log_lines(log_file, last_n=200_000):
            msg  = line.get("msg", "")
            ts   = line.get("ts", "")
            lvl  = line.get("level", "INFO")

            m = _re.search(r"Lancement\s*:\s*(\S+)", msg)
            if m:
                key = m.group(1).lower()
                if key in status:
                    current = key
                    status[key].update({"status": "running", "start_ts": ts, "products": 0})

            if current and current in status:
                if "✓" in msg:
                    status[current]["products"] += 1
                    status[current]["last_ts"]   = ts
                if lvl == "WARNING" and "Erreur" in msg:
                    status[current]["errors"] += 1
                m2 = _re.search(r"(\d+) produits", msg)
                if m2 and ("terminé" in msg.lower() or "total :" in msg.lower()):
                    status[current].update({
                        "status":   "done",
                        "products": int(m2.group(1)),
                        "end_ts":   ts,
                    })
                    current = None
                if lvl == "ERROR" and current:
                    status[current].update({"status": "error", "end_ts": ts})
                    current = None
        return status

    # ── Init session state ─────────────────────────────────────────
    if "cc_selected" not in st.session_state:
        st.session_state.cc_selected = set(ALL_SCRAPERS)

    # ══════════════════════════════════════════════════════════════
    col_left, col_right = st.columns([4, 6], gap="large")

    # ─────────────────────────────────────────────────────────────
    # COLONNE GAUCHE : Sélection
    # ─────────────────────────────────────────────────────────────
    with col_left:
        st.subheader("Sélection des scrapers")

        # Actions rapides
        qc1, qc2, qc3 = st.columns(3)
        if qc1.button("✅ Tous", use_container_width=True):
            st.session_state.cc_selected = set(ALL_SCRAPERS)
            st.rerun()
        if qc2.button("⬜ Aucun", use_container_width=True):
            st.session_state.cc_selected = set()
            st.rerun()
        # Playwright only / requests only toggle
        pw_only = set(k for k, v in SCRAPER_TECH.items() if v == "playwright")
        if qc3.button("🎭 Playwright", use_container_width=True):
            st.session_state.cc_selected = pw_only
            st.rerun()

        st.markdown("---")

        # Cartes par groupe
        for group_name, group_data in GROUPS.items():
            color = group_data["color"]
            scrapers_in_group = group_data["scrapers"]

            # Header groupe + toggle
            gc1, gc2 = st.columns([4, 1])
            gc1.markdown(
                f'<span style="color:{color};font-weight:700;font-size:15px">'
                f'{group_name}</span>', unsafe_allow_html=True
            )
            all_in = all(s in st.session_state.cc_selected for s in scrapers_in_group)
            btn_label = "Aucun" if all_in else "Tous"
            if gc2.button(btn_label, key=f"grp_{group_name}", use_container_width=True):
                if all_in:
                    st.session_state.cc_selected -= set(scrapers_in_group)
                else:
                    st.session_state.cc_selected |= set(scrapers_in_group)
                st.rerun()

            # Cartes scrapers (3 par ligne)
            for i in range(0, len(scrapers_in_group), 3):
                row = scrapers_in_group[i:i+3]
                cols = st.columns(3)
                for col, scraper in zip(cols, row):
                    is_sel  = scraper in st.session_state.cc_selected
                    tech    = SCRAPER_TECH.get(scraper, "requests")
                    label   = SCRAPERS_META[scraper]["label"] if scraper in SCRAPERS_META else scraper
                    db_cnt  = brand_cnt.get(SCRAPERS_META[scraper]["brand"] if scraper in SCRAPERS_META else "", 0)
                    border  = color if is_sel else "#334155"
                    bg      = f"{color}18" if is_sel else "transparent"
                    icon    = "🎭" if tech == "playwright" else "🌐"
                    chk = col.checkbox(
                        label,
                        value=is_sel,
                        key=f"chk_{scraper}",
                    )
                    if chk != is_sel:
                        if chk:
                            st.session_state.cc_selected.add(scraper)
                        else:
                            st.session_state.cc_selected.discard(scraper)
                        st.rerun()
                    col.markdown(
                        f'<div style="font-size:10px;color:#64748b;margin-top:-10px;'
                        f'margin-bottom:8px">{icon} {db_cnt:,} en base</div>',
                        unsafe_allow_html=True,
                    )

        st.markdown("---")

        selected_list = sorted(st.session_state.cc_selected,
                               key=lambda s: ALL_SCRAPERS.index(s) if s in ALL_SCRAPERS else 99)
        n_sel = len(selected_list)

        # Résumé sélection
        st.markdown(
            f'<div style="background:#1e293b;border-radius:8px;padding:10px 14px;'
            f'margin-bottom:12px;font-size:13px;color:#94a3b8">'
            f'<b style="color:#e2e8f0">{n_sel}</b> scraper{"s" if n_sel>1 else ""} sélectionné{"s" if n_sel>1 else ""} '
            f'— <span style="color:#6366f1">{sum(1 for s in selected_list if SCRAPER_TECH.get(s)=="playwright")} Playwright</span> '
            f'/ <span style="color:#06b6d4">{sum(1 for s in selected_list if SCRAPER_TECH.get(s)=="requests")} requests</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Boutons lancement / arrêt
        if not running:
            if st.button(
                f"▶  Lancer {n_sel} scraper{'s' if n_sel > 1 else ''}",
                type="primary",
                disabled=n_sel == 0,
                use_container_width=True,
            ):
                args = [VENV_PYTHON, "-m", "pipeline.run", "--scrapers"] + selected_list
                proc = subprocess.Popen(args, cwd=str(PROJECT_ROOT),
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                st.session_state.pid          = proc.pid
                st.session_state.cc_launched  = selected_list
                time.sleep(1.5)
                st.rerun()
        else:
            st.button("⏳ Pipeline en cours…", disabled=True, use_container_width=True)
            if st.button("⏹  Arrêter", use_container_width=True):
                try:
                    os.kill(st.session_state.pid, 15)
                except Exception:
                    pass
                st.session_state.pid = None
                st.rerun()

        # Options avancées
        with st.expander("⚙️ Options avancées"):
            log_level = st.selectbox("Niveau de log", ["INFO", "DEBUG", "WARNING"], index=0,
                                     key="cc_log_level")

    # ─────────────────────────────────────────────────────────────
    # COLONNE DROITE : Progression
    # ─────────────────────────────────────────────────────────────
    with col_right:
        st.subheader("Progression en temps réel")

        log_files = get_log_files()
        if not log_files:
            st.info("Lance un scraper pour voir la progression ici.")
        else:
            latest_log    = log_files[0]
            launched      = st.session_state.get("cc_launched", ALL_SCRAPERS)
            multi_status  = parse_multi_status(latest_log, launched)

            # ── Barre globale ──────────────────────────────────
            n_done  = sum(1 for v in multi_status.values() if v["status"] == "done")
            n_total = len(launched)
            n_error = sum(1 for v in multi_status.values() if v["status"] == "error")
            total_p = sum(v["products"] for v in multi_status.values())

            pct_g    = n_done / n_total * 100 if n_total else 0
            bar_col  = "#10b981" if not running else "#6366f1"
            st.markdown(
                f"""<div style="background:#1e293b;border-radius:8px;height:32px;
                    width:100%;overflow:hidden;margin-bottom:10px">
                  <div style="background:{bar_col};height:100%;width:{pct_g:.1f}%;
                    display:flex;align-items:center;justify-content:center;
                    font-size:13px;font-weight:700;color:#fff">
                    {n_done} / {n_total} scrapers  —  {pct_g:.0f}%
                  </div>
                </div>""",
                unsafe_allow_html=True,
            )

            # ── KPIs ──────────────────────────────────────────
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Scrapers terminés", f"{n_done} / {n_total}")
            k2.metric("Produits collectés", f"{total_p:,}")
            k3.metric("Erreurs produits",   n_error)
            # Vitesse depuis dernier log
            try:
                first_lines = read_log_lines(latest_log, last_n=200_000)
                t0_str = next((l["ts"] for l in first_lines if "Lancement" in l.get("msg","")), None)
                tN_str = first_lines[-1]["ts"] if first_lines else None
                if t0_str and tN_str and total_p > 0:
                    t0 = datetime.fromisoformat(t0_str.replace("Z","+00:00"))
                    tN = datetime.fromisoformat(tN_str.replace("Z","+00:00"))
                    s  = (tN - t0).total_seconds()
                    speed = total_p / (s / 3600) if s > 0 else 0
                    k4.metric("Vitesse", f"{speed:.0f} prod/h")
                else:
                    k4.metric("Vitesse", "—")
            except Exception:
                k4.metric("Vitesse", "—")

            st.markdown("---")

            # ── Pipeline visuel : chips par scraper ───────────
            st.markdown("**Scrapers :**")
            STATUS_STYLE = {
                "done":    ("✅", "#10b981", "#052e16"),
                "running": ("⏳", "#6366f1", "#1e1b4b"),
                "error":   ("❌", "#ef4444", "#450a0a"),
                "pending": ("⬜", "#475569", "#0f172a"),
            }
            chips_html = '<div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px">'
            for scraper in launched:
                sv       = multi_status.get(scraper, {"status": "pending", "products": 0})
                icon, border, bg = STATUS_STYLE.get(sv["status"], STATUS_STYLE["pending"])
                label    = SCRAPERS_META[scraper]["label"] if scraper in SCRAPERS_META else scraper
                products = sv["products"]
                prod_str = f" · {products:,}" if products > 0 else ""
                chips_html += (
                    f'<div style="border:1px solid {border};background:{bg};'
                    f'border-radius:20px;padding:4px 10px;font-size:12px;color:#e2e8f0;'
                    f'white-space:nowrap">'
                    f'{icon} {label}{prod_str}</div>'
                )
            chips_html += "</div>"
            st.markdown(chips_html, unsafe_allow_html=True)

            # ── Détail scraper en cours ────────────────────────
            running_scrapers = [s for s, v in multi_status.items() if v["status"] == "running"]
            if running_scrapers:
                cur_s  = running_scrapers[0]
                cur_v  = multi_status[cur_s]
                cur_lbl = SCRAPERS_META[cur_s]["label"] if cur_s in SCRAPERS_META else cur_s

                # Si ASOS, utiliser le parser par page
                if cur_s == "asos":
                    asos_prog = parse_run_progress(latest_log)
                    p_done    = asos_prog["pages_done"]
                    p_total   = asos_prog["pages_total"]
                    p_pct     = p_done / p_total * 100 if p_total else 0
                    st.markdown(
                        f"**⏳ {cur_lbl}** — page {p_done}/{p_total} — "
                        f"{cur_v['products']:,} produits"
                    )
                    st.markdown(
                        f'<div style="background:#1e293b;border-radius:6px;height:16px;'
                        f'width:100%;overflow:hidden">'
                        f'<div style="background:#6366f1;height:100%;width:{p_pct:.1f}%"></div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                    # Page en cours dans ASOS
                    if asos_prog["current_page"]:
                        cp = asos_prog["current_page"]
                        cp_pct = min(cp["products"] / max(cp["urls"], 1) * 100, 100)
                        st.markdown(
                            f'<span style="font-size:11px;color:#94a3b8">📄 `{cp["label"]}` — '
                            f'{cp["products"]} / {cp["urls"]} URLs</span>',
                            unsafe_allow_html=True,
                        )
                        st.markdown(
                            f'<div style="background:#1e293b;border-radius:4px;height:8px;'
                            f'width:100%;overflow:hidden;margin-top:4px">'
                            f'<div style="background:#06b6d4;height:100%;width:{cp_pct:.1f}%"></div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.markdown(f"**⏳ {cur_lbl}** — {cur_v['products']:,} produits collectés")

            # ── Tableau récapitulatif scrapers terminés ────────
            done_scrapers = [(s, v) for s, v in multi_status.items() if v["status"] == "done"]
            if done_scrapers:
                st.markdown("**Scrapers terminés :**")
                def _dur_ms(v):
                    try:
                        t0 = datetime.fromisoformat(v.get("start_ts","").replace("Z","+00:00"))
                        t1 = datetime.fromisoformat(v.get("end_ts","").replace("Z","+00:00"))
                        return int((t1 - t0).total_seconds() / 60)
                    except Exception:
                        return 0
                df_done = pd.DataFrame([
                    {
                        "Scraper":   SCRAPERS_META[s]["label"] if s in SCRAPERS_META else s,
                        "Produits":  v["products"],
                        "Erreurs":   v["errors"],
                        "Durée (min)": _dur_ms(v),
                        "Terminé à": v.get("end_ts","")[:19] if v.get("end_ts") else "—",
                    }
                    for s, v in done_scrapers
                ])
                st.dataframe(
                    df_done, use_container_width=True, hide_index=True, height=200,
                    column_config={
                        "Produits":    st.column_config.NumberColumn(),
                        "Erreurs":     st.column_config.NumberColumn(),
                        "Durée (min)": st.column_config.NumberColumn(format="%d min"),
                    },
                )

            st.markdown("---")

            # ── Log en direct ──────────────────────────────────
            st.markdown("**Log en direct**")
            lv_filter = st.selectbox("Niveau", ["INFO","WARNING","ERROR"], index=0,
                                     key="cc_lv", label_visibility="collapsed")
            LVL = {"INFO": 1, "WARNING": 2, "ERROR": 3}
            min_lv = LVL.get(lv_filter, 1)
            live_lines = [l for l in read_log_lines(latest_log, last_n=80)
                          if LVL.get(l.get("level","INFO"), 1) >= min_lv]
            log_txt = "\n".join(
                "[{ts}] [{lvl:7}] {msg}".format(
                    ts=l.get("ts","")[:19], lvl=l.get("level","?"), msg=l.get("msg","")
                )
                for l in live_lines
            )
            st.code(log_txt, language=None)
            st.caption(
                f"📄 `{latest_log.name}` — "
                f"{sum(1 for l in live_lines if '✓' in l.get('msg',''))} succès · "
                f"{sum(1 for l in live_lines if l.get('level') in ('WARNING','ERROR'))} warnings"
            )

            # Auto-refresh
            auto = st.checkbox("🔄 Auto-refresh (5s)", value=running, key="cc_auto")
            if auto and running:
                time.sleep(5)
                st.rerun()


# ══════════════════════════════════════════════════════════════════
#  PAGE : LOGS
# ══════════════════════════════════════════════════════════════════
elif page == "📋 Logs":
    st.title("📋 Historique des logs")

    log_files = get_log_files()
    if not log_files:
        st.warning("Aucun fichier de log trouvé.")
        st.stop()

    selected_log = st.selectbox(
        "Fichier de log",
        log_files,
        format_func=lambda p: f"{p.name}  ({p.stat().st_size // 1024} Ko)",
    )

    lines = read_log_lines(selected_log, last_n=2000)
    if not lines:
        st.warning("Log vide.")
        st.stop()

    df_log = pd.DataFrame(lines)
    if "ts" in df_log:
        df_log["ts"] = pd.to_datetime(df_log["ts"], errors="coerce").dt.strftime("%H:%M:%S")

    c1, c2, c3 = st.columns(3)
    level_opts = ["Tous"] + sorted(df_log["level"].dropna().unique().tolist()) if "level" in df_log else ["Tous"]
    level_f    = c1.selectbox("Niveau", level_opts)
    scraper_opts = ["Tous"] + sorted(df_log["scraper"].dropna().unique().tolist()) if "scraper" in df_log else ["Tous"]
    scraper_f  = c2.selectbox("Scraper", scraper_opts)
    search     = c3.text_input("Recherche dans le message")

    fdf = df_log.copy()
    if level_f != "Tous" and "level" in fdf.columns:
        fdf = fdf[fdf["level"] == level_f]
    if scraper_f != "Tous" and "scraper" in fdf.columns:
        fdf = fdf[fdf["scraper"] == scraper_f]
    if search and "msg" in fdf.columns:
        fdf = fdf[fdf["msg"].str.contains(search, case=False, na=False)]

    st.write(f"**{len(fdf):,}** lignes affichées")

    display_cols = [c for c in ["ts", "level", "scraper", "msg"] if c in fdf.columns]
    st.dataframe(
        fdf[display_cols].rename(columns={
            "ts": "Heure", "level": "Niveau", "scraper": "Scraper", "msg": "Message"
        }),
        use_container_width=True,
        height=600,
    )

    # Stats du run
    if "level" in df_log.columns:
        st.divider()
        st.subheader("Résumé du run")
        level_counts = df_log["level"].value_counts().reset_index()
        level_counts.columns = ["Niveau", "Nb"]
        fig = px.pie(
            level_counts, values="Nb", names="Niveau", hole=0.4,
            color="Niveau",
            color_discrete_map={"INFO": "#10b981", "WARNING": "#f59e0b", "ERROR": "#ef4444"},
        )
        fig.update_traces(marker=dict(line=dict(color="#0f172a", width=2)))
        _layout(fig, "Répartition des niveaux de log")
        st.plotly_chart(fig, use_container_width=True)


# ══════════════════════════════════════════════════════════════════
#  PAGE : PRODUITS
# ══════════════════════════════════════════════════════════════════
elif page == "🗄️ Produits":
    st.title("🗄️ Explorer les produits")

    products = load_db()
    if not products:
        st.warning("Base vide.")
        st.stop()

    df = pd.DataFrame(products)

    with st.expander("🔎 Filtres", expanded=True):
        col1, col2, col3, col4 = st.columns(4)

        brand_f = col1.selectbox(
            "Marque",
            ["Toutes"] + sorted(df["brand_source"].dropna().unique().tolist()),
        )
        sexe_f = col2.selectbox(
            "Sexe",
            ["Tous"] + sorted(df["sexe"].dropna().unique().tolist()),
        )
        cat_f = col3.selectbox(
            "Catégorie",
            ["Toutes"] + sorted(df["categorie"].dropna().unique().tolist()),
        )
        style_f = col4.selectbox(
            "Style",
            ["Tous"] + sorted(df["style"].dropna().unique().tolist()),
        )

        prices = df["price_value"].dropna()
        if len(prices) > 0:
            p_min, p_max = float(prices.min()), float(prices.max())
            price_range = st.slider(
                "Fourchette de prix (€)",
                p_min, min(p_max, 1000.0),
                (p_min, min(p_max, 1000.0)),
                step=1.0,
            )

        search_name = st.text_input("Recherche dans le nom")

    fdf = df.copy()
    if brand_f  != "Toutes": fdf = fdf[fdf["brand_source"] == brand_f]
    if sexe_f   != "Tous":   fdf = fdf[fdf["sexe"]         == sexe_f]
    if cat_f    != "Toutes": fdf = fdf[fdf["categorie"]    == cat_f]
    if style_f  != "Tous":   fdf = fdf[fdf["style"]        == style_f]
    if len(prices) > 0:
        fdf = fdf[
            fdf["price_value"].isna() |
            ((fdf["price_value"] >= price_range[0]) & (fdf["price_value"] <= price_range[1]))
        ]
    if search_name:
        fdf = fdf[fdf["name"].str.contains(search_name, case=False, na=False)]

    st.write(f"**{len(fdf):,}** produits sur **{len(df):,}**")

    display_cols = ["brand_source", "name", "price_value", "sexe", "categorie",
                    "style", "color", "taille", "rating", "url"]
    available = [c for c in display_cols if c in fdf.columns]

    st.dataframe(
        fdf[available].head(1000),
        use_container_width=True,
        height=600,
        column_config={
            "brand_source": st.column_config.TextColumn("Marque"),
            "name":         st.column_config.TextColumn("Nom", width="large"),
            "price_value":  st.column_config.NumberColumn("Prix (€)", format="%.2f €"),
            "sexe":         st.column_config.TextColumn("Sexe"),
            "categorie":    st.column_config.TextColumn("Catégorie"),
            "style":        st.column_config.TextColumn("Style"),
            "color":        st.column_config.TextColumn("Couleur"),
            "rating":       st.column_config.NumberColumn("Note", format="%.1f ⭐"),
            "url":          st.column_config.LinkColumn("URL"),
        },
    )

    if st.button("📥 Télécharger la sélection (CSV)"):
        csv = fdf[available].to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇ Télécharger CSV",
            csv,
            file_name=f"smartwear_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
        )


# ══════════════════════════════════════════════════════════════════
#  PAGE : QUALITÉ
# ══════════════════════════════════════════════════════════════════
elif page == "🔬 Qualité":
    st.title("🔬 Audit & Contrôles qualité")

    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Audit des données")
        st.write("Déduplique, corrige les catégories, nettoie les descriptions.")
        if st.button("🔍 Lancer l'audit", type="primary", use_container_width=True):
            with st.spinner("Audit en cours…"):
                from pipeline.audit import run_audit
                st.session_state.audit_stats = run_audit()
                load_db.clear()  # invalider le cache DB

    with col2:
        st.subheader("Contrôles qualité")
        st.write("Vérifie les incohérences style / catégorie / type.")
        if st.button("🔬 Lancer les checks", use_container_width=True):
            with st.spinner("Checks en cours…"):
                from pipeline.check import run_check
                st.session_state.check_anomalies = run_check()

    st.divider()

    # Résultats audit
    if st.session_state.audit_stats:
        s = st.session_state.audit_stats
        st.subheader("Résultats de l'audit")
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Produits initiaux",      s.get("total_initial", 0))
        c2.metric("Doublons supprimés",     s.get("dupes_removed", 0),  delta_color="inverse")
        c3.metric("Descriptions nettoyées", s.get("desc_fixed", 0))
        c4.metric("Sexe inférés",           s.get("sexe_fixed", 0))
        c5.metric("Produits finaux",        s.get("total_final", 0))

    # Résultats checks
    if st.session_state.check_anomalies is not None:
        st.subheader("Résultats des contrôles")
        anomalies = st.session_state.check_anomalies
        if not anomalies:
            st.success("✅ Aucune anomalie détectée !")
        else:
            st.warning(f"⚠️ {len(anomalies)} type(s) d'anomalies")
            for a in anomalies:
                with st.expander(f"⚠️ {a['label']} — **{a['count']}** cas"):
                    for p in a.get("samples", []):
                        st.markdown(
                            f"- `[{p.get('brand_source')}]` **{str(p.get('name',''))[:55]}**"
                            f" | style=`{p.get('style')}` | catégorie=`{p.get('categorie')}`"
                        )

    # Aperçu stats DB
    st.divider()
    st.subheader("Aperçu de la base")
    products = load_db()
    if products:
        df = pd.DataFrame(products)
        completeness = {
            col: round(df[col].notna().mean() * 100, 1)
            for col in ["name", "price_value", "description", "image",
                        "color", "rating", "sexe", "categorie", "style"]
            if col in df.columns
        }
        df_comp = pd.DataFrame(
            list(completeness.items()), columns=["Champ", "Complétude (%)"]
        ).sort_values("Complétude (%)", ascending=True)
        fig = px.bar(
            df_comp, x="Complétude (%)", y="Champ", orientation="h",
            color="Complétude (%)",
            color_continuous_scale=[[0, "#ef4444"], [0.5, "#f59e0b"], [1, "#10b981"]],
            range_color=[0, 100],
        )
        fig.update_layout(coloraxis_showscale=False)
        _layout(fig, "Complétude des champs (%)")
        st.plotly_chart(fig, use_container_width=True)
