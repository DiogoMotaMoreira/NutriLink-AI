import time
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# Configuração da página do Streamlit
st.set_page_config(page_title="NutriLink-AI - Simulação em Tempo Real", layout="wide")
st.title("🛵 NutriLink-AI: Simulação de Entrega no Porto")

# ==============================================================================
# DADOS REAIS DE EXEMPLO (PORTO)
# ==============================================================================
DOADOR = {
    "nome": "Confeitaria do Bolhão",
    "lat": 41.1487,
    "lon": -8.6061
}

INSTITUICAO = {
    "nome": "Refood Porto Centro",
    "lat": 41.1505,
    "lon": -8.6320
}

ESTAFETA = {
    "nome": "Rui Silva (Mota)",
    "posicao_inicial": {"lat": 41.1478, "lon": -8.6110}
}

# ==============================================================================
# FUNÇÃO PARA OBTER ROTA REAL POR ESTRADA (API OSRM)
# ==============================================================================
def obter_rota_estrada(lat_origem, lon_origem, lat_destino, lon_destino):
    """Obtém as coordenadas ponto a ponto pelas estradas usando OSRM."""
    url = f"http://router.project-osrm.org/route/v1/driving/{lon_origem},{lat_origem};{lon_destino},{lat_destino}?overview=full&geometries=geojson"
    
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if "routes" in data and len(data["routes"]) > 0:
            # OSRM devolve [lon, lat], invertemos para [lat, lon] que o Folium usa
            coordenadas = data["routes"][0]["geometry"]["coordinates"]
            return [[pt[1], pt[0]] for pt in coordenadas]
    except Exception as e:
        st.error(f"Erro ao obter rota por estrada: {e}")
    
    # Fallback: se a API falhar, devolve linha reta
    return [[lat_origem, lon_origem], [lat_destino, lon_destino]]

# ==============================================================================
# INTERFACE E SIMULAÇÃO DA ANIMAÇÃO
# ==============================================================================
col1, col2 = st.columns([1, 3])

with col1:
    st.subheader("📋 Detalhes da Missão")
    st.markdown(f"**Doador:** {DOADOR['nome']}")
    st.markdown(f"**Destino:** {INSTITUICAO['nome']}")
    st.markdown(f"**Estafeta:** {ESTAFETA['nome']}")
    
    iniciar = st.button("🚀 Iniciar Simulação de Entrega", use_container_width=True)

with col2:
    # 1. Obter rota real da posição do estafeta até ao doador, e depois até à instituição
    rota_ate_doador = obter_rota_estrada(
        ESTAFETA["posicao_inicial"]["lat"], ESTAFETA["posicao_inicial"]["lon"],
        DOADOR["lat"], DOADOR["lon"]
    )
    rota_entrega = obter_rota_estrada(
        DOADOR["lat"], DOADOR["lon"],
        INSTITUICAO["lat"], INSTITUICAO["lon"]
    )
    
    # Rota completa percorrida pelas estradas do Porto
    rota_completa = rota_ate_doador + rota_entrega
    
    # Estado da animação no Streamlit
    if "passo" not in st.session_state:
        st.session_state.passo = 0

    if iniciar:
        st.session_state.passo = 0

    # Posição atual do estafeta na animação
    pos_atual = rota_completa[st.session_state.passo]

    # Criar o mapa Folium centrado no Porto
    m = folium.Map(location=[41.1495, -8.6110], zoom_start=14)

    # Marcador do Doador (Verde)
    folium.Marker(
        [DOADOR["lat"], DOADOR["lon"]],
        popup=f"Store: {DOADOR['nome']}",
        tooltip=DOADOR["nome"],
        icon=folium.Icon(color="green", icon="shopping-cart", prefix="fa")
    ).add_to(m)

    # Marcador da IPSS (Azul)
    folium.Marker(
        [INSTITUICAO["lat"], INSTITUICAO["lon"]],
        popup=f"IPSS: {INSTITUICAO['nome']}",
        tooltip=INSTITUICAO["nome"],
        icon=folium.Icon(color="blue", icon="heart", prefix="fa")
    ).add_to(m)

    # Linha da estrada desenhada no mapa (Laranja)
    folium.PolyLine(rota_completa, color="orange", weight=5, opacity=0.7).add_to(m)

    # Marcador do Estafeta em Movimento (Vermelho)
    folium.Marker(
        pos_atual,
        popup=f"Estafeta: {ESTAFETA['nome']}",
        tooltip="Estafeta em trânsito",
        icon=folium.Icon(color="red", icon="motorcycle", prefix="fa")
    ).add_to(m)

    # Renderizar o mapa no Streamlit
    st_folium(m, width=900, height=550, key="mapa_porto")

    # Loop de Animação: avança os pontos da estrada um a um
    if iniciar or (0 < st.session_state.passo < len(rota_completa) - 1):
        if st.session_state.passo < len(rota_completa) - 1:
            # Salta alguns pontos da rota para andar a uma velocidade agradável
            st.session_state.passo = min(st.session_state.passo + 3, len(rota_completa) - 1)
            time.sleep(0.1)
            st.rerun()
        else:
            st.success("🎉 Entrega concluída com sucesso no Centro do Porto!")