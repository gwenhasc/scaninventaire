import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Inventaire scan EAN", layout="wide")
st.title("📦 Inventaire — Scan EAN → Compteur → Export CSV")

REQUIRED_COLS = ["EAN 1", "EAN 2", "Reference", "Name", "Couleur", "Taille", "Pointure"]

def normalize_code(x) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ""
    return str(x).strip().replace(" ", "").replace("\n", "").replace("\r", "")

def load_products(file) -> pd.DataFrame:
    df = pd.read_csv(file, dtype=str).fillna("")
    df.columns = [c.strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes : {missing}")
    df["EAN 1"] = df["EAN 1"].apply(normalize_code)
    df["EAN 2"] = df["EAN 2"].apply(normalize_code)

    if (df["EAN 1"] == "").any():
        raise ValueError("Certains produits ont un EAN 1 vide. EAN 1 est obligatoire.")
    if df["EAN 1"].duplicated().any():
        dups = df[df["EAN 1"].duplicated(keep=False)]["EAN 1"].unique().tolist()
        raise ValueError(f"Doublons détectés dans EAN 1 : {dups[:10]}{'...' if len(dups)>10 else ''}")
    return df

def build_alias_map(df: pd.DataFrame) -> dict:
    # code scanné (EAN1 ou EAN2) -> EAN1
    m = {}
    for _, row in df.iterrows():
        ean1 = row["EAN 1"]
        ean2 = row["EAN 2"]
        if ean1:
            m[ean1] = ean1
        if ean2:
            if ean2 in m and m[ean2] != ean1:
                raise ValueError(f"Conflit : EAN 2 '{ean2}' pointe vers plusieurs EAN 1 ({m[ean2]} et {ean1}).")
            m[ean2] = ean1
    return m

def init_state():
    if "products" not in st.session_state:
        st.session_state.products = None
    if "alias_map" not in st.session_state:
        st.session_state.alias_map = {}

    # Multi-dossiers (sessions)
    if "sessions" not in st.session_state:
        st.session_state.sessions = {
            "Inventaire 1": {"counts": {}, "scan_log": [], "unknown": {}}
        }
    if "current_session" not in st.session_state:
        st.session_state.current_session = "Inventaire 1"

    # Feedback dernier scan
    if "last_scan" not in st.session_state:
        st.session_state.last_scan = {"status": None, "message": ""}

    # Champ scan
    if "scan_code" not in st.session_state:
        st.session_state.scan_code = ""

init_state()

# ---------------- Sidebar: chargement produits + dossiers ----------------
st.sidebar.header("⚙️ Configuration")

prod_file = st.sidebar.file_uploader("Importer produits.csv", type=["csv"])

if prod_file is not None:
    try:
        products = load_products(prod_file)
        alias_map = build_alias_map(products)
        st.session_state.products = products
        st.session_state.alias_map = alias_map
        st.sidebar.success(f"Produits chargés : {len(products)}")
    except Exception as e:
        st.session_state.products = None
        st.session_state.alias_map = {}
        st.sidebar.error(str(e))

if st.session_state.products is None:
    st.warning("Importe ton fichier `produits.csv` pour commencer.")
    st.stop()

products = st.session_state.products
alias_map = st.session_state.alias_map

st.sidebar.divider()
st.sidebar.subheader("📁 Dossiers d’inventaire")

session_names = list(st.session_state.sessions.keys())
st.session_state.current_session = st.sidebar.selectbox(
    "Choisir un dossier",
    session_names,
    index=session_names.index(st.session_state.current_session) if st.session_state.current_session in session_names else 0
)

new_name = st.sidebar.text_input("Nouveau dossier", placeholder="Ex: Woluwe - 20/02")
colA, colB = st.sidebar.columns(2)
with colA:
    if st.button("➕ Créer", use_container_width=True):
        name = new_name.strip()
        if name and name not in st.session_state.sessions:
            st.session_state.sessions[name] = {"counts": {}, "scan_log": [], "unknown": {}}
            st.session_state.current_session = name
            st.sidebar.success("Dossier créé.")
        elif name in st.session_state.sessions:
            st.sidebar.warning("Ce dossier existe déjà.")
        else:
            st.sidebar.warning("Donne un nom au dossier.")
with colB:
    if st.button("🧹 Reset dossier", use_container_width=True):
        st.session_state.sessions[st.session_state.current_session] = {"counts": {}, "scan_log": [], "unknown": {}}
        st.sidebar.success("Dossier réinitialisé.")

# Raccourcis vers dossier courant
cur = st.session_state.sessions[st.session_state.current_session]
counts = cur["counts"]
scan_log = cur["scan_log"]
unknown = cur["unknown"]

# ---------------- Fonctions scan / retirer ----------------
def product_label(row: pd.Series) -> str:
    # Affiche Taille ou Pointure selon ce qui existe
    size = row.get("Taille", "").strip()
    shoe = row.get("Pointure", "").strip()
    if size and shoe:
        extra = f"Taille {size} / Pointure {shoe}"
    elif size:
        extra = f"Taille {size}"
    elif shoe:
        extra = f"Pointure {shoe}"
    else:
        extra = ""
    return extra

def register_scan(raw_code: str, qty: int = 1):
    code = normalize_code(raw_code)
    if not code:
        return

    ts = datetime.now().isoformat(timespec="seconds")

    if code in alias_map:
        ean1 = alias_map[code]
        is_alias = (code != ean1)

        counts[ean1] = counts.get(ean1, 0) + int(qty)

        # infos produit
        prod = products.loc[products["EAN 1"] == ean1].iloc[0]
        extra = product_label(prod)

        alias_txt = f" (alias {code} → {ean1})" if is_alias else f" ({ean1})"
        msg = f"✅ {prod['Name']} — {prod['Couleur']} — {extra}{alias_txt}  +{qty}"

        scan_log.append({
            "timestamp": ts,
            "action": "ADD",
            "code_scanné": code,
            "ean1": ean1,
            "qty": int(qty)
        })

        st.session_state.last_scan = {"status": "ok", "message": msg}
        st.toast(msg, icon="✅")
    else:
        unknown[code] = unknown.get(code, 0) + int(qty)
        msg = f"⛔ Code inconnu : {code}  +{qty}"
        scan_log.append({
            "timestamp": ts,
            "action": "UNKNOWN",
            "code_scanné": code,
            "ean1": "",
            "qty": int(qty)
        })
        st.session_state.last_scan = {"status": "err", "message": msg}
        st.toast(msg, icon="⛔")

def remove_one(ean1: str):
    if ean1 in counts:
        counts[ean1] -= 1
        if counts[ean1] <= 0:
            counts.pop(ean1, None)

        ts = datetime.now().isoformat(timespec="seconds")
        scan_log.append({
            "timestamp": ts,
            "action": "REMOVE",
            "code_scanné": "",
            "ean1": ean1,
            "qty": 1
        })

        prod = products.loc[products["EAN 1"] == ean1].iloc[0]
        extra = product_label(prod)
        msg = f"➖ Retiré 1 : {prod['Name']} — {prod['Couleur']} — {extra} ({ean1})"
        st.session_state.last_scan = {"status": "ok", "message": msg}
        st.toast(msg, icon="➖")

# ---------------- UI Scan (ajout direct) ----------------
st.subheader("🔎 Scan (ajout direct)")

# Bandeau dernier scan (vert/rouge)
last = st.session_state.last_scan
if last["status"] == "ok":
    st.success(last["message"])
elif last["status"] == "err":
    st.error(last["message"])
else:
    st.info("Clique dans le champ puis scanne. Le scan s’ajoute automatiquement.")

def on_scan_change():
    # Déclenché dès que le champ change (le scanner envoie généralement ENTER)
    code = st.session_state.scan_code
    register_scan(code, qty=1)
    # Reset du champ dans le callback (safe)
    st.session_state.scan_code = ""

st.text_input(
    "Champ de scan (ton scanner agit comme un clavier)",
    key="scan_code",
    placeholder="Scanne ici…",
    on_change=on_scan_change
)

st.caption("Astuce : si ton scanner n’envoie pas ENTER, configure-le pour suffixer un retour (CR/LF).")

# ---------------- Affichage uniquement des articles scannés ----------------
st.divider()
st.subheader(f"📋 Articles scannés — {st.session_state.current_session}")

scanned_ean1 = [ean for ean, q in counts.items() if q > 0]
if not scanned_ean1:
    st.info("Aucun article scanné pour l’instant.")
else:
    subset = products[products["EAN 1"].isin(scanned_ean1)].copy()
    subset["Quantite"] = subset["EAN 1"].map(counts).fillna(0).astype(int)

    # Tri: quantité décroissante puis référence
    subset = subset.sort_values(["Quantite", "Reference"], ascending=[False, True])

    # Affichage "liste" avec bouton Retirer
    header = st.columns([2, 3, 2, 2, 1, 1])
    header[0].markdown("**EAN 1**")
    header[1].markdown("**Produit**")
    header[2].markdown("**Couleur**")
    header[3].markdown("**Taille / Pointure**")
    header[4].markdown("**Qté**")
    header[5].markdown("**Retirer**")

    for _, row in subset.iterrows():
        ean1 = row["EAN 1"]
        extra = product_label(row)
        cols = st.columns([2, 3, 2, 2, 1, 1])
        cols[0].write(ean1)
        cols[1].write(f"{row['Name']}  ({row['Reference']})")
        cols[2].write(row["Couleur"])
        cols[3].write(extra)
        cols[4].write(int(row["Quantite"]))
        if cols[5].button("Retirer 1", key=f"remove_{st.session_state.current_session}_{ean1}"):
            remove_one(ean1)
            st.rerun()

    st.divider()

    # Exports
    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        st.download_button(
            "⬇️ Export inventaire (scannés)",
            data=subset.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"inventaire_{st.session_state.current_session}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with c2:
        log_df = pd.DataFrame(scan_log)
        st.download_button(
            "⬇️ Export journal scans",
            data=log_df.to_csv(index=False).encode("utf-8-sig") if not log_df.empty else "timestamp,action,code_scanné,ean1,qty\n",
            file_name=f"scan_log_{st.session_state.current_session}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with c3:
        unk_df = pd.DataFrame([{"code_scanné": k, "quantite": v} for k, v in unknown.items()]).sort_values(
            "quantite", ascending=False
        ) if unknown else pd.DataFrame(columns=["code_scanné", "quantite"])
        st.download_button(
            "⬇️ Export inconnus",
            data=unk_df.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"codes_inconnus_{st.session_state.current_session}.csv",
            mime="text/csv",
            use_container_width=True
        )

# ---------------- Optionnel : afficher inconnus ----------------
with st.expander("⚠️ Voir les codes inconnus"):
    if unknown:
        unk_df = pd.DataFrame([{"code_scanné": k, "quantite": v} for k, v in unknown.items()]).sort_values("quantite", ascending=False)
        st.dataframe(unk_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun code inconnu.")
