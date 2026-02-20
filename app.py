import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Inventaire scan EAN", layout="wide")

st.title("📦 Inventaire — Scan EAN → Compteur → Export CSV")

REQUIRED_COLS = ["EAN 1", "EAN 2", "Reference", "Name", "Couleur", "Taille", "Pointure"]

def normalize_code(x):
    if pd.isna(x):
        return ""
    return str(x).strip().replace(" ", "").replace("\n", "").replace("\r", "")

def load_products(file):
    df = pd.read_csv(file, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        st.error(f"Colonnes manquantes : {missing}")
        st.stop()

    df["EAN 1"] = df["EAN 1"].apply(normalize_code)
    df["EAN 2"] = df["EAN 2"].apply(normalize_code)

    return df

def build_alias_map(df):
    alias_map = {}
    for _, row in df.iterrows():
        if row["EAN 1"]:
            alias_map[row["EAN 1"]] = row["EAN 1"]
        if row["EAN 2"]:
            alias_map[row["EAN 2"]] = row["EAN 1"]
    return alias_map

# ---------------- Session State ----------------
if "counts" not in st.session_state:
    st.session_state.counts = {}

if "scan_log" not in st.session_state:
    st.session_state.scan_log = []

if "unknown" not in st.session_state:
    st.session_state.unknown = {}

# ---------------- Upload CSV ----------------
st.sidebar.header("⚙️ Charger les produits")

file = st.sidebar.file_uploader("Importer produits.csv", type=["csv"])

if file:
    products = load_products(file)
    alias_map = build_alias_map(products)
else:
    st.warning("Importe ton fichier produits.csv")
    st.stop()

# ---------------- Fonction scan ----------------
def register_scan(code, qty):
    code = normalize_code(code)
    if not code:
        return

    ts = datetime.now().isoformat(timespec="seconds")

    if code in alias_map:
        ean1 = alias_map[code]
        st.session_state.counts[ean1] = st.session_state.counts.get(ean1, 0) + qty

        st.session_state.scan_log.append({
            "timestamp": ts,
            "code_scanné": code,
            "ean1": ean1,
            "qty": qty
        })

        prod = products.loc[products["EAN 1"] == ean1].iloc[0]
        st.success(f"{prod['Name']} +{qty}")

    else:
        st.session_state.unknown[code] = st.session_state.unknown.get(code, 0) + qty
        st.warning(f"Code inconnu : {code}")

# ---------------- UI Scan ----------------
st.subheader("🔎 Scan")

with st.form("scan_form", clear_on_submit=True):
    code = st.text_input("Scanner ici")
    qty = st.number_input("Quantité", min_value=1, value=1)

    submitted = st.form_submit_button("Ajouter")

if submitted:
    register_scan(code, qty)

# ---------------- Résultats ----------------
st.subheader("📊 Inventaire")

result = products.copy()
result["Quantite"] = result["EAN 1"].map(st.session_state.counts).fillna(0).astype(int)

st.dataframe(result)

st.download_button(
    "⬇️ Export CSV",
    data=result.to_csv(index=False).encode("utf-8-sig"),
    file_name="inventaire.csv",
    mime="text/csv"
)

# ---------------- Inconnus ----------------
st.subheader("⚠️ Codes inconnus")

if st.session_state.unknown:
    unk_df = pd.DataFrame(
        [{"Code": k, "Quantite": v} for k, v in st.session_state.unknown.items()]
    )
    st.dataframe(unk_df)

# ---------------- Log ----------------
st.subheader("🧾 Journal")

if st.session_state.scan_log:
    log_df = pd.DataFrame(st.session_state.scan_log)
    st.dataframe(log_df)
