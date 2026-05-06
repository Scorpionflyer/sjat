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


# ── Column name resolution ────────────────────────────────────────────────────
_COL_ALIASES = {
    "Aasta":         ["Aasta", "aasta", "AASTA", "Year", "year"],
    "Maakond":       ["Maakond", "maakond", "MAAKOND", "County", "county"],
    "Sugu":          ["Sugu", "sugu", "SUGU", "Sex", "sex"],
    "Loomulik iive": ["Loomulik iive", "Loomulik iive kokku", "Natural increase"],
}

def resolve_col(df: pd.DataFrame, candidates: list) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise KeyError(f"None of {candidates} found in columns: {list(df.columns)}")


# ── Merge ─────────────────────────────────────────────────────────────────────
def normalize_name(name: str) -> str:
    return str(name).lower().replace(" maakond", "").replace("maa", "").strip()


def merge_data(gdf: gpd.GeoDataFrame, df: pd.DataFrame, year: int, sugu: str) -> gpd.GeoDataFrame:
    col_aasta   = resolve_col(df, _COL_ALIASES["Aasta"])
    col_sugu    = resolve_col(df, _COL_ALIASES["Sugu"])
    col_maakond = resolve_col(df, _COL_ALIASES["Maakond"])
    col_iive    = resolve_col(df, _COL_ALIASES["Loomulik iive"])

    # Year may be stored as string in the CSV
    year_val = str(year) if df[col_aasta].dtype == object else year

    subset = df[(df[col_aasta] == year_val) & (df[col_sugu] == sugu)].copy()
    subset = subset.rename(columns={col_maakond: "Maakond", col_iive: "Loomulik iive"})

    # EHAK / nutiteq GeoJSON county name column
    name_col = next(
        (c for c in ("MNIMI", "NIMI", "NAME", "maakond") if c in gdf.columns),
        [c for c in gdf.columns if c != "geometry"][0],
    )

    # Dissolve to county level if geometry has sub-county rows
    if "MKOOD" in gdf.columns:
        geo = gdf.dissolve(by=name_col).reset_index()
    else:
        geo = gdf.copy()

    geo = geo.copy()
    geo["_key"]    = geo[name_col].apply(normalize_name)
    subset["_key"] = subset["Maakond"].apply(normalize_name)

    merged = geo.merge(subset[["_key", "Maakond", "Loomulik iive"]], on="_key", how="left")
    merged.drop(columns=["_key"], inplace=True)
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
    year = st.slider("Aasta", min_value=2014, max_value=2023, value=2023, step=1)
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
