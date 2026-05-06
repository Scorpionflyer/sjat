import io
import requests
import pandas as pd
from io import StringIO
import json
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import streamlit as st

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Loomulik iive Eestis", page_icon="🗺️", layout="wide")

# ── Constants ─────────────────────────────────────────────────────────────────
STATISTIKAAMETI_API_URL = "https://andmed.stat.ee/api/v1/et/stat/RV032"
GEOJSON_URL = "https://gist.githubusercontent.com/nutiteq/1ab8f24f9a6ad2bb47da/raw/b89bfd350842b662099131e442488eeac453f8e5/maakonnad.geojson"

JSON_PAYLOAD = {
    "query": [
        {"code": "Aasta",   "selection": {"filter": "item", "values": ["2014","2015","2016","2017","2018","2019","2020","2021","2022","2023"]}},
        {"code": "Maakond", "selection": {"filter": "item", "values": ["39","44","49","51","57","59","65","67","70","74","78","82","84","86","37"]}},
        {"code": "Sugu",    "selection": {"filter": "item", "values": ["2","3"]}},
    ],
    "response": {"format": "csv"},
}

# ── Data loading ──────────────────────────────────────────────────────────────
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

    # PX-Web APIs sometimes use semicolons — detect the delimiter
    first_line = text.split("\n")[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","

    df = pd.read_csv(StringIO(text), sep=sep)
    # Strip stray whitespace or quotes from column names
    df.columns = [c.strip().strip('"') for c in df.columns]
    return df


@st.cache_data(show_spinner="Laen kaardiandmeid…")
def load_geodata() -> gpd.GeoDataFrame:
    resp = requests.get(GEOJSON_URL, timeout=30)
    resp.raise_for_status()
    return gpd.read_file(io.StringIO(resp.text))


# ── Merge ─────────────────────────────────────────────────────────────────────
def merge_data(gdf: gpd.GeoDataFrame, df: pd.DataFrame, year: int, sugu: str) -> gpd.GeoDataFrame:
    # API returns wide format: sex is encoded in column names, not a separate column
    # e.g. "Mehed Loomulik iive" / "Naised Loomulik iive"
    iive_col = f"{sugu} Loomulik iive"

    year_val = str(year) if df["Aasta"].dtype == object else year
    subset = df[df["Aasta"] == year_val][["Maakond", iive_col]].copy()
    subset = subset.rename(columns={iive_col: "Loomulik iive"})

    # MNIMI in GeoJSON matches "Harju maakond" format exactly — direct join
    geo = gdf.dissolve(by="MNIMI").reset_index() if "MKOOD" in gdf.columns else gdf.copy()

    merged = geo.merge(subset, left_on="MNIMI", right_on="Maakond", how="left")
    return merged


# ── Plot ──────────────────────────────────────────────────────────────────────
def make_choropleth(merged: gpd.GeoDataFrame, year: int, sugu: str) -> plt.Figure:
    col = "Loomulik iive"
    vmin = merged[col].min()
    vmax = merged[col].max()

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
        column=col, ax=ax, legend=True, cmap=cmap, norm=norm,
        edgecolor="#333333", linewidth=0.6,
        missing_kwds={"color": "#2a2a2a", "label": "Andmed puuduvad"},
        legend_kwds={"label": col, "orientation": "horizontal", "shrink": 0.6, "pad": 0.02},
    )

    for _, row in merged.iterrows():
        if row.geometry is None:
            continue
        centroid = row.geometry.centroid
        name  = row.get("Maakond", "")
        value = row.get(col, None)
        if pd.notna(value):
            ax.annotate(
                f"{name}\n{int(value):+}",
                xy=(centroid.x, centroid.y),
                ha="center", va="center",
                fontsize=6.5, color="white", fontweight="bold",
            )

    ax.set_title(f"Loomulik iive maakonniti — {year} ({sugu})", fontsize=15, color="white", pad=14)
    ax.axis("off")

    for text in fig.findobj(plt.Text):
        text.set_color("white")
    for cba in [a for a in fig.axes if a is not ax]:
        cba.tick_params(colors="white", labelsize=8)
        plt.setp(plt.getp(cba, "xticklabels"), color="white")
        cba.set_facecolor("#0e1117")

    plt.tight_layout()
    return fig


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("🗺️ Loomulik iive Eestis")
st.caption("Andmeallikas: Statistikaamet · RV032")

with st.sidebar:
    st.header("Filtrid")
    year = st.sidebar.selectbox("Aasta", options=list(range(2014, 2024)), index=9)
    sugu = st.radio("Sugu", options=["Mehed", "Naised"], index=0)
    st.divider()
    show_table = st.checkbox("Näita andmetabelit", value=False)
    show_debug = st.checkbox("Silumine", value=False)

# Load
try:
    df  = load_statistics()
    gdf = load_geodata()
except requests.HTTPError as e:
    st.error(f"API päring ebaõnnestus: {e}")
    st.stop()
except Exception as e:
    st.error(f"Viga andmete laadimisel: {e}")
    st.stop()

if show_debug:
    with st.expander("🔍 Silumine", expanded=True):
        st.write("**Statistika veergude nimed:**", list(df.columns))
        st.write("**GeoJSON veergude nimed:**", [c for c in gdf.columns if c != "geometry"])
        st.dataframe(df.head(5))

# Merge & plot
try:
    merged = merge_data(gdf, df, year, sugu)
except KeyError as e:
    st.error(f"Veergude ühendamine ebaõnnestus: {e}")
    st.info("Luba 'Silumine' külgribal, et näha tegelikke veerunimesid.")
    st.stop()

c1, c2, c3 = st.columns(3)
total    = merged["Loomulik iive"].sum()
positive = int((merged["Loomulik iive"] > 0).sum())
negative = int((merged["Loomulik iive"] < 0).sum())
c1.metric("Kokku (kõik maakonnad)", f"{int(total):+}")
c2.metric("Positiivne iive", f"{positive} maakonda")
c3.metric("Negatiivne iive", f"{negative} maakonda")

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
