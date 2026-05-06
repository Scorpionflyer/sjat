import requests
import pandas as pd
from io import StringIO
import json
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import streamlit as st

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Loomulik iive Eestis",
    page_icon="🗺️",
    layout="wide",
)

# ── Constants ─────────────────────────────────────────────────────────────────
STATISTIKAAMETI_API_URL = "https://andmed.stat.ee/api/v1/et/stat/RV032"
GEOJSON_URL = "https://gist.githubusercontent.com/nutiteq/1ab8f24f9a6ad2bb47da/raw/b89bfd350842b662099131e442488eeac453f8e5/maakonnad.geojson"

JSON_PAYLOAD = {
    "query": [
        {
            "code": "Aasta",
            "selection": {
                "filter": "item",
                "values": ["2014","2015","2016","2017","2018","2019","2020","2021","2022","2023"],
            },
        },
        {
            "code": "Maakond",
            "selection": {
                "filter": "item",
                "values": ["39","44","49","51","57","59","65","67","70","74","78","82","84","86","37"],
            },
        },
        {
            "code": "Sugu",
            "selection": {"filter": "item", "values": ["2", "3"]},
        },
    ],
    "response": {"format": "csv"},
}

SUGU_LABELS = {"Mehed": "Mehed", "Naised": "Naised"}

# ── Data loading (cached) ─────────────────────────────────────────────────────
@st.cache_data(show_spinner="Laen andmeid Statistikaametist…")
def load_statistics() -> pd.DataFrame:
    response = requests.post(
        STATISTIKAAMETI_API_URL,
        json=JSON_PAYLOAD,
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    text = response.content.decode("utf-8-sig")
    return pd.read_csv(StringIO(text))


@st.cache_data(show_spinner="Laen kaardiandmeid…")
def load_geodata() -> gpd.GeoDataFrame:
    resp = requests.get(GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    import io
    return gpd.read_file(io.StringIO(resp.text))


def normalize_name(name: str) -> str:
    """Lowercase and strip common suffixes for fuzzy county name matching."""
    return str(name).lower().replace(" maakond", "").replace("maa", "").strip()


def merge_data(gdf: gpd.GeoDataFrame, df: pd.DataFrame, year: int, sugu: str) -> gpd.GeoDataFrame:
    """Filter stats by year & sex, then join onto the GeoDataFrame."""
    subset = df[(df["Aasta"] == year) & (df["Sugu"] == sugu)].copy()

    # EHAK GeoJSON uses MNIMI for county name
    name_col = "MNIMI" if "MNIMI" in gdf.columns else next(
        (c for c in gdf.columns if c != "geometry"), gdf.columns[0]
    )

    # Dissolve to county level if GeoJSON has municipality-level rows
    if "MKOOD" in gdf.columns:
        geo_counties = gdf.dissolve(by=name_col).reset_index()
    else:
        geo_counties = gdf.copy()

    # Normalised join to handle "Harju maakond" vs "Harjumaa" etc.
    geo_counties = geo_counties.copy()
    geo_counties["_key"] = geo_counties[name_col].apply(normalize_name)
    subset = subset.copy()
    subset["_key"] = subset["Maakond"].apply(normalize_name)

    merged = geo_counties.merge(
        subset[["_key", "Maakond", "Loomulik iive"]], on="_key", how="left"
    )
    merged.drop(columns=["_key"], inplace=True)
    return merged


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_choropleth(merged: gpd.GeoDataFrame, year: int, sugu: str) -> plt.Figure:
    col = "Loomulik iive"

    vmin = merged[col].min()
    vmax = merged[col].max()
    # Use a diverging colormap centred at 0 if range crosses zero
    if vmin < 0 < vmax:
        cmap = "RdYlGn"
        norm = mcolors.TwoSlopeNorm(vmin=vmin, vcenter=0, vmax=vmax)
    else:
        cmap = "YlGn" if vmin >= 0 else "OrRd_r"
        norm = None

    fig, ax = plt.subplots(figsize=(11, 8))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")

    merged.plot(
        column=col,
        ax=ax,
        legend=True,
        cmap=cmap,
        norm=norm,
        edgecolor="#333333",
        linewidth=0.6,
        missing_kwds={"color": "#2a2a2a", "label": "Andmed puuduvad"},
        legend_kwds={
            "label": col,
            "orientation": "horizontal",
            "shrink": 0.6,
            "pad": 0.02,
        },
    )

    # County labels
    for _, row in merged.iterrows():
        if row.geometry is None:
            continue
        centroid = row.geometry.centroid
        name = row.get("Maakond", "")
        value = row.get(col, None)
        if pd.notna(value):
            ax.annotate(
                f"{name}\n{int(value):+}",
                xy=(centroid.x, centroid.y),
                ha="center",
                va="center",
                fontsize=6.5,
                color="white",
                fontweight="bold",
            )

    ax.set_title(
        f"Loomulik iive maakonniti — {year} ({sugu})",
        fontsize=15,
        color="white",
        pad=14,
    )
    ax.axis("off")

    # Style the colorbar
    for text in ax.get_figure().findobj(plt.Text):
        text.set_color("white")
    cb = [a for a in fig.axes if a is not ax]
    for cba in cb:
        cba.tick_params(colors="white", labelsize=8)
        plt.setp(plt.getp(cba, "xticklabels"), color="white")
        cba.set_facecolor("#0e1117")

    plt.tight_layout()
    return fig


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("🗺️ Loomulik iive Eestis")
st.caption("Andmeallikas: Statistikaamet · RV032")

# Sidebar controls
with st.sidebar:
    st.header("Filtrid")

    year = st.slider("Aasta", min_value=2014, max_value=2023, value=2023, step=1)

    sugu = st.radio("Sugu", options=["Mehed", "Naised"], index=0)

    st.divider()
    show_table = st.checkbox("Näita andmetabelit", value=False)

# Load data
try:
    df = load_statistics()
    gdf = load_geodata()
except requests.HTTPError as e:
    st.error(f"API päring ebaõnnestus: {e}")
    st.stop()
except Exception as e:
    st.error(f"Viga andmete laadimisel: {e}")
    st.stop()

# Merge & plot
merged = merge_data(gdf, df, year, sugu)

col1, col2, col3 = st.columns(3)
total = merged["Loomulik iive"].sum()
positive = (merged["Loomulik iive"] > 0).sum()
negative = (merged["Loomulik iive"] < 0).sum()
col1.metric("Kokku (kõik maakonnad)", f"{int(total):+}")
col2.metric("Positiivne iive", f"{positive} maakonda")
col3.metric("Negatiivne iive", f"{negative} maakonda")

st.divider()

fig = make_choropleth(merged, year, sugu)
st.pyplot(fig, use_container_width=True)

if show_table:
    st.subheader("Andmetabel")
    table = (
        merged[["Maakond", "Loomulik iive"]]
        .dropna()
        .sort_values("Loomulik iive", ascending=False)
        .reset_index(drop=True)
    )
    st.dataframe(table, use_container_width=True, height=460)
