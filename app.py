# Load environment variables from a .env file.
from dotenv import load_dotenv
import streamlit as st

import json
# Define structured output models using Pydantic
import folium
from google import genai
from pydantic import BaseModel

# Langchain imports that we will use to interact with Gemini
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
import requests


# Pulling our Gemini API key from our .env file.
load_dotenv()

# Pydantic models for structured output
class FoodAnalysisResult(BaseModel):
    status: str  # "Aprovado" or "Rejeitado"
    allergens: list[str] = []
    care_instructions: str = "" # e.g., "necessidade de mala térmica"

class InstitutionSelection(BaseModel):
    institution_id: str | None = None
    institution_name: str | None = None
    reason: str = ""

class LogisticsResult(BaseModel):
    courier_name: str
    vehicle_type: str  # ex: "Mota", "Carrinha"
    estimated_time: str
    instructions: str

# Function to load institutions data
def load_json_data(file_path: str):
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def triar_alimento(food_item: str, target_audience: str) -> FoodAnalysisResult:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite") # Usar gemini-3.5-flash-lite para evitar o aviso
    parser = PydanticOutputParser(pydantic_object=FoodAnalysisResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are a food safety expert. Analyze the food item. Output valid JSON."),
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

    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
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

def atribuir_logistica(alimento: str, instituicao_nome: str) -> LogisticsResult:
    llm = ChatGoogleGenerativeAI(model="gemini-3.5-flash-lite")
    parser = PydanticOutputParser(pydantic_object=LogisticsResult)
    prompt = ChatPromptTemplate.from_messages([
        ("system", "Assign courier and logistics instructions. Output valid JSON."),
        ("human", "Assign logistics for '{alimento}' to '{instituicao_nome}'. Schema:\n{format_instructions}")
    ]).partial(format_instructions=parser.get_format_instructions())

    chain = prompt | llm | parser
    return chain.invoke({"alimento": alimento, "instituicao_nome": instituicao_nome})

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

col_left, col_right = st.columns([1, 2])

with col_left:
    st.subheader("📥 Novo Excedente Alimentar")
    food_input = st.text_input("Alimento Doados", value="Maçã")
    target_input = st.selectbox("Público-Alvo", ["crianças em idade escolar", "sem-abrigo", "idosos"])
    
    btn_executar = st.button("🚀 Executar Agentes IA", use_container_width=True)

if btn_executar:
    with col_left:
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
                logistica = atribuir_logistica(food_input, recetor.institution_name)
                st.write(f"**Estafeta:** {logistica.courier_name} ({logistica.vehicle_type})")
                st.write(f"**Tempo Estimado:** {logistica.estimated_time}")
                st.caption(f"**Instruções:** {logistica.instructions}")
                
                # Guardar no estado para renderização no mapa
                st.session_state["resultado"] = {
                    "triagem": triagem,
                    "recetor": recetor,
                    "logistica": logistica
                }

# RENDERIZAÇÃO DO MAPA
with col_right:
    st.subheader("🗺️ Visualização da Rota em Tempo Real")
    
    if "resultado" in st.session_state:
        res = st.session_state["resultado"]
        
        # Local do doador (usar primeiro doador ou fallback no Porto)
        doador = doadores_data[0] if doadores_data else {"lat": 41.1487, "lon": -8.6061, "nome": "Doador Local"}
        
        # Local da instituição receptora
        inst_coords = {"lat": 41.1505, "lon": -8.6320, "nome": res["recetor"].institution_name}
        for inst in instituicoes_porto_data:
            if inst.get("id") == res["recetor"].institution_id or inst.get("nome") == res["recetor"].institution_name:
                inst_coords = inst
                break
        
        # Rota real OSRM
        rota = obter_rota_osrm(doador["lat"], doador["lon"], inst_coords["lat"], inst_coords["lon"])
        
        # Construção do Mapa Folium
        m = folium.Map(location=[doador["lat"], doador["lon"]], zoom_start=14)
        
        folium.Marker(
            [doador["lat"], doador["lon"]], 
            tooltip=f"Doador: {doador['nome']}", 
            icon=folium.Icon(color="green", icon="store", prefix="fa")
        ).add_to(m)
        
        folium.Marker(
            [inst_coords["lat"], inst_coords["lon"]], 
            tooltip=f"IPSS: {inst_coords['nome']}", 
            icon=folium.Icon(color="blue", icon="heart", prefix="fa")
        ).add_to(m)
        
        folium.PolyLine(rota, color="#e74c3c", weight=5, opacity=0.8).add_to(m)

        # Animação do Estafeta via JS Nativo
        rota_json = json.dumps(rota)
        courier_name = res["logistica"].courier_name
        vehicle_type = res["logistica"].vehicle_type

        js_code = f"""
        <script>
        document.addEventListener("DOMContentLoaded", function() {{
            setTimeout(function() {{
                var mapElement = document.querySelector('.folium-map');
                if (!mapElement) return;
                var map = window[mapElement.id];
                var rota = {rota_json};
                var courierName = "{courier_name}";
                var vehicleType = "{vehicle_type}";
                
                var iconClass = "fa-motorcycle"; // Default icon
                if (vehicleType === "Mota") {{
                    iconClass = "fa-motorcycle";
                }} else if (vehicleType === "Carrinha") {{
                    iconClass = "fa-truck";
                }} else if (vehicleType === "Bicicleta") {{ // Assuming 'Bicicleta' is a possible output
                    iconClass = "fa-bicycle";
                }}
                
                var icon = L.divIcon({{
                    className: 'courier-marker',
                    html: "<div style='background-color:#e74c3c; color:white; padding:6px 12px; border-radius:20px; font-weight:bold; font-size:12px; white-space:nowrap; box-shadow:0 2px 6px rgba(0,0,0,0.4); border: 2px solid white;'><i class='fa " + iconClass + "'></i> " + courierName + "</div>",
                    iconSize: [120, 36],
                    iconAnchor: [60, 18]
                }});
                
                var marker = L.marker(rota[0], {{icon: icon}}).addTo(map);
                var i = 0;
                function move() {{
                    if (i < rota.length) {{
                        marker.setLatLng(rota[i]);
                        i++;
                        setTimeout(move, 120);
                    }}
                }}
                move();
            }}, 800);
        }});
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_code))
        
        # Renderização HTML limpa e estável no Streamlit
        html(m._repr_html_(), height=600)
    else:
        st.info("Clica em 'Executar Agentes IA' para correr as tuas funções Gemini e gerar o mapa.")