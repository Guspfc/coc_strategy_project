"""
Motor de estratégia de guerra do Clash of Clans.
Módulo reutilizável com toda a lógica de negócio.
"""
import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()


def _get_secret(key: str, default=None):
    """Tenta ler do Streamlit secrets primeiro, depois do ambiente (.env)."""
    try:
        import streamlit as st
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


API_KEY = _get_secret("COC_API_KEY")
CLAN_TAG = _get_secret("COC_CLAN_TAG", "#PLV2VQQP")

if not API_KEY:
    raise RuntimeError("COC_API_KEY não definida. Configure em Streamlit Secrets ou .env.")

HEADERS = {"Authorization": f"Bearer {API_KEY}", "Accept": "application/json"}


def fetch_war_data(clan_tag: str = CLAN_TAG) -> dict:
    encoded = clan_tag.replace("#", "%23")
    url = f"https://cocproxy.royaleapi.dev/v1/clans/{encoded}/currentwar"
    r = requests.get(url, headers=HEADERS)
    r.raise_for_status()
    data = r.json()
    if data.get("state") == "notInWar":
        raise ValueError("O clã não está em guerra no momento.")
    return data


def build_members_df(members: list, side: str) -> pd.DataFrame:
    rows = []
    for m in members:
        attacks = m.get("attacks", [])
        rows.append({
            "tag": m["tag"], "name": m["name"],
            "townhall_level": m["townhallLevel"],
            "map_position": m["mapPosition"],
            "attacks_used": len(attacks),
            "attacks_detail": attacks, "side": side,
        })
    return pd.DataFrame(rows).sort_values("map_position").reset_index(drop=True)


def calc_opponent_stars(df_clan: pd.DataFrame, df_opponent: pd.DataFrame) -> dict:
    all_attacks = []
    for _, member in df_clan.iterrows():
        for atk in member["attacks_detail"]:
            all_attacks.append(atk)
    stars = {}
    for _, opp in df_opponent.iterrows():
        hits = [a for a in all_attacks if a["defenderTag"] == opp["tag"]]
        stars[opp["tag"]] = max((a["stars"] for a in hits), default=0)
    return stars


def _find_first_attack(pos, df_opp, stars):
    target_pos = pos + 2
    max_pos = df_opp["map_position"].max()
    if target_pos > max_pos:
        target_pos = max_pos

    primary = df_opp[df_opp["map_position"] == target_pos]
    if not primary.empty:
        o = primary.iloc[0]
        if stars.get(o["tag"], 0) < 3:
            s = stars.get(o["tag"], 0)
            reason = f"Alvo primário (espelho+2): #{int(o['map_position']):02d}" + (
                " ainda não atacado" if s == 0 else f" tem {s}⭐"
            )
            return o, reason

    for _, o in df_opp[df_opp["map_position"] > target_pos].sort_values("map_position").iterrows():
        if stars.get(o["tag"], 0) < 3:
            return o, f"Primário #{target_pos:02d} com 3⭐ → próxima abaixo"

    for _, o in df_opp[df_opp["map_position"] < target_pos].sort_values("map_position", ascending=False).iterrows():
        if stars.get(o["tag"], 0) < 3:
            return o, f"Todas abaixo com 3⭐ → subindo no mapa"

    return None, "Todas as bases já têm 3⭐"


def _find_second_attack(th, df_opp, stars):
    for label, filt in [
        (f"Mesmo TH{th}", df_opp["townhall_level"] == th),
        ("TH inferior", df_opp["townhall_level"] < th),
        ("TH superior", df_opp["townhall_level"] > th),
    ]:
        subset = df_opp[filt].sort_values("map_position", ascending=False)
        for _, o in subset.iterrows():
            if stars.get(o["tag"], 0) < 3:
                return o, f"{label}, de baixo pra cima"
    return None, "Todas as bases já têm 3⭐"


def determine_target(player_tag, df_clan, df_opponent, opponent_stars):
    row = df_clan[df_clan["tag"] == player_tag]
    if row.empty:
        raise ValueError(f"Jogador {player_tag} não encontrado no clã.")
    p = row.iloc[0]
    pos, th, used = p["map_position"], p["townhall_level"], p["attacks_used"]
    detail = p["attacks_detail"]

    res = {
        "player_tag": p["tag"], "player_name": p["name"],
        "player_position": pos, "player_th": th,
        "attacks_used": used, "attacks_remaining": 2 - used,
    }

    if all(s == 3 for s in opponent_stars.values()) and used < 2:
        res.update(strategy="BÔNUS", reason="Perfect War",
                   target_tag=None, target_name=None, target_position=None,
                   target_th=None, target_stars=None, next_attack=used + 1)
        return res

    if used == 0:
        t, reason = _find_first_attack(pos, df_opponent, opponent_stars)
        res["next_attack"] = 1
    elif used == 1:
        t, reason = _find_second_attack(th, df_opponent, opponent_stars)
        res["next_attack"] = 2
        a = detail[0]
        res["first_attack_info"] = {
            "tag": a["defenderTag"], "stars": a["stars"], "pct": a["destructionPercentage"]
        }
    else:
        res.update(strategy="ENCERRADO", reason="Ataques finalizados",
                   target_tag=None, target_name=None, target_position=None,
                   target_th=None, target_stars=None, next_attack=None)
        return res

    if t is not None:
        s = opponent_stars.get(t["tag"], 0)
        res.update(target_tag=t["tag"], target_name=t["name"],
                   target_position=int(t["map_position"]),
                   target_th=t["townhall_level"], target_stars=s,
                   strategy="ESPELHO+2" if used == 0 else "2º ATAQUE", reason=reason)
    else:
        res.update(target_tag=None, target_name=None, target_position=None,
                   target_th=None, target_stars=None, strategy="SEM ALVO", reason=reason)
    return res
