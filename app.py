# --- Scan UI
st.subheader("🔎 Scan")
st.caption("Astuce : ton scanner USB envoie le code comme du texte + ENTER. Clique dans le champ puis scanne en boucle.")

scan_col1, scan_col2 = st.columns([2, 1])

def register_scan(raw_code: str, add_qty: int):
    raw_code = normalize_code(raw_code)
    if not raw_code:
        return

    ts = datetime.now().isoformat(timespec="seconds")

    if raw_code in alias_map:
        ean1 = alias_map[raw_code]
        st.session_state.counts[ean1] = st.session_state.counts.get(ean1, 0) + int(add_qty)
        st.session_state.scan_log.append({
            "timestamp": ts,
            "code_scanné": raw_code,
            "ean1_resolu": ean1,
            "quantité": int(add_qty),
            "statut": "OK"
        })
        prod = products.loc[products["EAN 1"] == ean1].iloc[0]
        st.toast(f"✅ {prod['Name']} ({prod['Reference']}) +{add_qty}", icon="✅")
    else:
        st.session_state.unknown[raw_code] = st.session_state.unknown.get(raw_code, 0) + int(add_qty)
        st.session_state.scan_log.append({
            "timestamp": ts,
            "code_scanné": raw_code,
            "ean1_resolu": "",
            "quantité": int(add_qty),
            "statut": "INCONNU"
        })
        st.toast(f"⚠️ Code inconnu : {raw_code} (+{add_qty})", icon="⚠️")

with st.form("scan_form", clear_on_submit=True):
    with scan_col1:
        code = st.text_input("Code scanné (EAN1 ou EAN2)", value="", placeholder="Scanne ici…")
    with scan_col2:
        qty = st.number_input("Quantité à ajouter", min_value=1, value=1, step=1)

    submitted = st.form_submit_button("Ajouter le scan", type="primary")

if submitted:
    register_scan(code, qty)
