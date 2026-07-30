# Load environment variables from a .env file.
from dotenv import load_dotenv
import streamlit as st
from streamlit.components.v1 import html
import os
import time
import json
import folium
from pydantic import BaseModel
from typing import Literal

# Langchain imports that we will use to interact with Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import requests

# Pulling our Gemini API key from our .env file.
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    API_KEY = os.getenv("GEMINI_API_KEY")

# Pydantic models for structured output
class FoodAnalysisResult(BaseModel):
    status: Literal["Aprovado", "Rejeitado"]  # MUST be exactly "Aprovado" or "Rejeitado"
    allergens: list[str] = []
    care_instructions: str = "" # e.g., "necessidade de mala térmica"

class InstitutionSelection(BaseModel):
    institution_id: str | None = None
    institution_name: str | None = None
    reason: str = ""

class LogisticsResult(BaseModel):
    courier_id: str
    courier_name: str
    vehicle_type: str  # ex: "Mota elétrica", "Carrinha Comercial"
    estimated_time: str
    instructions: str

# Function to load institutions data
def load_json_data(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def triar_alimento(food_item: str, target_audience: str) -> FoodAnalysisResult:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=API_KEY)
    parser = PydanticOutputParser(pydantic_object=FoodAnalysisResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a food safety expert. Analyze the food item for safety and suitability. "
                   "The 'status' field MUST be exactly 'Aprovado' (if safe and suitable) or 'Rejeitado' (if unsafe or unsuitable). "
                   "Do NOT use any other value for status. Output valid JSON."),
        ("human", "Analyze '{food_item}' for audience '{target_audience}'. Schema:\n{format_instructions}")
    ]).partial(format_instructions=parser.get_format_instructions())
    
    chain = prompt | llm | parser
    return chain.invoke({"food_item": food_item, "target_audience": target_audience})

def encontrar_instituicao(
    food_item: str, 
    food_allergens: list[str], 
    institutions_data: list[dict],
    target_audience: str,
    doador_lat: float,
    doador_lon: float
) -> InstitutionSelection:
    import math
    
    def calcular_distancia(lat1, lon1, lat2, lon2):
        R = 6371.0  # Earth radius in km
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(R * c, 2)

    eligible_institutions = []
    for inst in institutions_data:
        inst_allergens = [r.lower().strip() for r in inst.get("restricoes_alimentares", [])]
        has_conflict = any(allergen.lower().strip() in inst_allergens for allergen in food_allergens)
        if not has_conflict:
            inst_copy = dict(inst)
            inst_copy["distancia_do_doador_km"] = calcular_distancia(doador_lat, doador_lon, inst["lat"], inst["lon"])
            eligible_institutions.append(inst_copy)

    if not eligible_institutions:
        return InstitutionSelection(
            institution_id=None, 
            institution_name=None, 
            reason="Conflito de alérgenos com todas as instituições."
        )

    # Sort by distance first so the LLM has proximity context
    eligible_institutions.sort(key=lambda x: x["distancia_do_doador_km"])

    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=API_KEY)
    parser = PydanticOutputParser(pydantic_object=InstitutionSelection)
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a social coordinator matching food donations to local institutions (IPSS) in Porto. "
         "Select the BEST institution for this donation. "
         "Criteria for 'best':\n"
         "1. Target Audience Match: The institution's 'publico_alvo' list should ideally match or contain the donation's 'target_audience'.\n"
         "2. Proximity: Closer institutions ('distancia_do_doador_km') are preferred to minimize travel time.\n"
         "3. Capacity: Consider their daily meals capability ('refeicoes_diarias').\n"
         "Provide a detailed justification for your choice in the 'reason' field. "
         "Output valid JSON."),
        ("human", 
         "Food: '{food_item}'\n"
         "Allergens: {food_allergens}\n"
         "Target Audience: '{target_audience}'\n"
         "Institutions:\n{institutions_for_prompt}\n\n"
         "Schema:\n{format_instructions}")
    ]).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | llm | parser
    return chain.invoke({
        "food_item": food_item,
        "food_allergens": food_allergens,
        "target_audience": target_audience,
        "institutions_for_prompt": json.dumps(eligible_institutions, ensure_ascii=False)
    })

def atribuir_logistica(alimento: str, instituicao_nome: str, estafetas_disponiveis: list[dict]) -> LogisticsResult:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=API_KEY)
    parser = PydanticOutputParser(pydantic_object=LogisticsResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are a logistics coordinator for food rescue deliveries in Porto. "
         "You MUST select exactly ONE courier from the provided list — use their exact 'id' and 'nome'. "
         "Choose the most suitable courier based on vehicle type and cargo capacity for the food item. "
         "Output valid JSON."),
        ("human", 
         "Assign ONE courier to deliver '{alimento}' to '{instituicao_nome}'.\n\n"
         "Available couriers:\n{estafetas_json}\n\nSchema:\n{format_instructions}")
    ]).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | llm | parser
    return chain.invoke({
        "alimento": alimento, 
        "instituicao_nome": instituicao_nome,
        "estafetas_json": json.dumps(estafetas_disponiveis, ensure_ascii=False)
    })

# API gratuita para calcular rota real pelas estradas do Porto
def obter_rota_osrm(lat1, lon1, lat2, lon2):
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
    try:
        r = requests.get(url, timeout=3).json()
        coords = r["routes"][0]["geometry"]["coordinates"]
        return [[pt[1], pt[0]] for pt in coords]
    except Exception:
        return [[lat1, lon1], [lat2, lon2]]


# ==============================================================================
# INTERFACE STREAMLIT
# ==============================================================================
st.set_page_config(page_title="NutriLink-AI", layout="wide")
st.title("🥗 NutriLink-AI: Painel de Resgate Alimentar Autónomo")

institutions_data = load_json_data("institutions.json")
doadores_data = load_json_data("doadores.json")
instituicoes_porto_data = load_json_data("instituicoes_porto.json")

# Inicializar session_state
if "pedidos" not in st.session_state:
    st.session_state["pedidos"] = []

if "pedidos_executados" not in st.session_state:
    st.session_state["pedidos_executados"] = []

if "estafetas" not in st.session_state:
    st.session_state["estafetas"] = load_json_data("estafetas.json")

estafetas_data = st.session_state["estafetas"]

# Verificar se algum pedido foi concluído
agora = time.time()
novos_pedidos_ativos = []
pedidos_concluidos_nesta_execucao = False

for pedido in st.session_state["pedidos"]:
    passo_segundos = 0.12
    total_pontos = len(pedido.get("rota_completa", []))
    tempo_total = total_pontos * passo_segundos
    tempo_decorrido = agora - pedido["start_timestamp"]
    
    if tempo_decorrido >= tempo_total:
        # Pedido Concluído!
        # Encontrar a localização da instituição destinatária para atualizar o estafeta
        inst_coords = {"lat": 41.1505, "lon": -8.6320} # Default
        for inst in instituicoes_porto_data:
            if inst.get("id") == pedido["recetor"].institution_id or inst.get("nome") == pedido["recetor"].institution_name:
                inst_coords = inst
                break
                
        # Atualizar a posição do estafeta no session_state para a IPSS de entrega
        courier_id = pedido["logistica"].courier_id
        for est in st.session_state["estafetas"]:
            if est["id"] == courier_id:
                est["posicao_atual"] = {"lat": inst_coords["lat"], "lon": inst_coords["lon"]}
                break
        
        pedido["end_timestamp"] = pedido["start_timestamp"] + tempo_total
        st.session_state["pedidos_executados"].append(pedido)
        pedidos_concluidos_nesta_execucao = True
    else:
        novos_pedidos_ativos.append(pedido)

if pedidos_concluidos_nesta_execucao:
    st.session_state["pedidos"] = novos_pedidos_ativos
    st.toast("✅ Um ou mais resgates alimentares foram concluídos com sucesso!")
    st.rerun()

col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("📥 Novo Excedente Alimentar")
    doador_nomes = [d["nome"] for d in doadores_data]
    doador_selecionado = st.selectbox("Doador", doador_nomes)
    food_input = st.text_input("Alimento Doado", value="Maçã")
    target_input = st.selectbox("Público-Alvo", ["crianças em idade escolar", "sem-abrigo", "idosos"])
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        btn_executar = st.button("🚀 Executar Agentes IA", use_container_width=True)
    with col_btn2:
        btn_limpar = st.button("🗑️ Limpar Pedidos", use_container_width=True)

if btn_limpar:
    st.session_state["pedidos"] = []
    st.session_state["pedidos_executados"] = []
    st.session_state["estafetas"] = load_json_data("estafetas.json")
    st.rerun()

if btn_executar:
    with col_left:
        # Calcular estafetas disponíveis (excluir os já atribuídos)
        ids_ocupados = {p["logistica"].courier_id for p in st.session_state["pedidos"]}
        estafetas_disponiveis = [e for e in st.session_state["estafetas"] if e["id"] not in ids_ocupados]
        
        if not estafetas_disponiveis:
            st.error("⚠️ Todos os estafetas estão ocupados! Limpa os pedidos para recomeçar.")
        else:
            # Obter o doador selecionado
            doador = next((d for d in doadores_data if d["nome"] == doador_selecionado), doadores_data[0])
            
            # 1. TRIAGEM Alimentar
            triagem = triar_alimento(food_input, target_input)
            
            if triagem.status == "Aprovado":
                # 2. Seleção inteligente da melhor instituição (escolhe a melhor IPSS com base no público-alvo e distância)
                recetor = encontrar_instituicao(
                    food_input, 
                    triagem.allergens, 
                    instituicoes_porto_data,
                    target_input,
                    doador["lat"],
                    doador["lon"]
                )

                if recetor.institution_name:
                    # 3. Atribuição Logística
                    logistica = atribuir_logistica(food_input, recetor.institution_name, estafetas_disponiveis)
                    
                    # Pre-calcular e guardar rotas/dados geográficos para otimizar desempenho
                    inst_coords = {"lat": 41.1505, "lon": -8.6320, "nome": recetor.institution_name}
                    for inst in instituicoes_porto_data:
                        if inst.get("id") == recetor.institution_id or inst.get("nome") == recetor.institution_name:
                            inst_coords = inst
                            break
                    
                    est_data = next((e for e in st.session_state["estafetas"] if e["id"] == logistica.courier_id), estafetas_disponiveis[0])
                    est_pos = est_data["posicao_atual"]
                    
                    rota_pickup = obter_rota_osrm(est_pos["lat"], est_pos["lon"], doador["lat"], doador["lon"])
                    rota_entrega = obter_rota_osrm(doador["lat"], doador["lon"], inst_coords["lat"], inst_coords["lon"])
                    rota_completa = rota_pickup + rota_entrega[1:]
                    
                    st.session_state["pedidos"].append({
                        "alimento": food_input,
                        "publico_alvo": target_input,
                        "triagem": triagem,
                        "recetor": recetor,
                        "logistica": logistica,
                        "doador": doador,
                        "start_timestamp": time.time(),
                        "rota_pickup": rota_pickup,
                        "rota_entrega": rota_entrega,
                        "rota_completa": rota_completa,
                        "inst_coords": inst_coords
                    })
                    st.rerun()
                else:
                    st.warning("⚠️ Não foi possível encontrar uma instituição adequada para este pedido.")
            else:
                st.error("❌ O alimento foi rejeitado na triagem. Não é possível prosseguir com o pedido.")

# Exibição organizada em abas (Pedidos Ativos vs Pedidos Executados)
with col_left:
    st.markdown("---")
    tab_ativos, tab_executados = st.tabs(["📋 Pedidos Ativos", "✅ Pedidos Executados"])
    
    with tab_ativos:
        if st.session_state["pedidos"]:
            st.write(f"**Pedidos em curso ({len(st.session_state['pedidos'])})**")
            for i, pedido in enumerate(st.session_state["pedidos"]):
                color_emoji = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "🟤"][i % 7]
                
                expander_title = (
                    f"{color_emoji} **Pedido {i+1}:** {pedido['alimento']} "
                    f"→ {pedido['recetor'].institution_name} "
                    f"🛵 {pedido['logistica'].courier_name} ({pedido['logistica'].vehicle_type})"
                )
                
                tempo_decorrido = time.time() - pedido["start_timestamp"]
                tempo_total = len(pedido["rota_completa"]) * 0.12
                tempo_restante = max(0.0, tempo_total - tempo_decorrido)
                
                with st.expander(expander_title):
                    st.info(f"⏳ **Em trânsito...** Tempo restante estimado: {tempo_restante:.1f}s")
                    st.markdown("---")
                    st.write("🤖 **Agente 1: Triagem Alimentar**")
                    st.write(f"**Status:** {pedido['triagem'].status}")
                    st.write(f"**Alérgenos:** {', '.join(pedido['triagem'].allergens) if pedido['triagem'].allergens else 'Nenhum'}")
                    st.caption(f"**Cuidados:** {pedido['triagem'].care_instructions}")
                    
                    st.markdown("---")
                    st.write("🏠 **Agente 2: Seleção de Instituição**")
                    st.write(f"**Destino:** {pedido['recetor'].institution_name}")
                    st.caption(f"**Motivo:** {pedido['recetor'].reason}")
                    
                    st.markdown("---")
                    st.write("🛵 **Agente 3: Atribuição Logística**")
                    st.write(f"**Estafeta:** {pedido['logistica'].courier_name} ({pedido['logistica'].vehicle_type})")
                    st.write(f"**Tempo Estimado:** {pedido['logistica'].estimated_time}")
                    st.caption(f"**Instruções:** {pedido['logistica'].instructions}")
                    
                    st.markdown("---")
                    st.write("🏪 **Doador:**")
                    st.write(f"**Nome:** {pedido['doador']['nome']}")
                    st.write(f"**Localização:** Lat: {pedido['doador']['lat']}, Lon: {pedido['doador']['lon']}")
        else:
            st.info("Nenhum pedido ativo em curso.")
            
    with tab_executados:
        if st.session_state["pedidos_executados"]:
            st.write(f"**Pedidos concluídos ({len(st.session_state['pedidos_executados'])})**")
            for i, pedido in enumerate(st.session_state["pedidos_executados"]):
                expander_title = (
                    f"✅ **Pedido {i+1} (Concluído):** {pedido['alimento']} "
                    f"→ {pedido['recetor'].institution_name} "
                    f"🛵 {pedido['logistica'].courier_name}"
                )
                
                with st.expander(expander_title):
                    st.success("🎉 **Resgate concluído com sucesso!**")
                    st.write(f"**Alimento:** {pedido['alimento']}")
                    st.write(f"**Público-Alvo:** {pedido['publico_alvo']}")
                    
                    st.markdown("---")
                    st.write("🤖 **Agente 1: Triagem Alimentar**")
                    st.write(f"**Status:** {pedido['triagem'].status}")
                    st.write(f"**Alérgenos:** {', '.join(pedido['triagem'].allergens) if pedido['triagem'].allergens else 'Nenhum'}")
                    st.caption(f"**Cuidados:** {pedido['triagem'].care_instructions}")
                    
                    st.markdown("---")
                    st.write("🏠 **Agente 2: Seleção de Instituição**")
                    st.write(f"**Destino:** {pedido['recetor'].institution_name}")
                    st.caption(f"**Motivo:** {pedido['recetor'].reason}")
                    
                    st.markdown("---")
                    st.write("🛵 **Agente 3: Atribuição Logística**")
                    st.write(f"**Estafeta:** {pedido['logistica'].courier_name} ({pedido['logistica'].vehicle_type})")
                    st.caption(f"**Instruções:** {pedido['logistica'].instructions}")
                    
                    st.markdown("---")
                    st.write("🏪 **Doador:**")
                    st.write(f"**Nome:** {pedido['doador']['nome']}")
        else:
            st.info("Nenhum pedido foi concluído ainda.")

with col_right:
    st.subheader("🗺️ Visualização das Rotas em Tempo Real")
    
    # Desenhar o mapa geral centrado no Porto
    centro_lat = 41.1500
    centro_lon = -8.6100
    if st.session_state["pedidos"]:
        centro_lat = st.session_state["pedidos"][0]["doador"]["lat"]
        centro_lon = st.session_state["pedidos"][0]["doador"]["lon"]
        
    m = folium.Map(location=[centro_lat, centro_lon], zoom_start=13)
    
    # Desenhar todos os doadores (verde)
    for d in doadores_data:
        folium.Marker(
            [d["lat"], d["lon"]], 
            tooltip=f"🏪 Doador: {d['nome']}", 
            icon=folium.Icon(color="green", icon="store", prefix="fa")
        ).add_to(m)
        
    # Desenhar todas as instituições (azul)
    for inst in instituicoes_porto_data:
        folium.Marker(
            [inst["lat"], inst["lon"]], 
            tooltip=f"🏠 IPSS: {inst['nome']}", 
            icon=folium.Icon(color="blue", icon="heart", prefix="fa")
        ).add_to(m)
        
    # Mostrar todos os estafetas (cinzento se livre, caso contrário ficará associado ao pedido)
    assigned_ids = {p["logistica"].courier_id for p in st.session_state["pedidos"]}
    for est in st.session_state["estafetas"]:
        pos = est["posicao_atual"]
        veiculo = est["veiculo"]
        
        if est["id"] not in assigned_ids:
            folium.Marker(
                [pos["lat"], pos["lon"]],
                tooltip=f"⚪ {est['nome']} (Disponível) — {veiculo}",
                icon=folium.Icon(color="gray", icon="user", prefix="fa")
            ).add_to(m)
            
    # Processar animações para pedidos ativos
    route_animations = []
    pedido_colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#e67e22", "#1abc9c"]
    
    for idx, pedido in enumerate(st.session_state["pedidos"]):
        color = pedido_colors[idx % len(pedido_colors)]
        doador = pedido["doador"]
        inst_coords = pedido["inst_coords"]
        
        # Marcador especial ativo da instituição destinatária do pedido ativo
        folium.Marker(
            [inst_coords["lat"], inst_coords["lon"]], 
            tooltip=f"🏠 Destino Ativo (Pedido {idx+1}): {inst_coords['nome']}", 
            icon=folium.Icon(color="orange", icon="star", prefix="fa")
        ).add_to(m)
        
        # Desenhar rotas pré-calculadas
        folium.PolyLine(pedido["rota_pickup"], color=color, weight=4, opacity=0.5, dash_array="10 5").add_to(m)
        folium.PolyLine(pedido["rota_entrega"], color=color, weight=5, opacity=0.8).add_to(m)
        
        segundos_decorridos = time.time() - pedido["start_timestamp"]
        
        route_animations.append({
            "rota": pedido["rota_completa"],
            "name": pedido["logistica"].courier_name,
            "vehicle": pedido["logistica"].vehicle_type,
            "color": color,
            "tempo_decorrido": segundos_decorridos
        })
        
    if route_animations:
        animations_json = json.dumps(route_animations, ensure_ascii=False)
        
        js_code = f"""
        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            setTimeout(function() {{
                var mapElement = document.querySelector('.folium-map');
                if (!mapElement) return;
                var map = window[mapElement.id];

                var animations = {animations_json};
                var passoEmSegundos = 0.12; // Velocidade do movimento (120ms por ponto)

                animations.forEach(function(anim) {{
                    var iconClass = "fa-motorcycle";
                    if (anim.vehicle.indexOf("Mota") !== -1) iconClass = "fa-motorcycle";
                    else if (anim.vehicle.indexOf("Carrinha") !== -1) iconClass = "fa-truck";
                    else if (anim.vehicle.indexOf("Bicicleta") !== -1) iconClass = "fa-bicycle";

                    var icon = L.divIcon({{
                        className: 'courier-marker',
                        html: "<div style='background-color:" + anim.color + "; color:white; padding:5px 10px; border-radius:20px; font-weight:bold; font-size:11px; white-space:nowrap; box-shadow:0 2px 6px rgba(0,0,0,0.4); border:2px solid white;'><i class='fa " + iconClass + "'></i> " + anim.name + "</div>",
                        iconSize: [140, 32],
                        iconAnchor: [70, 16]
                    }});

                    var i = Math.floor(anim.tempo_decorrido / passoEmSegundos);
                    if (i >= anim.rota.length) i = anim.rota.length - 1;

                    var marker = L.marker(anim.rota[i], {{icon: icon}}).addTo(map);

                    function move() {{
                        if (i < anim.rota.length) {{
                            marker.setLatLng(anim.rota[i]);
                            i++;
                            setTimeout(move, passoEmSegundos * 1000);
                        }} else {{
                            marker.setLatLng(anim.rota[anim.rota.length - 1]);
                        }}
                    }}
                    move();
                }});
            }}, 800);
        }});
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_code))
        
    html(m._repr_html_(), height=600)

# Auto-rerun inteligente no momento em que o próximo pedido for concluído (evita recarregamentos constantes do mapa)
if st.session_state["pedidos"]:
    tempos_restantes = []
    for pedido in st.session_state["pedidos"]:
        passo_segundos = 0.12
        total_pontos = len(pedido.get("rota_completa", []))
        tempo_total = total_pontos * passo_segundos
        tempo_decorrido = time.time() - pedido["start_timestamp"]
        tempo_restante = tempo_total - tempo_decorrido
        if tempo_restante > 0:
            tempos_restantes.append(tempo_restante)
            
    if tempos_restantes:
        # Aguarda o tempo exato até o próximo pedido terminar (com uma pequena folga de 0.5s)
        proximo_tempo = min(tempos_restantes) + 0.5
        time.sleep(proximo_tempo)
        st.rerun()