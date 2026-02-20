import streamlit as st
import pandas as pd
from datetime import datetime
import base64

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

def product_label(row: pd.Series) -> str:
    size = (row.get("Taille", "") or "").strip()
    shoe = (row.get("Pointure", "") or "").strip()
    if size and shoe:
        return f"Taille {size} / Pointure {shoe}"
    if size:
        return f"Taille {size}"
    if shoe:
        return f"Pointure {shoe}"
    return ""

# --- Sons (bips) : petits WAV en base64
# (Sons simples; si tu veux un vrai "bip scanner", je peux te mettre un autre wav)
SOUND_OK_WAV_B64 = (
    "UklGRrQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YZAAAAA="
)
SOUND_ERR_WAV_B64 = (
    "UklGRrQAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YbAAAAA="
)

def play_sound(kind: str):
    # Certains navigateurs bloquent autoplay sans interaction utilisateur
    if not st.session_state.get("sound_enabled", False):
        return
    b64 = SOUND_OK_WAV_B64 if kind == "ok" else SOUND_ERR_WAV_B64
    audio_html = f"""
    <audio autoplay>
      <source src="data:audio/wav;base64,{b64}" type="audio/wav">
    </audio>
    """
    st.components.v1.html(audio_html, height=0)

def init_state():
    if "products" not in st.session_state:
        st.session_state.products = None
    if "alias_map" not in st.session_state:
        st.session_state.alias_map = {}

    if "sessions" not in st.session_state:
        st.session_state.sessions = {
            "Inventaire 1": {"counts": {}, "scan_log": [], "unknown": {}}
        }
    if "current_session" not in st.session_state:
        st.session_state.current_session = "Inventaire 1"

    if "last_scan" not in st.session_state:
        st.session_state.last_scan = {"status": None, "message": ""}

    if "scan_code" not in st.session_state:
        st.session_state.scan_code = ""

    if "add_qty" not in st.session_state:
        st.session_state.add_qty = 1

    if "sound_enabled" not in st.session_state:
        st.session_state.sound_enabled = False

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
cA, cB = st.sidebar.columns(2)
with cA:
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
with cB:
    if st.button("🧹 Reset", use_container_width=True):
        st.session_state.sessions[st.session_state.current_session] = {"counts": {}, "scan_log": [], "unknown": {}}
        st.sidebar.success("Dossier réinitialisé.")

# Supprimer dossier
st.sidebar.caption("⚠️ Suppression irréversible du dossier.")
can_delete = len(st.session_state.sessions) > 1
if st.sidebar.button("🗑️ Supprimer ce dossier", use_container_width=True, disabled=not can_delete):
    to_del = st.session_state.current_session
    if len(st.session_state.sessions) <= 1:
        st.sidebar.warning("Impossible de supprimer le dernier dossier.")
    else:
        st.session_state.sessions.pop(to_del, None)
        st.session_state.current_session = list(st.session_state.sessions.keys())[0]
        st.sidebar.success(f"Dossier supprimé : {to_del}")
        st.rerun()

st.sidebar.divider()
st.sidebar.subheader("🔊 Sons")
st.session_state.sound_enabled = st.sidebar.checkbox("Activer sons OK/Erreur", value=st.session_state.sound_enabled)

# Raccourcis vers dossier courant
cur = st.session_state.sessions[st.session_state.current_session]
counts = cur["counts"]
scan_log = cur["scan_log"]
unknown = cur["unknown"]

# ---------------- Fonctions scan / retirer ----------------
def register_scan(raw_code: str, qty: int = 1):
    code = normalize_code(raw_code)
    if not code:
        return

    qty = int(qty)
    if qty <= 0:
        qty = 1

    ts = datetime.now().isoformat(timespec="seconds")

    if code in alias_map:
        ean1 = alias_map[code]
        is_alias = (code != ean1)
        counts[ean1] = counts.get(ean1, 0) + qty

        prod = products.loc[products["EAN 1"] == ean1].iloc[0]
        extra = product_label(prod)
        alias_txt = f" (alias {code} → {ean1})" if is_alias else f" ({ean1})"
        msg = f"✅ +{qty} — {prod['Name']} — {prod['Couleur']} — {extra}{alias_txt}"

        scan_log.append({
            "timestamp": ts,
            "action": "ADD",
            "code_scanné": code,
            "ean1": ean1,
            "qty": qty
        })

        st.session_state.last_scan = {"status": "ok", "message": msg}
        st.toast(msg, icon="✅")
        play_sound("ok")
    else:
        unknown[code] = unknown.get(code, 0) + qty
        msg = f"⛔ +{qty} — Code inconnu : {code}"

        scan_log.append({
            "timestamp": ts,
            "action": "UNKNOWN",
            "code_scanné": code,
            "ean1": "",
            "qty": qty
        })

        st.session_state.last_scan = {"status": "err", "message": msg}
        st.toast(msg, icon="⛔")
        play_sound("err")

def remove_qty(ean1: str, qty: int):
    qty = int(qty)
    if qty <= 0:
        return
    if ean1 not in counts:
        return

    counts[ean1] -= qty
    if counts[ean1] <= 0:
        counts.pop(ean1, None)

    ts = datetime.now().isoformat(timespec="seconds")
    scan_log.append({
        "timestamp": ts,
        "action": "REMOVE",
        "code_scanné": "",
        "ean1": ean1,
        "qty": qty
    })

    prod = products.loc[products["EAN 1"] == ean1].iloc[0]
    extra = product_label(prod)
    msg = f"➖ -{qty} — {prod['Name']} — {prod['Couleur']} — {extra} ({ean1})"
    st.session_state.last_scan = {"status": "ok", "message": msg}
    st.toast(msg, icon="➖")
    play_sound("ok")

# ---------------- UI Scan (ajout direct) ----------------
st.subheader("🔎 Scan (ajout direct)")

last = st.session_state.last_scan
if last["status"] == "ok":
    st.success(last["message"])
elif last["status"] == "err":
    st.error(last["message"])
else:
    st.info("Clique dans le champ puis scanne. Le scan s’ajoute automatiquement.")

c1, c2 = st.columns([2, 1])

with c2:
    st.number_input("Quantité ajout", min_value=1, value=st.session_state.add_qty, step=1, key="add_qty")

def on_scan_change():
    code = st.session_state.scan_code
    register_scan(code, qty=st.session_state.add_qty)
    st.session_state.scan_code = ""

with c1:
    st.text_input(
        "Champ de scan (ton scanner agit comme un clavier)",
        key="scan_code",
        placeholder="Scanne ici…",
        on_change=on_scan_change
    )

st.caption("Si ton scanner n’envoie pas ENTER, configure-le pour suffixer un retour (CR/LF).")

# ---------------- Affichage uniquement des articles scannés ----------------
st.divider()
st.subheader(f"📋 Articles scannés — {st.session_state.current_session}")

scanned_ean1 = [ean for ean, q in counts.items() if q > 0]
if not scanned_ean1:
    st.info("Aucun article scanné pour l’instant.")
else:
    subset = products[products["EAN 1"].isin(scanned_ean1)].copy()
    subset["Quantite"] = subset["EAN 1"].map(counts).fillna(0).astype(int)
    subset = subset.sort_values(["Quantite", "Reference"], ascending=[False, True])

    header = st.columns([2, 3, 2, 2, 1, 1, 1])
    header[0].markdown("**EAN 1**")
    header[1].markdown("**Produit**")
    header[2].markdown("**Couleur**")
    header[3].markdown("**Taille / Pointure**")
    header[4].markdown("**Qté**")
    header[5].markdown("**Retirer**")
    header[6].markdown("**Action**")

    for _, row in subset.iterrows():
        ean1 = row["EAN 1"]
        extra = product_label(row)

        cols = st.columns([2, 3, 2, 2, 1, 1, 1])
        cols[0].write(ean1)
        cols[1].write(f"{row['Name']}  ({row['Reference']})")
        cols[2].write(row["Couleur"])
        cols[3].write(extra)
        cols[4].write(int(row["Quantite"]))

        # quantité à retirer par ligne (clé unique)
        qty_key = f"rmqty_{st.session_state.current_session}_{ean1}"
        if qty_key not in st.session_state:
            st.session_state[qty_key] = 1

        cols[5].number_input("", min_value=1, value=st.session_state[qty_key], step=1, key=qty_key, label_visibility="collapsed")

        if cols[6].button("Retirer", key=f"removebtn_{st.session_state.current_session}_{ean1}"):
            remove_qty(ean1, st.session_state[qty_key])
            st.rerun()

    st.divider()

    # Exports
    ex1, ex2, ex3 = st.columns([1, 1, 1])
    with ex1:
        st.download_button(
            "⬇️ Export inventaire (scannés)",
            data=subset.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"inventaire_{st.session_state.current_session}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with ex2:
        log_df = pd.DataFrame(scan_log)
        st.download_button(
            "⬇️ Export journal scans",
            data=log_df.to_csv(index=False).encode("utf-8-sig") if not log_df.empty else "timestamp,action,code_scanné,ean1,qty\n",
            file_name=f"scan_log_{st.session_state.current_session}.csv",
            mime="text/csv",
            use_container_width=True
        )
    with ex3:
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

with st.expander("⚠️ Voir les codes inconnus"):
    if unknown:
        unk_df = pd.DataFrame([{"code_scanné": k, "quantite": v} for k, v in unknown.items()]).sort_values("quantite", ascending=False)
        st.dataframe(unk_df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun code inconnu.")
