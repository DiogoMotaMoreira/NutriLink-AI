# Load environment variables from a .env file.
from dotenv import load_dotenv
import streamlit as st
from streamlit.components.v1 import html
import os

import json
# Define structured output models using Pydantic
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

def encontrar_instituicao(food_item: str, food_allergens: list[str], institutions_data: list[dict]) -> InstitutionSelection:
    eligible_institutions = [
        inst for inst in institutions_data 
        if not any(allergen in inst.get("restricoes_alimentares", []) for allergen in food_allergens)
    ]

    if not eligible_institutions:
        return InstitutionSelection(institution_id=None, institution_name=None, reason="Conflito de alérgenos com todas as instituições.")

    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite", google_api_key=API_KEY)
    parser = PydanticOutputParser(pydantic_object=InstitutionSelection)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Select the best institution for the food donation based on profile. Output valid JSON."),
        ("human", "Food: '{food_item}', Allergens: {food_allergens}\nInstitutions:\n{institutions_for_prompt}\nSchema:\n{format_instructions}")
    ]).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | llm | parser
    return chain.invoke({
        "food_item": food_item,
        "food_allergens": food_allergens,
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
estafetas_data = load_json_data("estafetas.json")

# Inicializar lista de pedidos ativos no session_state
if "pedidos" not in st.session_state:
    st.session_state["pedidos"] = []

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
    st.rerun()

if btn_executar:
    with col_left:
        # Calcular estafetas disponíveis (excluir os já atribuídos)
        ids_ocupados = {p["logistica"].courier_id for p in st.session_state["pedidos"]}
        estafetas_disponiveis = [e for e in estafetas_data if e["id"] not in ids_ocupados]
        
        if not estafetas_disponiveis:
            st.error("⚠️ Todos os estafetas estão ocupados! Limpa os pedidos para recomeçar.")
        else:
            # 1. TRIAGEM
            st.markdown("---")
            st.write("🤖 **Agente 1: Triagem Alimentar**")
            triagem = triar_alimento(food_input, target_input)
            
            if triagem.status == "Aprovado":
                st.success(f"Status: {triagem.status}")
            else:
                st.error(f"Status: {triagem.status}")
                
            st.write(f"**Alérgenos:** {triagem.allergens}")
            st.caption(f"**Cuidados:** {triagem.care_instructions}")

            # 2. RECETOR
            if triagem.status == "Aprovado":
                st.markdown("---")
                st.write("🏠 **Agente 2: Seleção de Instituição**")
                recetor = encontrar_instituicao(food_input, triagem.allergens, instituicoes_porto_data)
                st.info(f"**Destino:** {recetor.institution_name}")
                st.caption(f"**Motivo:** {recetor.reason}")

                # 3. LOGÍSTICA
                if recetor.institution_name:
                    st.markdown("---")
                    st.write("🛵 **Agente 3: Atribuição Logística**")
                    logistica = atribuir_logistica(food_input, recetor.institution_name, estafetas_disponiveis)
                    
                    st.write(f"**Estafeta:** {logistica.courier_name} ({logistica.vehicle_type})")
                    st.write(f"**Tempo Estimado:** {logistica.estimated_time}")
                    st.caption(f"**Instruções:** {logistica.instructions}")
                    
                    # Adicionar pedido à lista de pedidos ativos
                    doador = next((d for d in doadores_data if d["nome"] == doador_selecionado), doadores_data[0])
                    st.session_state["pedidos"].append({
                        "alimento": food_input,
                        "publico_alvo": target_input,
                        "triagem": triagem,
                        "recetor": recetor,
                        "logistica": logistica,
                        "doador": doador
                    })

# Mostrar resumo dos pedidos ativos na sidebar esquerda
with col_left:
    if st.session_state["pedidos"]:
        st.markdown("---")
        st.subheader(f"📋 Pedidos Ativos ({len(st.session_state['pedidos'])})")
        for i, pedido in enumerate(st.session_state["pedidos"]):
            color = ["🔴", "🔵", "🟢", "🟡", "🟣", "🟠", "🟤"][i % 7]
            st.markdown(
                f"{color} **Pedido {i+1}:** {pedido['alimento']} → "
                f"{pedido['recetor'].institution_name}  \n"
                f"&nbsp;&nbsp;&nbsp;&nbsp;🛵 {pedido['logistica'].courier_name} ({pedido['logistica'].vehicle_type})"
            )

# RENDERIZAÇÃO DO MAPA
with col_right:
    st.subheader("🗺️ Visualização das Rotas em Tempo Real")
    
    if st.session_state["pedidos"]:
        pedidos = st.session_state["pedidos"]
        
        # Centrar mapa no primeiro doador
        centro = pedidos[0]["doador"]
        m = folium.Map(location=[centro["lat"], centro["lon"]], zoom_start=13)
        
        # Cores para cada pedido
        pedido_colors = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#e67e22", "#1abc9c"]
        
        # IDs dos estafetas atribuídos
        assigned_ids = {p["logistica"].courier_id for p in pedidos}
        
        # Mostrar TODOS os estafetas no mapa (disponíveis em cinzento)
        for est in estafetas_data:
            pos = est["posicao_atual"]
            veiculo = est["veiculo"]
            
            if est["id"] not in assigned_ids:
                folium.Marker(
                    [pos["lat"], pos["lon"]],
                    tooltip=f"⚪ {est['nome']} (Disponível) — {veiculo}",
                    icon=folium.Icon(color="gray", icon="user", prefix="fa")
                ).add_to(m)
        
        # Processar cada pedido
        route_animations = []
        
        for idx, pedido in enumerate(pedidos):
            color = pedido_colors[idx % len(pedido_colors)]
            doador = pedido["doador"]
            logistica = pedido["logistica"]
            
            # Encontrar coordenadas da instituição
            inst_coords = {"lat": 41.1505, "lon": -8.6320, "nome": pedido["recetor"].institution_name}
            for inst in instituicoes_porto_data:
                if inst.get("id") == pedido["recetor"].institution_id or inst.get("nome") == pedido["recetor"].institution_name:
                    inst_coords = inst
                    break
            
            # Marcador do Doador
            folium.Marker(
                [doador["lat"], doador["lon"]], 
                tooltip=f"🏪 Doador: {doador['nome']} (Pedido {idx+1})", 
                icon=folium.Icon(color="green", icon="store", prefix="fa")
            ).add_to(m)
            
            # Marcador da Instituição
            folium.Marker(
                [inst_coords["lat"], inst_coords["lon"]], 
                tooltip=f"🏠 IPSS: {inst_coords['nome']} (Pedido {idx+1})", 
                icon=folium.Icon(color="blue", icon="heart", prefix="fa")
            ).add_to(m)
            
            # Encontrar posição do estafeta
            est_data = next((e for e in estafetas_data if e["id"] == logistica.courier_id), None)
            if not est_data:
                continue
            
            est_pos = est_data["posicao_atual"]
            veiculo = est_data["veiculo"]
            
            # Determinar ícone do veículo
            if "Mota" in veiculo:
                fa_icon = "motorcycle"
            elif "Carrinha" in veiculo:
                fa_icon = "truck"
            elif "Bicicleta" in veiculo:
                fa_icon = "bicycle"
            elif "Carro" in veiculo:
                fa_icon = "car"
            else:
                fa_icon = "user"
            
            # Marcador do Estafeta (posição inicial)
            folium.Marker(
                [est_pos["lat"], est_pos["lon"]],
                tooltip=f"🛵 {logistica.courier_name} — Pedido {idx+1}: {pedido['alimento']} ({veiculo})",
                icon=folium.Icon(color="red", icon=fa_icon, prefix="fa")
            ).add_to(m)
            
            # Rota: Estafeta → Doador (tracejada)
            rota_pickup = obter_rota_osrm(est_pos["lat"], est_pos["lon"], doador["lat"], doador["lon"])
            folium.PolyLine(rota_pickup, color=color, weight=4, opacity=0.5, dash_array="10 5").add_to(m)
            
            # Rota: Doador → Instituição (sólida)
            rota_entrega = obter_rota_osrm(doador["lat"], doador["lon"], inst_coords["lat"], inst_coords["lon"])
            folium.PolyLine(rota_entrega, color=color, weight=5, opacity=0.8).add_to(m)
            
            # Rota completa para animação
            rota_completa = rota_pickup + rota_entrega[1:]
            route_animations.append({
                "rota": rota_completa,
                "name": logistica.courier_name,
                "vehicle": veiculo,
                "color": color,
                "pedido": f"Pedido {idx+1}: {pedido['alimento']}"
            })

        # Animação JS para TODOS os estafetas em simultâneo
        animations_json = json.dumps(route_animations, ensure_ascii=False)
        
        js_code = f"""
        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            setTimeout(function() {{
                var mapElement = document.querySelector('.folium-map');
                if (!mapElement) return;
                var map = window[mapElement.id];
                var animations = {animations_json};
                
                animations.forEach(function(anim) {{
                    var iconClass = "fa-motorcycle";
                    if (anim.vehicle.indexOf("Mota") !== -1) iconClass = "fa-motorcycle";
                    else if (anim.vehicle.indexOf("Carrinha") !== -1) iconClass = "fa-truck";
                    else if (anim.vehicle.indexOf("Bicicleta") !== -1) iconClass = "fa-bicycle";
                    else if (anim.vehicle.indexOf("Carro") !== -1) iconClass = "fa-car";
                    
                    var icon = L.divIcon({{
                        className: 'courier-marker',
                        html: "<div style='background-color:" + anim.color + "; color:white; padding:5px 10px; border-radius:20px; font-weight:bold; font-size:11px; white-space:nowrap; box-shadow:0 2px 6px rgba(0,0,0,0.4); border:2px solid white;'><i class='fa " + iconClass + "'></i> " + anim.name + "</div>",
                        iconSize: [150, 36],
                        iconAnchor: [75, 18]
                    }});
                    
                    var marker = L.marker(anim.rota[0], {{icon: icon}}).addTo(map);
                    var i = 0;
                    function move() {{
                        if (i < anim.rota.length) {{
                            marker.setLatLng(anim.rota[i]);
                            i++;
                            setTimeout(move, 100);
                        }}
                    }}
                    move();
                }});
            }}, 800);
        }});
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_code))
        
        # Legenda
        legend_items = ""
        for idx, pedido in enumerate(pedidos):
            color = pedido_colors[idx % len(pedido_colors)]
            legend_items += f'<span style="color:{color}">━━</span> {pedido["logistica"].courier_name}: {pedido["alimento"]}<br>'
        
        legend_html = f"""
        <div style="position:fixed; bottom:30px; left:30px; z-index:1000; background:white; 
                    padding:12px 16px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,0.3);
                    font-size:12px; font-family:sans-serif; max-width:300px;">
            <b>🗺️ Legenda</b><br>
            🟢 Doador &nbsp; 🔵 Instituição &nbsp; 🔴 Estafeta<br>
            ⚪ Estafeta Disponível<br>
            <span style="color:gray">╌╌╌</span> Pickup &nbsp; <span style="color:gray">━━</span> Entrega<br>
            <hr style="margin:4px 0">
            <b>Rotas Ativas:</b><br>
            {legend_items}
        </div>
        """
        m.get_root().html.add_child(folium.Element(legend_html))
        
        # Renderização HTML limpa e estável no Streamlit
        html(m._repr_html_(), height=600)
    else:
        st.info("Clica em '🚀 Executar Agentes IA' para criar um pedido. Podes criar vários pedidos — cada um terá o seu estafeta!")