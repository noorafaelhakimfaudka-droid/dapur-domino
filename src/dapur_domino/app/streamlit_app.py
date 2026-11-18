"""Dapur Domino — Streamlit Arena (Modul D: FR-D1..FR-D5, NFR-3, NFR-5)."""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from dapur_domino.app.artifacts_loader import (
    build_recipe_graph_from_csv,
    clean_display_title,
    extract_region_wide_slice,
    find_latest_completed_run,
    format_tanggal_indo,
    load_json_dict,
    sanitize_ingredient_inputs,
)
from dapur_domino.bridge.scoring import (
    LIMITATION_DISCLAIMER,
    compute_commodity_price_metrics,
    compute_mapping_coverage,
    load_commodity_mapping,
    score_price_aware_substitutions,
)
from dapur_domino.config import load_config
from dapur_domino.ingest.manifest import verify_raw_manifest
from dapur_domino.ingest.pihps import PIHPS_CATEGORIES
from dapur_domino.recipes.embedding import suggest_recipes_from_fridge
from dapur_domino.recipes.network import recommend_complements_conditional
from dapur_domino.tracking import verify_run_manifest

REPO_ROOT = Path(
    os.environ.get("DAPUR_DOMINO_ROOT", str(Path(__file__).resolve().parents[3]))
)
STYLES_PATH = Path(__file__).with_name("styles.css")
NAV_OPTIONS = ["Ganti bahan", "Isi kulkasku", "Efek domino", "Metodologi"]

STAGE_LABELS = {
    "m1": "Pembersihan Data Harga",
    "m2": "Analisis Efek Domino",
    "m3": "Jaringan Resep Masakan",
    "m4": "Penghubung Harga & Resep",
}


def _esc(val: Any) -> str:
    """HTML-escape any dynamic value before rendering into custom HTML (NFR-5)."""
    return html.escape(str(val), quote=True)


def _fmt_int(val: int | float) -> str:
    return f"{int(round(float(val))):,}".replace(",", ".")


def _fmt_idr(val: float | None) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"Rp {int(round(float(val))):,}".replace(",", ".")


def _fmt_pct(val: float | None, *, signed: bool = True, digits: int = 2) -> str:
    if val is None or pd.isna(val):
        return "—"
    v = float(val)
    prefix = "+" if (signed and v > 0) else ""
    return f"{prefix}{v:.{digits}f}%".replace(".", ",")


def _fmt_dec(val: float | None, digits: int = 1) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"{float(val):.{digits}f}".replace(".", ",")


def _inject_styles() -> None:
    if STYLES_PATH.is_file():
        css = STYLES_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Memuat data Dapur Domino...")
def load_app_state() -> dict[str, Any]:
    """Load processed datasets and latest verified run manifests into bounded cache."""
    cfg_path = REPO_ROOT / "configs" / "default.yaml"
    cfg = load_config(cfg_path)
    runs_dir = REPO_ROOT / "artifacts" / "runs"

    m1_dir = find_latest_completed_run(runs_dir, "m1_prices")
    m2_dir = find_latest_completed_run(runs_dir, "m2_domino")
    m3_dir = find_latest_completed_run(runs_dir, "m3_recipes")
    m4_dir = find_latest_completed_run(runs_dir, "m4_bridge")

    px_dir = REPO_ROOT / "data" / "processed" / "prices"
    rec_dir = REPO_ROOT / "data" / "processed" / "recipes"

    px_nat = pd.read_parquet(px_dir / "prices_national_wide.parquet")
    ret_nat = pd.read_parquet(px_dir / "returns_national_wide.parquet")
    px_prov = pd.read_parquet(px_dir / "prices_province_wide.parquet")
    ret_prov = pd.read_parquet(px_dir / "returns_province_wide.parquet")

    subs_df = pd.read_parquet(rec_dir / "ingredient_substitutions.parquet")
    nodes_df = pd.read_csv(rec_dir / "ingredient_nodes.csv")
    edges_df = pd.read_csv(rec_dir / "ingredient_edges.csv")
    train_norm = pd.read_parquet(rec_dir / "train_normalized.parquet").copy()
    train_norm["clean_title"] = [
        clean_display_title(str(t)) for t in train_norm["title"].tolist()
    ]

    graph, _ = build_recipe_graph_from_csv(
        rec_dir / "ingredient_nodes.csv", rec_dir / "ingredient_edges.csv"
    )
    mapping = load_commodity_mapping(REPO_ROOT / str(cfg.bridge["mapping_file"]))

    vp1_path = REPO_ROOT / "artifacts" / "vp1_summary.json"
    vp1_summary = load_json_dict(vp1_path) if vp1_path.is_file() else None

    return {
        "cfg": cfg,
        "runs": {"m1": m1_dir, "m2": m2_dir, "m3": m3_dir, "m4": m4_dir},
        "px_nat": px_nat,
        "ret_nat": ret_nat,
        "px_prov": px_prov,
        "ret_prov": ret_prov,
        "subs_df": subs_df,
        "nodes_df": nodes_df,
        "edges_df": edges_df,
        "train_norm": train_norm,
        "graph": graph,
        "mapping": mapping,
        "vp1": vp1_summary,
    }


def _render_top_navbar() -> str:
    """Render top brand and horizontal pill navigation (no left sidebar)."""
    col_brand, col_nav = st.columns([1.1, 2.2])
    with col_brand:
        st.markdown(
            '<div class="dd-brand">'
            '<span class="dd-tile"><i></i><i></i></span>'
            "<span>Dapur Domino</span>"
            "</div>",
            unsafe_allow_html=True,
        )
    with col_nav:
        selected_page = st.radio(
            "Halaman",
            NAV_OPTIONS,
            horizontal=True,
            label_visibility="collapsed",
        )
    st.markdown('<hr class="dd-nav-divider">', unsafe_allow_html=True)
    return str(selected_page)


def _render_substitution_page(state: dict[str, Any]) -> None:
    st.markdown(
        '<h1 class="dd-h1">Cabai lagi mahal? Cari gantinya.</h1>'
        '<p class="dd-lead">'
        "Kandidat pengganti dinilai dari kemiripan pemakaiannya di ribuan resep "
        "Nusantara, lalu diurutkan dengan kestabilan harga terbaru."
        "</p>",
        unsafe_allow_html=True,
    )

    subs_df: pd.DataFrame = state["subs_df"]
    nodes_df: pd.DataFrame = state["nodes_df"]
    graph: nx.Graph[str] = state["graph"]
    mapping: dict[str, dict[str, str]] = state["mapping"]
    cfg = state["cfg"]
    w_s = float(cfg.bridge["weights"]["similarity"])
    w_p = float(cfg.bridge["weights"]["price"])

    px_prov: pd.DataFrame = state["px_prov"]
    provinces = sorted({str(c).split("__", 1)[1] for c in px_prov.columns if "__" in str(c)})
    c_sel1, c_sel2 = st.columns(2)
    with c_sel1:
        region_choice = st.selectbox(
            "Harga acuan wilayah", ["Nasional (Semua Provinsi)", *provinces]
        )
    with c_sel2:
        ingredients = sorted(subs_df["ingredient"].unique().tolist())
        default_idx = (
            ingredients.index("cabai merah keriting")
            if "cabai merah keriting" in ingredients
            else 0
        )
        target = st.selectbox("Bahan yang mau diganti", ingredients, index=default_idx)

    if region_choice == "Nasional (Semua Provinsi)":
        active_px_wide = state["px_nat"]
        metrics_df = compute_commodity_price_metrics(state["px_nat"], state["ret_nat"])
    else:
        active_px_wide = extract_region_wide_slice(px_prov, region_choice)
        sub_ret = extract_region_wide_slice(state["ret_prov"], region_choice)
        metrics_df = compute_commodity_price_metrics(active_px_wide, sub_ret)

    target_map = mapping.get(target.strip().lower())
    hl_comcat = target_map["comcat_id"] if target_map else None

    strip_cards: list[str] = []
    for _, prow in metrics_df.sort_values("latest_price_idr", ascending=False).iterrows():
        cid = str(prow["comcat_id"])
        cname = PIHPS_CATEGORIES.get(cid, cid)
        px_val = float(prow["latest_price_idr"])
        ch_val = float(prow["pct_change_30d"])
        ch_cls = "dd-up" if ch_val > 0 else ("dd-down" if ch_val < 0 else "dd-muted")
        hl_cls = "hl" if cid == hl_comcat else ""
        strip_cards.append(
            f'<div class="dd-pc {hl_cls}">'
            f"<b>{_esc(cname)}</b>"
            f"<span>{_esc(_fmt_idr(px_val))}</span>"
            f'<small class="{ch_cls}">{_esc(_fmt_pct(ch_val))} · 30 hari</small>'
            f"</div>"
        )
    st.markdown(f'<div class="dd-strip">{"".join(strip_cards)}</div>', unsafe_allow_html=True)

    ranked = score_price_aware_substitutions(
        target, subs_df, mapping, metrics_df, w_similarity=w_s, w_price=w_p
    )
    if not ranked:
        st.warning(f"Belum ada kandidat pengganti untuk '{target}'.")
        return

    first = ranked[0]
    latest_dt_indo = format_tanggal_indo(str(metrics_df["latest_date"].max()))
    if first["target_price_idr"] is not None:
        t_px_str = _fmt_idr(float(first["target_price_idr"]))
        t_ch_val = float(first["target_pct_change_30d"] or 0.0)
        t_ch_cls = "dd-up" if t_ch_val > 0 else ("dd-down" if t_ch_val < 0 else "dd-muted")
        t_sub = f'<p class="{t_ch_cls}">{_esc(_fmt_pct(t_ch_val))} dalam 30 hari kerja</p>'
    else:
        t_px_str = "Belum dipantau"
        t_sub = (
            '<p class="dd-muted"><span class="dd-pill dd-p-no">Harga belum tersedia</span> '
            "di luar 10 bahan pokok harian</p>"
        )

    w_s_pct = int(round(w_s * 100))
    w_p_pct = int(round(w_p * 100))
    st.markdown(
        '<div class="dd-grid dd-g3">'
        '<div class="dd-card">'
        f'<p class="dd-muted">Harga {_esc(target)}</p>'
        f'<div class="dd-big">{_esc(t_px_str)}</div>'
        f"{t_sub}"
        "</div>"
        '<div class="dd-card">'
        '<p class="dd-muted">Bobot penilaian</p>'
        f'<div class="dd-big">{w_s_pct}% / {w_p_pct}%</div>'
        '<p class="dd-muted">kecocokan resep / kestabilan harga</p>'
        "</div>"
        '<div class="dd-card">'
        '<p class="dd-muted">Data harga terbaru</p>'
        f'<div class="dd-big">{_esc(latest_dt_indo)}</div>'
        '<p class="dd-muted">hari kerja terakhir</p>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    has_mapped_candidate = any(item["price_status"] == "mapped" for item in ranked)
    if not has_mapped_candidate:
        st.markdown(
            '<div class="dd-note warn" style="margin:6px 0 16px 0">'
            "<b>Info Harga</b>"
            "<span>"
            "Kandidat pengganti di bawah belum tercakup dalam 10 bahan pokok harian Bank "
            "Indonesia, sehingga daftar diurutkan murni berdasar kecocokan resep tanpa "
            "perkiraan harga buatan."
            "</span>"
            "</div>",
            unsafe_allow_html=True,
        )

    dom_cards: list[str] = []
    for item in ranked:
        is_mapped = item["price_status"] == "mapped"
        dom_cls = "dd-dom" if is_mapped else "dd-dom un"
        cand_name = _esc(item["candidate"])
        sim_pct = _fmt_pct(float(item["recipe_sub_score"]) * 100.0, signed=False, digits=1)

        if is_mapped:
            c_name = _esc(item["commodity_name"])
            c_px = _fmt_idr(float(item["latest_price_idr"]))
            c_ch = float(item["pct_change_30d"])
            c_cls = "dd-up" if c_ch > 0 else ("dd-down" if c_ch < 0 else "dd-muted")
            status_line = (
                '<span class="dd-pill dd-p-ok">Harga tersedia</span> '
                f'<span class="dd-muted">{c_name} · {_esc(c_px)} · '
                f'<b class="{c_cls}">{_esc(_fmt_pct(c_ch))}</b></span>'
            )
            score_label = "Nilai rekomendasi"
            comb_val = float(item["combined_score"])
            score_str = _fmt_pct(comb_val * 100.0, signed=False, digits=1)
            width_pct = max(0.0, min(100.0, comb_val * 100.0))
            meter_html = f'<div class="dd-meter"><i style="width:{width_pct:.1f}%"></i></div>'
        else:
            status_line = (
                '<span class="dd-pill dd-p-no">Harga belum dipantau</span> '
                '<span class="dd-muted">'
                "Di luar 10 bahan pokok harian — skor gabungan tidak dihitung."
                "</span>"
            )
            score_label = "Kecocokan resep"
            score_str = sim_pct
            meter_html = '<small class="dd-muted">Harga BI belum tersedia</small>'

        dom_cards.append(
            f'<article class="{dom_cls}">'
            "<div>"
            f'<h3 class="dd-h3">{cand_name}</h3>'
            '<div class="dd-facts">'
            f"<span>Kecocokan peran di resep: <b>{_esc(sim_pct)}</b></span>"
            "</div>"
            f'<div style="margin-top:10px">{status_line}</div>'
            "</div>"
            "<div>"
            f'<span class="dd-muted">{score_label}</span>'
            f'<div class="dd-score">{_esc(score_str)}</div>'
            f"{meter_html}"
            "</div>"
            "</article>"
        )

    st.markdown("".join(dom_cards), unsafe_allow_html=True)

    # Rich context from existing data: 90-day price trend & recipe companions
    c_ctx1, c_ctx2 = st.columns(2)
    with c_ctx1:
        if hl_comcat is not None:
            col_matches = [
                c for c in active_px_wide.columns if str(c).startswith(f"{hl_comcat}__")
            ]
            if col_matches:
                s_hist = active_px_wide[col_matches[0]].dropna().tail(90)
                cname_hl = PIHPS_CATEGORIES.get(hl_comcat, hl_comcat)
                fig_px = px.line(
                    x=s_hist.index,
                    y=s_hist.to_numpy(dtype=float),
                    title=f"Tren Harga 90 Hari Kerja Terakhir: {cname_hl} ({region_choice})",
                    labels={"x": "Tanggal", "y": "Harga (Rp/kg)"},
                )
                fig_px.update_traces(line_color="#D5352B", line_width=2.5)
                fig_px.update_layout(
                    paper_bgcolor="#FFFBF2",
                    plot_bgcolor="#FFFBF2",
                    font={"family": "Plus Jakarta Sans, sans-serif", "color": "#2E1D15"},
                    margin={"l": 10, "r": 10, "t": 40, "b": 10},
                    height=280,
                )
                st.plotly_chart(fig_px, width="stretch")
        else:
            st.markdown(
                '<div class="dd-card">'
                f'<h3 class="dd-h3">Riwayat Harga {_esc(target)}</h3>'
                '<p class="dd-muted" style="margin-top:8px">'
                "Bahan ini belum memiliki catatan harga harian di Bank Indonesia (PIHPS), "
                "sehingga grafik riwayat harga tidak ditampilkan."
                "</p></div>",
                unsafe_allow_html=True,
            )

    with c_ctx2:
        node_match = nodes_df.loc[nodes_df["ingredient"] == target]
        rec_cnt = int(node_match.iloc[0]["recipe_count"]) if not node_match.empty else 0
        neighbors: list[str] = []
        if target in graph:
            nbr_sorted = sorted(
                graph[target].items(),
                key=lambda kv: int(kv[1].get("count", 0)),
                reverse=True,
            )[:8]
            neighbors = [
                f"{nbr} ({_fmt_int(int(attrs.get('count', 0)))} resep)" for nbr, attrs in nbr_sorted
            ]
        nbr_html = (
            "".join(f'<span class="dd-chip">{_esc(n)}</span>' for n in neighbors)
            if neighbors
            else '<span class="dd-muted">Belum ada data pasangan.</span>'
        )
        st.markdown(
            '<div class="dd-card">'
            f'<h3 class="dd-h3">Profil Pemakaian "{_esc(target)}" di Dapur Nusantara</h3>'
            f'<p class="dd-muted" style="margin-top:6px">'
            f"Digunakan dalam <b>{_fmt_int(rec_cnt)}</b> resep masakan. "
            "Bahan yang paling sering dimasak bersamaan:"
            "</p>"
            f'<div class="dd-chips" style="margin-top:10px">{nbr_html}</div>'
            "</div>",
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="dd-note warn">'
        "<b>Perlu diingat</b>"
        f"<span>{_esc(LIMITATION_DISCLAIMER)}</span>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_fridge_page(state: dict[str, Any]) -> None:
    nodes_df: pd.DataFrame = state["nodes_df"]
    graph: nx.Graph[str] = state["graph"]
    train_norm: pd.DataFrame = state["train_norm"]
    n_train = len(train_norm)
    freq_map = dict(
        zip(
            nodes_df["ingredient"].astype(str),
            nodes_df["recipe_count"].astype(int),
            strict=False,
        )
    )

    st.markdown(
        '<h1 class="dd-h1">Ada apa di kulkasmu?</h1>'
        '<p class="dd-lead">'
        "Pilih bahan yang kamu punya. Kami sarankan bahan pelengkap yang paling sering "
        f"dipadukan serta resep terdekat dari <b>{_fmt_int(n_train)}</b> resep masakan Nusantara."
        "</p>",
        unsafe_allow_html=True,
    )

    top_options = nodes_df["ingredient"].head(150).tolist()
    selected = st.multiselect(
        "Bahan populer (maks. 25 bahan)",
        options=top_options,
        default=[
            x
            for x in ["bawang merah", "bawang putih", "cabai rawit", "telur ayam"]
            if x in top_options
        ],
        max_selections=25,
    )
    c_in1, c_in2 = st.columns([2, 1])
    with c_in1:
        extra_text = st.text_input(
            "Bahan lain, pisahkan dengan koma",
            value="",
            placeholder="mis. daun kemangi, tahu",
        )
    try:
        extra_list = [s for s in extra_text.split(",") if s.strip()]
        available = sanitize_ingredient_inputs([*selected, *extra_list], max_items=25)
    except ValueError as exc:
        st.error(str(exc))
        return

    if len(available) < 1:
        st.warning("Pilih minimal 1 bahan terlebih dahulu.")
        return

    with c_in2:
        min_ov = st.slider(
            "Minimal bahan yang cocok",
            min_value=1,
            max_value=min(5, len(available)),
            value=min(2, len(available)),
        )

    chips_html = "".join(f'<span class="dd-chip">{_esc(item)}</span>' for item in available)
    st.markdown(f'<div class="dd-chips">{chips_html}</div>', unsafe_allow_html=True)

    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown(
            '<h2 class="dd-h2">Bahan pelengkap</h2>'
            '<p class="dd-muted" style="margin-bottom:12px">'
            "Sering dimasak bersama bahan yang ada di kulkasmu.</p>",
            unsafe_allow_html=True,
        )
        comps = recommend_complements_conditional(
            available, graph, total_recipes=n_train, top_k=12
        )
        if comps:
            comp_cards: list[str] = []
            for rank_i, c in enumerate(comps, start=1):
                ing_name = str(c["ingredient"])
                cnt_rec = freq_map.get(ing_name, 0)
                paired_str = _esc(", ".join(c["paired_with"]))
                comp_cards.append(
                    '<div class="dd-card" style="padding:14px 18px">'
                    '<div style="display:flex;justify-content:space-between;align-items:center">'
                    f"<b>{rank_i}. {_esc(ing_name)}</b>"
                    f'<span class="dd-pill dd-p-ok">{_fmt_int(cnt_rec)} resep</span>'
                    "</div>"
                    f'<div class="dd-muted" style="margin-top:4px">'
                    f"Cocok dipadukan dengan: {paired_str}</div>"
                    "</div>"
                )
            st.markdown("".join(comp_cards), unsafe_allow_html=True)
        else:
            st.info("Belum ditemukan saran bahan pelengkap untuk kombinasi ini.")

    with col_right:
        st.markdown(
            '<h2 class="dd-h2">Resep yang cocok</h2>'
            '<p class="dd-muted" style="margin-bottom:12px">'
            "Diurutkan dari kelengkapan bahan tertinggi.</p>",
            unsafe_allow_html=True,
        )
        recipes = suggest_recipes_from_fridge(
            available,
            train_norm["clean_title"].astype(str).tolist(),
            train_norm["normalized_ingredients"].tolist(),
            top_k=12,
            min_overlap=min_ov,
        )
        if recipes:
            rec_cards: list[str] = []
            for r in recipes:
                pct = float(r["coverage_pct"])
                pill_cls = "dd-p-ok" if pct >= 60.0 else "dd-p-warn"
                matched_str = _esc(", ".join(r["matched"]))
                missing_str = (
                    _esc(", ".join(r["missing"])) if r["missing"] else "Semua bahan sudah ada!"
                )
                rec_cards.append(
                    '<div class="dd-card" style="padding:16px 18px">'
                    '<div style="display:flex;justify-content:space-between;'
                    'gap:10px;align-items:center">'
                    f'<h3 class="dd-h3">{_esc(r["title"])}</h3>'
                    f'<span class="dd-pill {pill_cls}">{_esc(_fmt_dec(pct, 0))}% cocok</span>'
                    "</div>"
                    f'<div class="dd-meter"><i style="width:{min(100.0, pct):.1f}%"></i></div>'
                    f'<p class="dd-muted">Sudah ada ({int(r["matched_count"])}): {matched_str}</p>'
                    f'<p class="dd-muted">Kurang ({int(r["missing_count"])}): {missing_str}</p>'
                    "</div>"
                )
            st.markdown("".join(rec_cards), unsafe_allow_html=True)
        else:
            st.info("Belum ada resep yang cocok. Tambah bahan atau kurangi minimal kecocokan.")


def _render_domino_page(state: dict[str, Any]) -> None:
    m2_dir: Path | None = state["runs"]["m2"]
    if m2_dir is None:
        st.error("Data analisis efek domino belum tersedia.")
        return

    nodes_raw = pd.read_csv(m2_dir / "commodity_nodes_raw_train.csv")
    edges_raw = pd.read_csv(m2_dir / "commodity_edges_raw_train.csv")
    wf_raw = pd.read_csv(m2_dir / "walk_forward_raw.csv")
    wf_adj = pd.read_csv(m2_dir / "walk_forward_seasonal_adj.csv")
    prov_sum = pd.read_csv(m2_dir / "spatial_province_summary.csv")
    city_sum = pd.read_csv(m2_dir / "spatial_city_summary.csv")
    event_df = pd.read_csv(m2_dir / "case_study_idul_fitri.csv")
    n_test_days = int(wf_raw["n_test"].max()) if not wf_raw.empty else 0

    st.markdown(
        '<h1 class="dd-h1">Siapa yang jatuh duluan?</h1>'
        '<p class="dd-lead">'
        "Menelusuri bahan pokok dan daerah yang harganya bergerak lebih dulu, "
        "serta menguji seberapa jauh pola tersebut bisa dipercaya untuk menebak harga ke depan."
        "</p>"
        '<div class="dd-note sci">'
        "<b>Bukan sebab-akibat</b>"
        "<span>"
        "Harga komoditas yang bergerak lebih dulu belum tentu menjadi penyebab langsung "
        f"naiknya komoditas lain. Kami menguji setiap pola pada {n_test_days} hari kerja "
        "berikutnya untuk memastikan apakah sinyalnya benar-benar membantu prediksi."
        "</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    prov_edges_path = m2_dir / "spatial_province_significant_edges.csv"
    city_edges_path = m2_dir / "spatial_city_significant_edges.csv"
    prov_edges = pd.read_csv(prov_edges_path) if prov_edges_path.is_file() else pd.DataFrame()
    city_edges = pd.read_csv(city_edges_path) if city_edges_path.is_file() else pd.DataFrame()

    tab1, tab2, tab3 = st.tabs(
        ["Hubungan Antar Bahan Pokok", "Pergerakan Antar Daerah", "Lonjakan Idul Fitri"]
    )

    with tab1:
        col_g, col_v = st.columns(2)
        with col_g:
            st.markdown(
                '<h3 class="dd-h3">Peta keterkaitan 10 bahan pokok</h3>'
                '<p class="dd-muted">'
                "Merah = lebih sering bergerak duluan · Hijau = lebih sering mengikuti."
                "</p>",
                unsafe_allow_html=True,
            )
            sig_edges = edges_raw.loc[edges_raw["significant"]].copy()
            g: nx.DiGraph[str] = nx.DiGraph()
            for _, r in nodes_raw.iterrows():
                g.add_node(str(r["commodity_name"]), net=float(r["net_trigger_score"]))
            for _, r in sig_edges.iterrows():
                g.add_edge(str(r["source_name"]), str(r["target_name"]), weight=float(r["weight"]))

            pos = nx.circular_layout(g)
            edge_x: list[float | None] = []
            edge_y: list[float | None] = []
            for u, v in g.edges():
                x0, y0 = pos[u]
                x1, y1 = pos[v]
                edge_x.extend([float(x0), float(x1), None])
                edge_y.extend([float(y0), float(y1), None])

            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=edge_x,
                    y=edge_y,
                    mode="lines",
                    line={"width": 1.0, "color": "#C4B199"},
                    hoverinfo="none",
                )
            )
            node_x = [float(pos[n][0]) for n in g.nodes()]
            node_y = [float(pos[n][1]) for n in g.nodes()]
            node_net = [float(g.nodes[n]["net"]) for n in g.nodes()]
            fig.add_trace(
                go.Scatter(
                    x=node_x,
                    y=node_y,
                    mode="markers+text",
                    text=list(g.nodes()),
                    textposition="top center",
                    marker={
                        "size": 20,
                        "color": node_net,
                        "colorscale": [[0.0, "#3B7A4B"], [0.5, "#F2A81D"], [1.0, "#D5352B"]],
                        "showscale": True,
                        "colorbar": {"title": "Pemicu vs Pengikut"},
                        "line": {"width": 1.5, "color": "#2E1D15"},
                    },
                )
            )
            fig.update_layout(
                paper_bgcolor="#FFFBF2",
                plot_bgcolor="#FFFBF2",
                font={"family": "Plus Jakarta Sans, sans-serif", "color": "#2E1D15"},
                margin={"l": 10, "r": 10, "t": 20, "b": 10},
                xaxis={"visible": False},
                yaxis={"visible": False},
                showlegend=False,
                height=380,
            )
            st.plotly_chart(fig, width="stretch")

            role_rows: list[str] = []
            for _, nrow in nodes_raw.iterrows():
                cname = _esc(nrow["commodity_name"])
                out_d = int(nrow["out_degree"])
                in_d = int(nrow["in_degree"])
                net_s = float(nrow["net_trigger_score"])
                role_pill = (
                    '<span class="dd-pill dd-p-no">Sering mendahului</span>'
                    if net_s > 0
                    else '<span class="dd-pill dd-p-ok">Cenderung mengikuti</span>'
                )
                role_rows.append(
                    f"<tr><td><b>{cname}</b></td><td>{out_d} komoditas</td>"
                    f"<td>{in_d} komoditas</td><td>{role_pill}</td></tr>"
                )
            st.markdown(
                '<div class="dd-card" style="padding:14px">'
                '<h3 class="dd-h3" style="margin-bottom:8px">Peran tiap bahan pokok</h3>'
                '<table class="dd-table">'
                "<thead><tr><th>Bahan Pokok</th><th>Mendahului</th>"
                "<th>Mengikuti</th><th>Posisi</th></tr></thead>"
                f'<tbody>{"".join(role_rows)}</tbody>'
                "</table></div>",
                unsafe_allow_html=True,
            )

        with col_v:
            st.markdown(
                '<h3 class="dd-h3">Apakah terbukti saat menebak harga masa depan?</h3>'
                f'<p class="dd-muted">Diuji pada {n_test_days} hari kerja berikutnya '
                "dibandingkan dengan menebak dari tren harganya sendiri.</p>",
                unsafe_allow_html=True,
            )
            mode_wf = st.radio(
                "Mode pengujian",
                ["Tanpa koreksi musim", "Setelah memperhitungkan musim & Hari Raya"],
                horizontal=True,
            )
            wf_show = wf_raw if mode_wf == "Tanpa koreksi musim" else wf_adj

            rows_html: list[str] = []
            for _, wrow in wf_show.iterrows():
                cname = _esc(wrow["commodity_name"])
                skill = float(wrow["skill_vs_ar_pct"])
                passed = bool(wrow["vp6_validated"])
                skill_cls = "dd-down" if skill > 0 else "dd-up"
                bar_w = max(0.0, min(90.0, skill * 3.5)) if skill > 0 else 0.0
                bar_html = (
                    f'<span class="dd-bar-c" style="width:{bar_w:.1f}px"></span> '
                    if bar_w > 0
                    else ""
                )
                pill_html = (
                    '<span class="dd-pill dd-p-ok">Terbukti membantu</span>'
                    if passed
                    else '<span class="dd-pill dd-p-no">Cukup lihat tren sendiri</span>'
                )
                rows_html.append(
                    "<tr>"
                    f"<td><b>{cname}</b></td>"
                    f"<td>{int(wrow['n_triggers'])} bahan</td>"
                    f'<td>{bar_html}<b class="{skill_cls}">{_esc(_fmt_pct(skill))}</b></td>'
                    f"<td>{pill_html}</td>"
                    "</tr>"
                )

            n_pass = int(wf_show["vp6_validated"].sum())
            st.markdown(
                '<div class="dd-card" style="padding:14px">'
                '<table class="dd-table">'
                "<thead><tr>"
                "<th>Bahan Pokok</th><th>Sinyal Pendahulu</th>"
                "<th>Dampak ke Akurasi</th><th>Hasil Uji</th>"
                "</tr></thead>"
                f'<tbody>{"".join(rows_html)}</tbody>'
                "</table>"
                '<p class="dd-muted" style="margin-top:10px">'
                f"<b>{n_pass} dari {len(wf_show)}</b> bahan pokok terbukti lebih akurat "
                "ditebak dengan bantuan komoditas lain. Untuk cabai dan bawang, "
                "riwayat harganya sendiri sudah lebih kuat."
                "</p></div>",
                unsafe_allow_html=True,
            )

        # Pairwise historical price comparison from actual data
        if not sig_edges.empty:
            st.markdown(
                '<h2 class="dd-h2">Bandingkan riwayat harga dua bahan pokok</h2>',
                unsafe_allow_html=True,
            )
            pair_options = [
                f"{r['source_name']} → {r['target_name']} "
                f"(jeda terkuat {int(r['best_xcorr_lag'])} hari kerja)"
                for _, r in sig_edges.head(25).iterrows()
            ]
            chosen_pair = st.selectbox("Pilih pasangan hubungan harga", pair_options)
            pair_idx = pair_options.index(chosen_pair)
            prow_sel = sig_edges.iloc[pair_idx]
            src_col = f"{prow_sel['source']}__Semua Provinsi"
            dst_col = f"{prow_sel['target']}__Semua Provinsi"
            px_nat: pd.DataFrame = state["px_nat"]
            if src_col in px_nat.columns and dst_col in px_nat.columns:
                fig_pair = make_subplots(specs=[[{"secondary_y": True}]])
                fig_pair.add_trace(
                    go.Scatter(
                        x=px_nat.index,
                        y=px_nat[src_col],
                        name=str(prow_sel["source_name"]),
                        line={"color": "#D5352B", "width": 2},
                    ),
                    secondary_y=False,
                )
                fig_pair.add_trace(
                    go.Scatter(
                        x=px_nat.index,
                        y=px_nat[dst_col],
                        name=str(prow_sel["target_name"]),
                        line={"color": "#3B7A4B", "width": 2},
                    ),
                    secondary_y=True,
                )
                fig_pair.update_layout(
                    title=(
                        f"Perbandingan Harga Harian: {prow_sel['source_name']} vs "
                        f"{prow_sel['target_name']}"
                    ),
                    paper_bgcolor="#FFFBF2",
                    plot_bgcolor="#FFFBF2",
                    font={"family": "Plus Jakarta Sans, sans-serif", "color": "#2E1D15"},
                    height=340,
                    margin={"l": 10, "r": 10, "t": 40, "b": 10},
                )
                st.plotly_chart(fig_pair, width="stretch")

    with tab2:
        if not prov_sum.empty:
            com_names = prov_sum["commodity_name"].astype(str).tolist()
            default_c = com_names.index("Cabai Merah") if "Cabai Merah" in com_names else 0
            chosen_cname = st.selectbox(
                "Pilih bahan pokok untuk melihat peta daerah",
                com_names,
                index=default_c,
            )
            p_focus = prov_sum.loc[prov_sum["commodity_name"] == chosen_cname].iloc[0]
            cid_focus = str(p_focus["comcat_id"])

            c_p, c_c = st.columns(2)
            with c_p:
                n_pr = int(p_focus["n_provinces"])
                p_lead = _esc(p_focus["top_leader_province"])
                p_deg = int(p_focus["top_leader_out_degree"])
                st.markdown(
                    '<div class="dd-card">'
                    f'<h3 class="dd-h3">Provinsi yang bergerak lebih dulu ({n_pr} provinsi)</h3>'
                    '<p class="dd-muted" style="margin-top:10px">'
                    f"Pemimpin utama {_esc(chosen_cname)}</p>"
                    f'<div class="dd-big">{p_lead}</div>'
                    f'<p class="dd-muted">Mendahului pergerakan harga di {p_deg} provinsi lain</p>'
                    "</div>",
                    unsafe_allow_html=True,
                )
                if not prov_edges.empty and "comcat_id" in prov_edges.columns:
                    sub_pe = prov_edges.loc[prov_edges["comcat_id"] == cid_focus].head(10)
                    if not sub_pe.empty:
                        pe_rows = "".join(
                            f"<tr><td><b>{_esc(r['source'])}</b></td>"
                            f"<td>{_esc(r['target'])}</td>"
                            f"<td>{int(r['best_xcorr_lag'])} hari kerja</td></tr>"
                            for _, r in sub_pe.iterrows()
                        )
                        st.markdown(
                            '<div class="dd-card" style="padding:14px">'
                            '<h3 class="dd-h3" style="margin-bottom:8px">'
                            f"Jalur rambatan provinsi terkuat ({_esc(chosen_cname)})</h3>"
                            '<table class="dd-table">'
                            "<thead><tr><th>Provinsi Awal</th><th>Diikuti Provinsi</th>"
                            "<th>Jeda</th></tr></thead>"
                            f"<tbody>{pe_rows}</tbody></table></div>",
                            unsafe_allow_html=True,
                        )

            with c_c:
                city_match = (
                    city_sum.loc[city_sum["comcat_id"] == cid_focus]
                    if not city_sum.empty and "comcat_id" in city_sum.columns
                    else pd.DataFrame()
                )
                if not city_match.empty:
                    c_focus = city_match.iloc[0]
                    n_ct = int(c_focus["n_cities"])
                    c_lead = _esc(c_focus["top_leader_city"])
                    c_deg = int(c_focus["top_leader_out_degree"])
                    st.markdown(
                        '<div class="dd-card">'
                        f'<h3 class="dd-h3">Kota/Kabupaten pemimpin ({n_ct} kota)</h3>'
                        '<p class="dd-muted" style="margin-top:10px">'
                        f"Pemimpin utama {_esc(chosen_cname)}</p>"
                        f'<div class="dd-big">{c_lead}</div>'
                        f'<p class="dd-muted">Mendahului {c_deg} dari {n_ct - 1} kota lainnya</p>'
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    if not city_edges.empty and "comcat_id" in city_edges.columns:
                        sub_ce = city_edges.loc[city_edges["comcat_id"] == cid_focus].head(10)
                        if not sub_ce.empty:
                            ce_rows = "".join(
                                f"<tr><td><b>{_esc(r['source'])}</b></td>"
                                f"<td>{_esc(r['target'])}</td>"
                                f"<td>{int(r['best_xcorr_lag'])} hari kerja</td></tr>"
                                for _, r in sub_ce.iterrows()
                            )
                            st.markdown(
                                '<div class="dd-card" style="padding:14px">'
                                '<h3 class="dd-h3" style="margin-bottom:8px">'
                                f"Jalur rambatan kota terkuat ({_esc(chosen_cname)})</h3>"
                                '<table class="dd-table">'
                                "<thead><tr><th>Kota Awal</th><th>Diikuti Kota</th>"
                                "<th>Jeda</th></tr></thead>"
                                f"<tbody>{ce_rows}</tbody></table></div>",
                                unsafe_allow_html=True,
                            )
                else:
                    st.markdown(
                        '<div class="dd-card">'
                        '<h3 class="dd-h3">Ringkasan pemimpin seluruh bahan pokok</h3>'
                        '<p class="dd-muted">'
                        "Daftar provinsi yang paling sering bergerak lebih dulu:</p>"
                        "</div>",
                        unsafe_allow_html=True,
                    )
                    prov_clean = prov_sum[
                        ["commodity_name", "top_leader_province", "top_leader_out_degree"]
                    ].rename(
                        columns={
                            "commodity_name": "Bahan Pokok",
                            "top_leader_province": "Provinsi Pemimpin",
                            "top_leader_out_degree": "Jumlah Provinsi Pengikut",
                        }
                    )
                    st.dataframe(prov_clean, width="stretch", hide_index=True)

    with tab3:
        if event_df.empty:
            st.info("Tidak ada periode Idul Fitri yang tercakup pada rentang data ini.")
        else:
            ev_raw_list = sorted(event_df["event"].unique().tolist())
            ev_labels = {ev: ev.replace("_", " ") for ev in ev_raw_list}
            label_to_ev = {v: k for k, v in ev_labels.items()}
            chosen_label = st.selectbox(
                "Periode Idul Fitri", [ev_labels[e] for e in ev_raw_list]
            )
            ev_choice = label_to_ev[chosen_label]
            sub_ev = event_df.loc[event_df["event"] == ev_choice].sort_values(
                "pct_change_to_peak", ascending=False
            )
            col_e1, col_e2 = st.columns(2)
            with col_e1:
                fig_ev = px.bar(
                    sub_ev,
                    x="commodity_name",
                    y="pct_change_to_peak",
                    title=f"Perubahan Harga Menuju Puncak {chosen_label} (%)",
                    labels={"commodity_name": "Bahan Pokok", "pct_change_to_peak": "Perubahan (%)"},
                    color="pct_change_to_peak",
                    color_continuous_scale=["#3B7A4B", "#F2A81D", "#D5352B"],
                )
                fig_ev.update_layout(
                    paper_bgcolor="#FFFBF2",
                    plot_bgcolor="#FFFBF2",
                    font={"family": "Plus Jakarta Sans, sans-serif", "color": "#2E1D15"},
                    showlegend=False,
                    height=360,
                )
                st.plotly_chart(fig_ev, width="stretch")
            with col_e2:
                ev_rows = "".join(
                    f"<tr><td><b>{_esc(r['commodity_name'])}</b></td>"
                    f"<td>{_esc(_fmt_idr(float(r['baseline_mean_idr'])))}</td>"
                    f"<td>{_esc(_fmt_idr(float(r['peak_idr'])))}</td>"
                    f"<td>{_esc(format_tanggal_indo(str(r['peak_date'])))}</td>"
                    f"<td class=\"{'dd-up' if float(r['pct_change_to_peak']) > 0 else 'dd-down'}\">"
                    f"{_esc(_fmt_pct(float(r['pct_change_to_peak'])))}</td></tr>"
                    for _, r in sub_ev.iterrows()
                )
                st.markdown(
                    '<div class="dd-card" style="padding:14px">'
                    f'<h3 class="dd-h3" style="margin-bottom:8px">Rincian Harga {chosen_label}</h3>'
                    '<table class="dd-table">'
                    "<thead><tr><th>Bahan Pokok</th><th>Harga Awal</th>"
                    "<th>Harga Puncak</th><th>Tanggal Puncak</th><th>Perubahan</th></tr></thead>"
                    f"<tbody>{ev_rows}</tbody></table></div>",
                    unsafe_allow_html=True,
                )


def _render_evidence_page(state: dict[str, Any]) -> None:
    st.markdown(
        '<h1 class="dd-h1">Bagaimana sistem ini diuji?</h1>'
        '<p class="dd-lead">'
        "Semua rekomendasi di aplikasi ini dihitung dari data nyata. "
        "Berikut adalah hasil pengujian kualitasnya, termasuk bagian yang sudah akurat "
        "maupun yang masih terbatas."
        "</p>",
        unsafe_allow_html=True,
    )

    runs = state["runs"]
    manifests: dict[str, dict[str, Any]] = {}
    for stage_key in ("m1", "m2", "m3", "m4"):
        rdir = runs[stage_key]
        if rdir is not None and (rdir / "manifest.json").is_file():
            manifests[stage_key] = load_json_dict(rdir / "manifest.json")

    # 1. Scale of data used
    if "m1" in manifests and "m3" in manifests:
        m1_nat = manifests["m1"]["metrics"]["levels"]["national"]["cleaning"]
        m1_prov = manifests["m1"]["metrics"]["levels"]["province"]["cleaning"]
        m1_city = manifests["m1"]["metrics"]["levels"]["city"]["cleaning"]
        m3_corp = manifests["m3"]["metrics"]["corpus"]
        raw_rows = int(m1_nat["raw_rows"])
        b_days = int(m1_nat["business_day_rows"]) - int(m1_nat.get("holiday_dates_dropped", 0))
        n_nat_s = max(1, int(m1_nat["retained_series"]))
        n_prov_s = int(m1_prov["retained_series"]) // n_nat_s
        n_city_s = int(m1_city["retained_series"]) // n_nat_s
        if runs.get("m2") is not None:
            city_sum_p = runs["m2"] / "spatial_city_summary.csv"
            if city_sum_p.is_file():
                city_sum_df = pd.read_csv(city_sum_p)
                if not city_sum_df.empty and "n_cities" in city_sum_df.columns:
                    n_city_s = int(city_sum_df["n_cities"].max())
        tot_rec = int(m3_corp["train_recipes"]) + int(m3_corp["eval_recipes"])
        st.markdown(
            '<h2 class="dd-h2">Skala data yang dianalisis</h2>'
            '<div class="dd-grid dd-g3">'
            '<div class="dd-card">'
            '<p class="dd-muted">Catatan Harga Pangan (Bank Indonesia)</p>'
            f'<div class="dd-big">{_fmt_int(raw_rows)}</div>'
            f'<p class="dd-muted">baris data selama {b_days} hari pasar aktif (3 tahun)</p>'
            "</div>"
            '<div class="dd-card">'
            '<p class="dd-muted">Cakupan Wilayah Pantauan</p>'
            f'<div class="dd-big">{n_prov_s} Provinsi</div>'
            f'<p class="dd-muted">dan hingga {n_city_s} kota/kabupaten di Indonesia</p>'
            "</div>"
            '<div class="dd-card">'
            '<p class="dd-muted">Resep Masakan Nusantara</p>'
            f'<div class="dd-big">{_fmt_int(tot_rec)} Resep</div>'
            f'<p class="dd-muted">{_fmt_int(int(m3_corp["train_recipes"]))} resep untuk belajar · '
            f'{_fmt_int(int(m3_corp["eval_recipes"]))} resep untuk ujian</p>'
            "</div>"
            "</div>",
            unsafe_allow_html=True,
        )

    # 2. Plain-language quality cards
    st.markdown('<h2 class="dd-h2">Hasil pengujian kualitas sistem</h2>', unsafe_allow_html=True)
    q_cards: list[str] = []

    vp1 = state.get("vp1")
    if isinstance(vp1, dict):
        acc1 = float(vp1.get("accuracy_pct", 0.0))
        c1 = int(vp1.get("clean_count", 0))
        t1 = int(vp1.get("total_sampled", 300))
        q_cards.append(
            '<div class="dd-card"><span class="dd-pill dd-p-ok">Pembersihan Tulisan Resep</span>'
            f'<div class="dd-big">{_esc(_fmt_dec(acc1, 1))}%</div>'
            f'<p class="dd-muted">{c1} dari {t1} contoh tulisan bahan yang berantakan '
            "(seperti takaran, singkatan, dan catatan) berhasil dikenali dengan tepat.</p></div>"
        )

    if "m3" in manifests:
        m3m = manifests["m3"]["metrics"]
        vp2 = m3m["vp2_hide_one_ingredient"]
        cond_t5 = vp2["methods"]["cooccur_conditional"]["top_5"]
        pop_t5 = vp2["methods"]["popularity"]["top_5"]
        c_acc = _esc(_fmt_dec(float(cond_t5["accuracy_pct"]), 1))
        p_acc = _esc(_fmt_dec(float(pop_t5["accuracy_pct"]), 1))
        n_ev2 = int(vp2["n_eval_recipes"])
        q_cards.append(
            '<div class="dd-card"><span class="dd-pill dd-p-ok">Tebakan Bahan Pelengkap</span>'
            f'<div class="dd-big">{c_acc}%</div>'
            f'<p class="dd-muted">Saat 1 bahan disembunyikan dari {_fmt_int(n_ev2)} resep uji, '
            f"sistem berhasil menebaknya di 5 saran teratas — lebih akurat dari "
            f"sekadar menebak bahan populer ({p_acc}%).</p></div>"
        )
        vp3 = m3m["vp3_substitution_recall"]
        r5 = float(vp3.get("recall", {}).get("recall_at_5", 0.0))
        h5 = int(vp3.get("hits", {}).get("hits_at_5", 0))
        ev3 = int(vp3.get("evaluated_in_vocab", 0))
        q_cards.append(
            '<div class="dd-card"><span class="dd-pill dd-p-no">Keterbatasan Bahan Pengganti</span>'
            f'<div class="dd-big">{_esc(_fmt_dec(r5, 1))}%</div>'
            f'<p class="dd-muted">Baru {h5} dari {ev3} bahan uji yang langsung cocok dengan '
            "daftar pengganti buku masak karena sistem masih sering menyarankan variasi "
            "nama yang mirip.</p></div>"
        )

    if "m2" in manifests:
        m2m = manifests["m2"]["metrics"]
        vp6_r = m2m["vp6_walk_forward_raw"]
        vp6_a = m2m["vp6_walk_forward_seasonal_adj"]
        r_ok = int(vp6_r["targets_vp6_validated"])
        a_ok = int(vp6_a["targets_vp6_validated"])
        a_tot = int(vp6_a["targets_with_triggers"])
        combined_names: list[str] = []
        m2_dir = runs.get("m2")
        if m2_dir is not None:
            wf_r_p = m2_dir / "walk_forward_raw.csv"
            wf_a_p = m2_dir / "walk_forward_seasonal_adj.csv"
            if wf_r_p.is_file() and wf_a_p.is_file():
                df_wfr = pd.read_csv(wf_r_p)
                df_wfa = pd.read_csv(wf_a_p)
                ok_r = set(
                    df_wfr.loc[df_wfr["vp6_validated"].astype(bool), "commodity_name"].astype(str)
                )
                ok_a = set(
                    df_wfa.loc[df_wfa["vp6_validated"].astype(bool), "commodity_name"].astype(str)
                )
                combined_names = sorted(ok_r | ok_a)
        n_comb = len(combined_names) if combined_names else max(r_ok, a_ok)
        names_txt = ", ".join(combined_names) if combined_names else "sebagian bahan pokok"
        q_cards.append(
            '<div class="dd-card"><span class="dd-pill dd-p-warn">Kejujuran Prediksi Harga</span>'
            f'<div class="dd-big">{n_comb} dari {a_tot}</div>'
            f'<p class="dd-muted">Hanya {_esc(names_txt)} yang tebakan harganya benar-benar '
            f"terbantu oleh komoditas lain ({r_ok} di gerak mentah, {a_ok} pasca-koreksi "
            "musiman). Bahan lain lebih akurat mengikuti tren harganya sendiri.</p></div>"
        )
        vp7 = m2m["vp7_seasonal_robustness"]
        s_ed = int(vp7["survived_edges"])
        b_ed = int(vp7["base_significant_edges"])
        ret_p = _esc(_fmt_dec(float(vp7["retention_pct_of_base"]), 0))
        q_cards.append(
            '<div class="dd-card">'
            '<span class="dd-pill dd-p-ok">Tahan Efek Musim &amp; Lebaran</span>'
            f'<div class="dd-big">{ret_p}% ({s_ed}/{b_ed})</div>'
            '<p class="dd-muted">Seluruh pola keterkaitan harga tetap bertahan walaupun '
            "lonjakan musiman dan hari raya sudah dipisahkan.</p></div>"
        )
        vp5 = m2m["vp5_permutation_control"]
        f_rate = 100.0 * float(vp5["mean_false_edge_rate"])
        f_rate_str = _esc(_fmt_dec(f_rate, 1))
        q_cards.append(
            '<div class="dd-card"><span class="dd-pill dd-p-ok">Uji Acak Anti-Kebetulan</span>'
            f'<div class="dd-big">{f_rate_str}%</div>'
            f'<p class="dd-muted">Saat urutan tanggal diacak {int(vp5["n_permutations"])} kali, '
            f"hanya {f_rate_str}% hubungan yang muncul karena kebetulan "
            "(di bawah batas aman 5%).</p></div>"
        )

    st.markdown(f'<div class="dd-grid dd-g3">{"".join(q_cards)}</div>', unsafe_allow_html=True)

    analysis_dir = REPO_ROOT / "artifacts" / "analysis"
    eda_p_csv = analysis_dir / "eda_prices_stats.csv"
    scen_ts_csv = analysis_dir / "scenarios_timeseries_val.csv"
    if eda_p_csv.is_file() and scen_ts_csv.is_file():
        st.markdown(
            '<h2 class="dd-h2">Telaah Sebaran Harga &amp; Pemilihan Skenario Model</h2>',
            unsafe_allow_html=True,
        )
        c_eda, c_scen = st.columns(2)
        with c_eda:
            eda_df = pd.read_csv(eda_p_csv)
            eda_rows = "".join(
                f"<tr><td><b>{_esc(r['commodity_name'])}</b></td>"
                f"<td>{_esc(_fmt_idr(float(r['mean_idr'])))}</td>"
                f"<td>{_esc(_fmt_idr(float(r['min_idr'])))} – "
                f"{_esc(_fmt_idr(float(r['max_idr'])))}</td>"
                f"<td>{_esc(_fmt_dec(float(r['cv_pct']), 1))}%</td></tr>"
                for _, r in eda_df.iterrows()
            )
            st.markdown(
                '<div class="dd-card" style="padding:14px">'
                '<h3 class="dd-h3" style="margin-bottom:8px">'
                "Profil harga 10 bahan pokok (3 tahun)</h3>"
                '<table class="dd-table">'
                "<thead><tr><th>Bahan Pokok</th><th>Rata-rata</th>"
                "<th>Rentang (Termurah–Termahal)</th><th>Tingkat Gejolak</th></tr></thead>"
                f"<tbody>{eda_rows}</tbody></table></div>",
                unsafe_allow_html=True,
            )
        with c_scen:
            scen_df = pd.read_csv(scen_ts_csv)
            scen_rows_list: list[str] = []
            for _, r in scen_df.iterrows():
                desc_s = str(r["scenario_description"])
                if "DIPILIH" in desc_s:
                    musim_lbl = "Ya (Dipilih)"
                elif "Seasonally" in desc_s:
                    musim_lbl = "Ya"
                else:
                    musim_lbl = "Tidak"
                scen_rows_list.append(
                    f"<tr><td><b>{int(r['lag_order'])} hari kerja</b></td>"
                    f"<td>{_esc(str(r['ridge_alpha']))}</td>"
                    f"<td>{musim_lbl}</td>"
                    f"<td><b>{_esc(_fmt_pct(float(r['mean_skill_vs_ar_pct'])))}</b></td>"
                    f"<td>{int(r['commodities_beating_ar'])}/10 bahan</td></tr>"
                )
            scen_rows = "".join(scen_rows_list)
            st.markdown(
                '<div class="dd-card" style="padding:14px">'
                '<h3 class="dd-h3" style="margin-bottom:8px">'
                "Uji coba 8 skenario model prediksi harga</h3>"
                '<table class="dd-table">'
                "<thead><tr><th>Jeda Waktu</th><th>Kekuatan Penyeimbang</th>"
                "<th>Pisahkan Efek Musim</th><th>Peningkatan Akurasi</th>"
                "<th>Unggul di</th></tr></thead>"
                f"<tbody>{scen_rows}</tbody></table></div>",
                unsafe_allow_html=True,
            )

    # 3. Coverage & Laptop Resource Usage
    cov = compute_mapping_coverage(state["nodes_df"], state["mapping"])
    v_pct_str = _esc(_fmt_dec(cov.vocab_coverage_pct, 2))
    m_pct_str = _esc(_fmt_dec(cov.mention_coverage_pct, 2))
    v_w = min(100.0, cov.vocab_coverage_pct)
    m_w = min(100.0, cov.mention_coverage_pct)

    c_cov, c_ram = st.columns(2)
    with c_cov:
        st.markdown(
            '<div class="dd-card">'
            '<h3 class="dd-h3">Seberapa banyak bahan resep yang punya data harga?</h3>'
            '<p style="margin-top:12px">Jenis bahan di kamus resep: '
            f"<b>{cov.mapped_vocab_ingredients} dari {_fmt_int(cov.total_vocab_ingredients)}</b> "
            f"({v_pct_str}%)</p>"
            f'<div class="dd-meter"><i style="width:{v_w:.2f}%;background:var(--kunyit)"></i></div>'
            '<p style="margin-top:12px">Proporsi pemakaian di dapur sehari-hari: '
            f"<b>{_fmt_int(cov.mapped_recipe_mentions)} dari "
            f"{_fmt_int(cov.total_recipe_mentions)}</b> "
            f"({m_pct_str}%)</p>"
            f'<div class="dd-meter"><i style="width:{m_w:.2f}%;background:var(--kunyit)"></i></div>'
            '<p class="dd-muted" style="margin-top:8px">'
            "Walaupun hanya 10 bahan pokok yang harganya dipantau harian oleh Bank Indonesia, "
            "bahan-bahan tersebut menyumbang lebih dari seperempat pemakaian bahan di resep."
            "</p></div>",
            unsafe_allow_html=True,
        )

    with c_ram:
        ram_rows: list[str] = []
        for stage_key in ("m1", "m2", "m3", "m4"):
            if stage_key in manifests:
                m = manifests[stage_key]
                res = m.get("resources", {})
                dur = float(res.get("duration_sec", 0.0))
                rss = float(res.get("peak_rss_mb", 0.0))
                pct_ram = max(0.5, min(100.0, (rss / 8192.0) * 100.0))
                label_id = STAGE_LABELS.get(stage_key, stage_key)
                ram_rows.append(
                    f'<div style="margin-bottom:10px">'
                    f'<div style="display:flex;justify-content:space-between;font-size:0.88rem">'
                    f"<b>{_esc(label_id)}</b>"
                    f'<span class="dd-muted">{_esc(_fmt_dec(dur, 1))} detik · '
                    f"{_esc(_fmt_dec(rss, 0))} MB / 8.192 MB</span>"
                    f"</div>"
                    '<div class="dd-ram" style="margin:4px 0">'
                    f'<i style="width:{pct_ram:.2f}%"></i></div>'
                    f"</div>"
                )
        st.markdown(
            '<div class="dd-card">'
            '<h3 class="dd-h3" style="margin-bottom:10px">'
            "Pemakaian memori &amp; waktu proses di laptop</h3>"
            f'{"".join(ram_rows)}'
            '<p class="dd-muted" style="margin-top:6px">'
            "Seluruh proses berjalan ringan di bawah batas RAM laptop standar (8 GB)."
            "</p></div>",
            unsafe_allow_html=True,
        )
        if st.button("Periksa keutuhan seluruh file data"):
            raw_errs = verify_raw_manifest(
                REPO_ROOT / "data" / "raw" / "manifest.json", REPO_ROOT / "data" / "raw"
            )
            run_errs: dict[str, list[str]] = {}
            for k, rdir in runs.items():
                if rdir is not None:
                    run_errs[k] = verify_run_manifest(rdir / "manifest.json")
            if not raw_errs and all(not v for v in run_errs.values()):
                st.success("Semua file data mentah dan hasil analisis utuh dan terverifikasi.")
            else:
                st.error({"raw_errors": raw_errs, "run_errors": run_errs})


def main() -> None:
    st.set_page_config(
        page_title="Dapur Domino",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_styles()
    state = load_app_state()

    page = _render_top_navbar()
    latest_dt_indo = format_tanggal_indo(
        str(pd.Timestamp(state["px_nat"].index[-1]).strftime("%Y-%m-%d"))
    )

    if page == "Ganti bahan":
        _render_substitution_page(state)
    elif page == "Isi kulkasku":
        _render_fridge_page(state)
    elif page == "Efek domino":
        _render_domino_page(state)
    else:
        _render_evidence_page(state)

    st.markdown(
        '<div class="dd-footer">'
        "Dapur Domino · Berjalan 100% lokal di perangkat Anda · "
        f"Data harga: PIHPS Bank Indonesia, per {_esc(latest_dt_indo)}"
        "</div>",
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
