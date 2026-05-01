import sys
import os
import requests
import pandas as pd
from dotenv import load_dotenv

# Garante que o console do Windows suporte UTF-8 (emojis)
sys.stdout.reconfigure(encoding="utf-8")

# ============================================================
# Configurações (lidas do .env)
# ============================================================
load_dotenv()

API_KEY = os.getenv("COC_API_KEY")
CLAN_TAG = os.getenv("COC_CLAN_TAG", "#PLV2VQQP")

if not API_KEY:
    print("❌ COC_API_KEY não definida. Crie um arquivo .env com sua chave.")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json"
}


# ============================================================
# Funções de Acesso à API
# ============================================================
def fetch_war_data(clan_tag: str) -> dict:
    """Busca os dados da guerra atual do clã."""
    encoded_tag = clan_tag.replace("#", "%23")
    url = f"https://api.clashofclans.com/v1/clans/{encoded_tag}/currentwar"
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    data = response.json()

    if data.get("state") == "notInWar":
        raise ValueError("O clã não está em guerra no momento.")

    return data


# ============================================================
# Construção de DataFrames
# ============================================================
def build_members_df(members: list, side: str) -> pd.DataFrame:
    """
    Constrói um DataFrame com os membros de um lado da guerra.

    Args:
        members: lista de membros retornada pela API (clan.members ou opponent.members)
        side: 'clan' ou 'opponent'
    """
    rows = []
    for m in members:
        attacks = m.get("attacks", [])
        rows.append({
            "tag": m["tag"],
            "name": m["name"],
            "townhall_level": m["townhallLevel"],
            "map_position": m["mapPosition"],
            "attacks_used": len(attacks),
            "attacks_detail": attacks,
            "side": side,
        })

    df = pd.DataFrame(rows).sort_values("map_position").reset_index(drop=True)
    return df


# ============================================================
# Cálculo de Estrelas por Base Adversária
# ============================================================
def calc_opponent_stars(df_clan: pd.DataFrame, df_opponent: pd.DataFrame) -> dict:
    """
    Calcula o máximo de estrelas obtidas pelo nosso clã em cada base adversária.

    Retorna:
        dict: {opponent_tag: max_stars (0, 1, 2 ou 3)}
    """
    # Coleta todos os ataques do nosso clã
    all_attacks = []
    for _, member in df_clan.iterrows():
        for attack in member["attacks_detail"]:
            all_attacks.append(attack)

    # Para cada adversário, encontra o máximo de estrelas
    stars = {}
    for _, opp in df_opponent.iterrows():
        tag = opp["tag"]
        attacks_on_base = [a for a in all_attacks if a["defenderTag"] == tag]
        if attacks_on_base:
            stars[tag] = max(a["stars"] for a in attacks_on_base)
        else:
            stars[tag] = 0

    return stars


# ============================================================
# Lógica do 1º Ataque
# ============================================================
def find_first_attack_target(
    player_position: int,
    df_opponent: pd.DataFrame,
    opponent_stars: dict
) -> tuple:
    """
    1º Ataque: Atacar 2 posições ABAIXO do espelho.

    Regras:
        1. Alvo primário = espelho + 2 (ex: jogador #2 ataca o #4 adversário)
        2. Se o alvo já foi atacado mas tem estrela disponível (< 3⭐), atacá-lo
        3. Se o alvo tem 3⭐, procurar a próxima vila ABAIXO com estrela disponível
        4. Se TODAS abaixo têm 3⭐, procurar a vila ACIMA (de baixo pra cima)

    Returns:
        (opponent_row, motivo_str) ou (None, motivo_str)
    """
    target_position = player_position + 2
    max_position = df_opponent["map_position"].max()

    # Se a posição alvo ultrapassa o mapa, começa do último
    if target_position > max_position:
        target_position = max_position

    # --- Tenta o alvo primário (espelho + 2) ---
    primary = df_opponent[df_opponent["map_position"] == target_position]
    if not primary.empty:
        opp = primary.iloc[0]
        if opponent_stars.get(opp["tag"], 0) < 3:
            stars_now = opponent_stars.get(opp["tag"], 0)
            if stars_now == 0:
                reason = f"Alvo primário (espelho+2): #{int(opp['map_position']):02d} ainda não foi atacado"
            else:
                reason = f"Alvo primário (espelho+2): #{int(opp['map_position']):02d} tem {stars_now}⭐, estrela disponível"
            return opp, reason

    # --- Alvo primário tem 3⭐, buscar ABAIXO (posições maiores) ---
    below = df_opponent[df_opponent["map_position"] > target_position].sort_values("map_position")
    for _, opp in below.iterrows():
        if opponent_stars.get(opp["tag"], 0) < 3:
            reason = f"Primário #{target_position:02d} já tem 3⭐ → próxima abaixo com estrela disponível"
            return opp, reason

    # --- Todas abaixo têm 3⭐, buscar ACIMA (de baixo pra cima = posições menores, ordem decrescente) ---
    above = df_opponent[df_opponent["map_position"] < target_position].sort_values(
        "map_position", ascending=False
    )
    for _, opp in above.iterrows():
        if opponent_stars.get(opp["tag"], 0) < 3:
            reason = f"Todas abaixo do #{target_position:02d} com 3⭐ → subindo no mapa"
            return opp, reason

    return None, "Todas as bases adversárias já têm 3⭐!"


# ============================================================
# Lógica do 2º Ataque
# ============================================================
def find_second_attack_target(
    player_th: int,
    df_opponent: pd.DataFrame,
    opponent_stars: dict
) -> tuple:
    """
    2º Ataque: Prioriza oponente com mesmo TH, mais abaixo no mapa, com estrela disponível.

    Regras:
        1. Mesmo TH: mais abaixo no mapa (posição maior) com < 3⭐
        2. Se não há: TH inferior, de baixo pra cima com < 3⭐
        3. Se não há: TH superior, de baixo pra cima com < 3⭐

    Returns:
        (opponent_row, motivo_str) ou (None, motivo_str)
    """
    # --- 1. Mesmo nível de TH, mais abaixo no mapa (posição maior primeiro) ---
    same_th = df_opponent[df_opponent["townhall_level"] == player_th].sort_values(
        "map_position", ascending=False
    )
    for _, opp in same_th.iterrows():
        if opponent_stars.get(opp["tag"], 0) < 3:
            reason = f"Mesmo TH{player_th}, mais abaixo com estrela disponível"
            return opp, reason

    # --- 2. TH inferior, de baixo pra cima (posição maior primeiro) ---
    lower_th = df_opponent[df_opponent["townhall_level"] < player_th].sort_values(
        "map_position", ascending=False
    )
    for _, opp in lower_th.iterrows():
        if opponent_stars.get(opp["tag"], 0) < 3:
            reason = f"Sem TH{player_th} disponível → TH inferior (TH{opp['townhall_level']}), de baixo pra cima"
            return opp, reason

    # --- 3. TH superior, de baixo pra cima (posição maior primeiro) ---
    higher_th = df_opponent[df_opponent["townhall_level"] > player_th].sort_values(
        "map_position", ascending=False
    )
    for _, opp in higher_th.iterrows():
        if opponent_stars.get(opp["tag"], 0) < 3:
            reason = f"Sem TH{player_th} ou inferior disponível → TH superior (TH{opp['townhall_level']}), de baixo pra cima"
            return opp, reason

    return None, "Todas as bases adversárias já têm 3⭐!"


# ============================================================
# Determinação de Alvo Principal
# ============================================================
def determine_target(
    player_tag: str,
    df_clan: pd.DataFrame,
    df_opponent: pd.DataFrame,
    opponent_stars: dict
) -> dict:
    """
    Determina o alvo de um jogador na guerra com base na estratégia completa.

    ESTRATÉGIA:
        1º Ataque: Atacar 2 posições abaixo do espelho, com lógica de fallback
        2º Ataque: Mesmo TH mais abaixo → TH inferior → TH superior (de baixo pra cima)
    """
    # Busca o jogador no nosso clã
    player_row = df_clan[df_clan["tag"] == player_tag]
    if player_row.empty:
        raise ValueError(f"Jogador com tag {player_tag} não encontrado no clã.")

    player = player_row.iloc[0]
    player_position = player["map_position"]
    player_th = player["townhall_level"]
    attacks_used = player["attacks_used"]
    attacks_detail = player["attacks_detail"]

    result = {
        "player_tag": player["tag"],
        "player_name": player["name"],
        "player_position": player_position,
        "player_th": player_th,
        "attacks_used": attacks_used,
        "attacks_remaining": 2 - attacks_used,
    }

    # ---- Perfect War: todas as bases com 3⭐ → ataque livre por bônus ----
    all_three_starred = all(s == 3 for s in opponent_stars.values())
    if all_three_starred and attacks_used < 2:
        result["next_attack"] = attacks_used + 1
        result["target_tag"] = None
        result["target_name"] = None
        result["target_position"] = None
        result["target_th"] = None
        result["target_stars"] = None
        result["strategy"] = "BÔNUS"
        result["reason"] = "Perfect War"
        result["message"] = "🏆 PERFECT WAR! Mapa fechado com 3⭐ em todas as bases. Ataque livre por bônus!"
        return result

    # ---- 0 ataques feitos → próximo é o 1º ----
    if attacks_used == 0:
        result["next_attack"] = 1
        target, reason = find_first_attack_target(player_position, df_opponent, opponent_stars)

        if target is not None:
            stars_now = opponent_stars.get(target["tag"], 0)
            result["target_tag"] = target["tag"]
            result["target_name"] = target["name"]
            result["target_position"] = int(target["map_position"])
            result["target_th"] = target["townhall_level"]
            result["target_stars"] = stars_now
            result["strategy"] = "ESPELHO+2"
            result["reason"] = reason
            result["message"] = (
                f"🎯 1º Ataque → #{int(target['map_position']):02d} "
                f"{target['name']} (TH{target['townhall_level']}) "
                f"[{stars_now}⭐ atual]\n"
                f"     📌 {reason}"
            )
        else:
            result["target_tag"] = None
            result["target_name"] = None
            result["target_position"] = None
            result["target_th"] = None
            result["target_stars"] = None
            result["strategy"] = "SEM ALVO"
            result["reason"] = reason
            result["message"] = f"🏆 {reason}"

    # ---- 1 ataque feito → próximo é o 2º ----
    elif attacks_used == 1:
        first_attack = attacks_detail[0]
        result["next_attack"] = 2
        result["first_attack_target"] = first_attack["defenderTag"]
        result["first_attack_stars"] = first_attack["stars"]
        result["first_attack_destruction"] = first_attack["destructionPercentage"]

        target, reason = find_second_attack_target(player_th, df_opponent, opponent_stars)

        if target is not None:
            stars_now = opponent_stars.get(target["tag"], 0)
            result["target_tag"] = target["tag"]
            result["target_name"] = target["name"]
            result["target_position"] = int(target["map_position"])
            result["target_th"] = target["townhall_level"]
            result["target_stars"] = stars_now
            result["strategy"] = "2º ATAQUE"
            result["reason"] = reason
            result["message"] = (
                f"🆓 2º Ataque → #{int(target['map_position']):02d} "
                f"{target['name']} (TH{target['townhall_level']}) "
                f"[{stars_now}⭐ atual]\n"
                f"     📌 {reason}\n"
                f"     📊 1º ataque: {first_attack['defenderTag']} → "
                f"{first_attack['stars']}⭐ {first_attack['destructionPercentage']}%"
            )
        else:
            result["target_tag"] = None
            result["target_name"] = None
            result["target_position"] = None
            result["target_th"] = None
            result["target_stars"] = None
            result["strategy"] = "SEM ALVO"
            result["reason"] = reason
            result["message"] = (
                f"🏆 {reason}\n"
                f"     📊 1º ataque: {first_attack['defenderTag']} → "
                f"{first_attack['stars']}⭐ {first_attack['destructionPercentage']}%"
            )

    # ---- 2 ataques feitos → encerrado ----
    else:
        result["next_attack"] = None
        result["target_tag"] = None
        result["target_name"] = None
        result["target_position"] = None
        result["target_th"] = None
        result["target_stars"] = None
        result["strategy"] = "ENCERRADO"
        result["reason"] = "Ataques finalizados"
        result["message"] = "✅ Já usou os 2 ataques nesta guerra."

    return result


# ============================================================
# Exibição
# ============================================================
def print_war_summary(df_clan: pd.DataFrame, df_opponent: pd.DataFrame, opponent_stars: dict):
    """Imprime o mapa completo da guerra com status de estrelas."""
    print("=" * 90)
    print("  📋 MAPA DA GUERRA")
    print("=" * 90)
    print(f"  {'#':>3}  {'NOSSO CLÃ':^25}  {'vs':^4}  {'CLÃ ADVERSÁRIO':^25}  {'ATK':^6}  {'⭐':^4}")
    print("-" * 90)

    positions = sorted(df_clan["map_position"].unique())
    for pos in positions:
        our = df_clan[df_clan["map_position"] == pos].iloc[0]
        opp_row = df_opponent[df_opponent["map_position"] == pos]
        opp = opp_row.iloc[0] if not opp_row.empty else None

        our_info = f"{our['name'][:18]:18s} TH{our['townhall_level']}"
        if opp is not None:
            opp_stars = opponent_stars.get(opp["tag"], 0)
            star_display = "⭐" * opp_stars + "☆" * (3 - opp_stars)
            opp_info = f"TH{opp['townhall_level']} {opp['name'][:18]:18s}"
        else:
            opp_info = "--- SEM ESPELHO ---"
            star_display = "   "

        atk_status = f"{our['attacks_used']}/2"
        print(f"  {pos:>3}  {our_info:>25}  {'→':^4}  {opp_info:<25}  [{atk_status:^4}]  {star_display}")

    print("=" * 90)


def print_player_target(result: dict):
    """Imprime o resultado da determinação de alvo de forma legível."""
    print()
    print("=" * 65)
    print(f"  🏰 JOGADOR: {result['player_name']} ({result['player_tag']})")
    print(f"  📍 Posição: #{result['player_position']} | TH{result['player_th']}")
    print(f"  ⚔️  Ataques: {result['attacks_used']}/2 ({result['attacks_remaining']} restante(s))")
    print("-" * 65)
    for line in result["message"].split("\n"):
        print(f"  {line}")
    print("=" * 65)
    print()


# ============================================================
# Execução Principal
# ============================================================
if __name__ == "__main__":
    # Busca dados da guerra
    print("🔄 Buscando dados da guerra atual...")
    war_data = fetch_war_data(CLAN_TAG)
    print(f"✅ Guerra encontrada! Estado: {war_data['state']}")
    print(f"   Tamanho: {war_data['teamSize']}v{war_data['teamSize']}")
    print()

    # Constrói DataFrames
    df_clan = build_members_df(war_data["clan"]["members"], "clan")
    df_opponent = build_members_df(war_data["opponent"]["members"], "opponent")

    # Calcula estrelas em cada base adversária
    opponent_stars = calc_opponent_stars(df_clan, df_opponent)

    # Mostra mapa da guerra
    print_war_summary(df_clan, df_opponent, opponent_stars)

    # Consulta jogador
    player_tag = input("\n🔎 Digite a tag do jogador (ex: #P0CLYPGUJ): ").strip()
    if not player_tag.startswith("#"):
        player_tag = "#" + player_tag

    try:
        result = determine_target(player_tag, df_clan, df_opponent, opponent_stars)
        print_player_target(result)
    except ValueError as e:
        print(f"\n❌ Erro: {e}")
