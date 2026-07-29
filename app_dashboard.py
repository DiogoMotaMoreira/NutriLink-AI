import json
import requests
import streamlit as st
import folium
from streamlit.components.v1 import html

st.set_page_config(
    page_title="NutriLink-AI - Central de Operações Multi-Agente", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⚡ NutriLink-AI: Central de Operações & Frota (Porto)")
st.caption("Sistema Autónomo Multi-Agente com Relocalização de Estafetas em Tempo Real")

# ==============================================================================
# BASE DE DADOS GLOBAL (PORTO)
# ==============================================================================
DOADORES = [
    {"id": "d1", "nome": "Confeitaria do Bolhão", "lat": 41.1487, "lon": -8.6061, "item": "Pão e Bolos (15kg)"},
    {"id": "d2", "nome": "Pingo Doce - Sá da Bandeira", "lat": 41.1492, "lon": -8.6067, "item": "Fruta Fresca (40kg)"},
    {"id": "d3", "nome": "Abadia do Porto", "lat": 41.1468, "lon": -8.6072, "item": "Sopa e Refeições quentes"},
]

INSTITUICOES = [
    {"id": "i1", "nome": "Refood Porto Centro", "lat": 41.1505, "lon": -8.6320, "publico": "Famílias"},
    {"id": "i2", "nome": "CASA Sem-Abrigo Porto", "lat": 41.1378, "lon": -8.6095, "publico": "Sem-Abrigo"},
    {"id": "i3", "nome": "Centro Social Santo Ildefonso", "lat": 41.1498, "lon": -8.6045, "publico": "Crianças e Idosos"},
]

ESTAFETAS = [
    {"id": "e1", "nome": "Rui Silva (Mota 01)", "lat": 41.1478, "lon": -8.6110, "tipo": "motorcycle"},
    {"id": "e2", "nome": "Ana Marta (Carrinha 02)", "lat": 41.1530, "lon": -8.6010, "tipo": "truck"},
    {"id": "e3", "nome": "Tiago Gonçalves (Bike 03)", "lat": 41.1450, "lon": -8.6080, "tipo": "bicycle"}
]

# MISSÕES SIMULADAS (Cruzamento entre Doadores, Recetores e Estafetas)
MISSOES = [
    {
        "id": "m1",
        "doador": DOADORES[0],
        "instituicao": INSTITUICOES[0],
        "estafeta": ESTAFETAS[0],
        "cor": "#e74c3c"
    },
    {
        "id": "m2",
        "doador": DOADORES[1],
        "instituicao": INSTITUICOES[1],
        "estafeta": ESTAFETAS[1],
        "cor": "#8e44ad"
    },
    {
        "id": "m3",
        "doador": DOADORES[2],
        "instituicao": INSTITUICOES[2],
        "estafeta": ESTAFETAS[2],
        "cor": "#d35400"
    }
]

# ==============================================================================
# FUNÇÃO PARA CALCULAR ROTAS REAIS (OSRM)
# ==============================================================================
@st.cache_data(show_spinner=False)
def obter_rota_estrada(lat_origem, lon_origem, lat_destino, lon_destino):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon_origem},{lat_origem};{lon_destino},{lat_destino}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if "routes" in data and len(data["routes"]) > 0:
            coords = data["routes"][0]["geometry"]["coordinates"]
            return [[pt[1], pt[0]] for pt in coords]
    except Exception:
        pass
    return [[lat_origem, lon_origem], [lat_destino, lon_destino]]

# Pré-calcular as rotas por estrada para todas as missões
for m in MISSOES:
    rota_coleta = obter_rota_estrada(
        m["estafeta"]["lat"], m["estafeta"]["lon"],
        m["doador"]["lat"], m["doador"]["lon"]
    )
    rota_entrega = obter_rota_estrada(
        m["doador"]["lat"], m["doador"]["lon"],
        m["instituicao"]["lat"], m["instituicao"]["lon"]
    )
    m["rota_completa"] = rota_coleta + rota_entrega

# ==============================================================================
# PAINEL LATERAL (SIDEBAR COM MÉTRICAS E CONTROLO)
# ==============================================================================
with st.sidebar:
    st.header("📊 Status da Operação")
    st.metric("Entregas Ativas", f"{len(MISSOES)} Simultâneas")
    st.metric("Locais Envolvidos", f"{len(DOADORES)} Doadores | {len(INSTITUICOES)} IPSSs")
    st.metric("Estafetas em Trânsito", len(ESTAFETAS))
    st.divider()
    
    st.subheader("🛵 Frota & Relocalização")
    for m in MISSOES:
        st.markdown(f"**{m['estafeta']['nome']}**")
        st.caption(f"📍 Recolha: {m['doador']['nome']} ➡️ Entrega: {m['instituicao']['nome']}")
        st.progress(100, text="Rota Atribuída pelo AI Agent")
        st.write("")

# ==============================================================================
# CONSTRUÇÃO DO MAPA INTERATIVO (FOLIUM)
# ==============================================================================
m_mapa = folium.Map(location=[41.1495, -8.6110], zoom_start=14)

# 1. Adicionar Marcadores de Todos os Doadores (Verde)
for d in DOADORES:
    folium.Marker(
        [d["lat"], d["lon"]],
        popup=f"<b>Doador:</b> {d['nome']}<br><b>Item:</b> {d['item']}",
        tooltip=f"🏪 Doador: {d['nome']}",
        icon=folium.Icon(color="green", icon="shopping-cart", prefix="fa")
    ).add_to(m_mapa)

# 2. Adicionar Marcadores de Todas as Instituições (Azul)
for i in INSTITUICOES:
    folium.Marker(
        [i["lat"], i["lon"]],
        popup=f"<b>Instituição:</b> {i['nome']}<br><b>Público:</b> {i['publico']}",
        tooltip=f"🏥 IPSS: {i['nome']}",
        icon=folium.Icon(color="blue", icon="heart", prefix="fa")
    ).add_to(m_mapa)

# 3. Desenhar a Rota de Cada Missão com Cores Diferentes
for m in MISSOES:
    folium.PolyLine(
        m["rota_completa"],
        color=m["cor"],
        weight=5,
        opacity=0.6,
        tooltip=f"Rota de {m['estafeta']['nome']}"
    ).add_to(m_mapa)

# ==============================================================================
# MOTOR JS MULTI-ANIMAÇÃO & RELOCALIZAÇÃO
# ==============================================================================
missoes_json = json.dumps([
    {
        "id": m["id"],
        "nome": m["estafeta"]["nome"],
        "tipo": m["estafeta"]["tipo"],
        "cor": m["cor"],
        "rota": m["rota_completa"]
    }
    for m in MISSOES
])

js_engine = f"""
<script>
document.addEventListener("DOMContentLoaded", function() {{
    setTimeout(function() {{
        var mapElement = document.querySelector('.folium-map');
        if (!mapElement) return;
        var map = window[mapElement.id];

        var missoes = {missoes_json};

        // Criar os marcadores e contadores para cada estafeta simultâneo
        missoes.forEach(function(m) {{
            var iconHtml = "<div style='background-color:" + m.cor + "; color:white; width:34px; height:34px; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 0 10px rgba(0,0,0,0.5); border: 2px solid white;'><i class='fa fa-" + m.tipo + "' style='font-size:16px;'></i></div>";
            
            var estafetaIcon = L.divIcon({{
                className: 'mota-animada-' + m.id,
                html: iconHtml,
                iconSize: [34, 34],
                iconAnchor: [17, 17]
            }});

            var marker = L.marker(m.rota[0], {{icon: estafetaIcon}}).addTo(map);
            var index = 0;

            function animar() {{
                if (index < m.rota.length) {{
                    marker.setLatLng(m.rota[index]);
                    index++;
                    setTimeout(animar, 100 + Math.random() * 40); // Pequena variação de velocidade entre eles
                }} else {{
                    // SIMULAÇÃO DE RELOCALIZAÇÃO AUTOMÁTICA
                    // Quando chega ao destino final, o estafeta aguarda e reinicia uma nova atribuição
                    setTimeout(function() {{
                        index = 0;
                        animar();
                    }}, 2500);
                }}
            }}

            animar();
        }});

    }}, 800);
}});
</script>
"""

m_mapa.get_root().html.add_child(folium.Element(js_engine))

# Renderizar o painel do mapa no Streamlit
html(m_mapa._repr_html_(), height=650)