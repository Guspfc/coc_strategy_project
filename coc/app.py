import streamlit as st
import pandas as pd
from war_engine import fetch_war_data, build_members_df, calc_opponent_stars, determine_target

# ── Page Config ──
st.set_page_config(page_title="CoC War Strategy", page_icon="⚔️", layout="wide")

# ── Custom CSS ──
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');

html, body, [class*="st-"] { font-family: 'Inter', sans-serif; }

.main { background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%); }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }

.title-block {
    text-align: center; padding: 1.5rem 0 0.5rem;
}
.title-block h1 {
    font-size: 2.6rem; font-weight: 900;
    background: linear-gradient(90deg, #f7971e, #ffd200);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.2rem;
}
.title-block p { color: #aaa; font-size: 1rem; }

.card {
    background: rgba(255,255,255,0.06);
    border: 1px solid rgba(255,255,255,0.10);
    border-radius: 16px; padding: 1.5rem;
    backdrop-filter: blur(12px);
    margin-bottom: 1rem;
}
.card h3 {
    margin: 0 0 0.8rem; font-size: 1.15rem;
    color: #ffd200;
}

.target-card {
    background: linear-gradient(135deg, rgba(247,151,30,0.15), rgba(255,210,0,0.08));
    border: 1px solid rgba(255,210,0,0.25);
    border-radius: 16px; padding: 1.8rem;
    text-align: center; margin-top: 1rem;
}
.target-card .label { color: #aaa; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 1px; }
.target-card .value { color: #fff; font-size: 1.6rem; font-weight: 700; margin: 0.3rem 0; }
.target-card .sub { color: #ccc; font-size: 0.95rem; }

.bonus-card {
    background: linear-gradient(135deg, rgba(0,200,83,0.15), rgba(0,230,118,0.08));
    border: 1px solid rgba(0,200,83,0.3);
    border-radius: 16px; padding: 1.8rem;
    text-align: center; margin-top: 1rem;
}
.bonus-card .value { color: #00e676; font-size: 1.5rem; font-weight: 700; }
.bonus-card .sub { color: #a5d6a7; font-size: 0.95rem; margin-top: 0.3rem; }

.done-card {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 16px; padding: 1.5rem;
    text-align: center; margin-top: 1rem;
}
.done-card .value { color: #888; font-size: 1.3rem; font-weight: 600; }

.star-full { color: #ffd200; }
.star-empty { color: #555; }

.table-responsive {
    width: 100%;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
}

.war-table {
    width: 100%; border-collapse: separate; border-spacing: 0;
    font-size: 0.88rem; color: #ddd;
    min-width: 600px; /* Força scroll horizontal no mobile */
}
.war-table th {
    background: rgba(255,210,0,0.12); color: #ffd200;
    padding: 0.6rem 0.8rem; text-align: left;
    border-bottom: 2px solid rgba(255,210,0,0.2);
    font-weight: 700; font-size: 0.8rem;
    text-transform: uppercase; letter-spacing: 0.5px;
}
.war-table td {
    padding: 0.55rem 0.8rem;
    border-bottom: 1px solid rgba(255,255,255,0.05);
}
.war-table tr:hover td { background: rgba(255,255,255,0.04); }

.stat-num { font-size: 2rem; font-weight: 900; color: #ffd200; }
.stat-label { font-size: 0.8rem; color: #aaa; text-transform: uppercase; letter-spacing: 1px; }

/* ── Mobile Responsiveness ── */
@media (max-width: 768px) {
    .title-block h1 { font-size: 2rem; }
    .title-block p { font-size: 0.9rem; }
    
    .card, .target-card, .bonus-card, .done-card { 
        padding: 1.2rem; 
    }
    
    .target-card .value { font-size: 1.3rem; }
    .stat-num { font-size: 1.5rem; }
    .stat-label { font-size: 0.7rem; }
    
    .war-table th, .war-table td {
        padding: 0.5rem;
    }
}
</style>
""", unsafe_allow_html=True)


# ── Helpers ──
def stars_html(current, total=3):
    return (
        '<span class="star-full">⭐</span>' * current
        + '<span class="star-empty">☆</span>' * (total - current)
    )


# ── Data Loading ──
@st.cache_data(ttl=60)
def load_war():
    data = fetch_war_data()
    df_c = build_members_df(data["clan"]["members"], "clan")
    df_o = build_members_df(data["opponent"]["members"], "opponent")
    s = calc_opponent_stars(df_c, df_o)
    return data, df_c, df_o, s


# ── Main ──
st.markdown("""
<div class="title-block">
    <h1>⚔️ CoC War Strategy</h1>
    <p>Sistema de alvos estratégicos para guerra de clã</p>
</div>
""", unsafe_allow_html=True)

try:
    war_data, df_clan, df_opponent, opp_stars = load_war()
except Exception as e:
    st.error(f"Erro ao buscar dados da guerra: {e}")
    st.stop()

# ── Controles Principais ──
st.markdown("### ⚔️ Qual jogador é você?")
col1, col2 = st.columns([3, 1])

player_options = {
    f"#{int(r['map_position']):02d} — {r['name']} (TH{r['townhall_level']})": r["tag"]
    for _, r in df_clan.iterrows()
}

with col1:
    selected_label = st.selectbox("Jogador", list(player_options.keys()), label_visibility="collapsed")
    selected_tag = player_options[selected_label]

with col2:
    if st.button("🔄 Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# ── Stats Row ──
total_stars = sum(opp_stars.values())
max_stars = len(opp_stars) * 3
pct = int(total_stars / max_stars * 100) if max_stars else 0
atks_used = df_clan["attacks_used"].sum()
atks_total = len(df_clan) * 2

c1, c2, c3, c4 = st.columns(4)
for col, num, label in [
    (c1, f"{total_stars}/{max_stars}", "Estrelas"),
    (c2, f"{pct}%", "Destruição"),
    (c3, f"{atks_used}/{atks_total}", "Ataques Usados"),
    (c4, war_data["teamSize"], "Tamanho"),
]:
    col.markdown(f"""
    <div class="card" style="text-align:center">
        <div class="stat-num">{num}</div>
        <div class="stat-label">{label}</div>
    </div>
    """, unsafe_allow_html=True)

# ── Target Card ──
result = determine_target(selected_tag, df_clan, df_opponent, opp_stars)

if result["strategy"] == "BÔNUS":
    st.markdown(f"""
    <div class="bonus-card">
        <div class="label">🏆 PERFECT WAR</div>
        <div class="value">Ataque livre por bônus!</div>
        <div class="sub">Mapa fechado com 3⭐ em todas as bases</div>
    </div>
    """, unsafe_allow_html=True)
elif result["strategy"] == "ENCERRADO":
    st.markdown(f"""
    <div class="done-card">
        <div class="value">✅ {result['player_name']} já usou os 2 ataques</div>
    </div>
    """, unsafe_allow_html=True)
elif result["target_tag"] is not None:
    atk_label = "1º ATAQUE — ESPELHO+2" if result["next_attack"] == 1 else "2º ATAQUE"
    s_now = result["target_stars"]
    st.markdown(f"""
    <div class="target-card">
        <div class="label">{atk_label}</div>
        <div class="value">#{result['target_position']:02d} {result['target_name']}</div>
        <div class="sub">TH{result['target_th']} &nbsp;|&nbsp; {stars_html(s_now)}</div>
        <div class="sub" style="margin-top:0.6rem; font-size:0.85rem; color:#aaa;">📌 {result['reason']}</div>
    </div>
    """, unsafe_allow_html=True)

    if result.get("first_attack_info"):
        a = result["first_attack_info"]
        st.markdown(f"""
        <div class="card" style="text-align:center; margin-top:0.5rem">
            <h3>📊 Resultado do 1º Ataque</h3>
            <p style="color:#ccc">Alvo: {a['tag']} — {a['stars']}⭐ {a['pct']}%</p>
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown(f"""
    <div class="done-card">
        <div class="value">🏆 {result['reason']}</div>
    </div>
    """, unsafe_allow_html=True)

# ── War Map Table ──
st.markdown('<div class="card"><h3>📋 Mapa da Guerra</h3>', unsafe_allow_html=True)

rows_html = ""
for _, our in df_clan.iterrows():
    pos = our["map_position"]
    opp_row = df_opponent[df_opponent["map_position"] == pos]
    opp = opp_row.iloc[0] if not opp_row.empty else None
    if opp is not None:
        s = opp_stars.get(opp["tag"], 0)
        opp_cell = f"TH{opp['townhall_level']} {opp['name']}"
        star_cell = stars_html(s)
    else:
        opp_cell = "—"
        star_cell = ""
    highlight = ' style="background:rgba(255,210,0,0.08)"' if our["tag"] == selected_tag else ""
    rows_html += f"""
    <tr{highlight}>
        <td style="text-align:center;font-weight:700">#{pos}</td>
        <td>{our['name']}</td>
        <td style="text-align:center">TH{our['townhall_level']}</td>
        <td style="text-align:center">{our['attacks_used']}/2</td>
        <td>{opp_cell}</td>
        <td style="text-align:center">{star_cell}</td>
    </tr>"""

st.markdown(f"""
<div class="table-responsive">
<table class="war-table">
<thead><tr>
    <th style="text-align:center">#</th><th>Nosso Clã</th><th style="text-align:center">TH</th>
    <th style="text-align:center">ATK</th><th>Adversário</th><th style="text-align:center">⭐</th>
</tr></thead>
<tbody>{rows_html}</tbody>
</table>
</div>
</div>
""", unsafe_allow_html=True)
