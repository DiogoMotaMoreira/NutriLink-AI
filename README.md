# 🥗 NutriLink-AI

**NutriLink-AI** is an experimental multi-agent system built to evaluate autonomous AI agent orchestration in real-world food rescue logistics. 

The project automates the sequential pipeline of surplus food triage, allergen filtering, beneficiary institution matching, and dynamic courier routing across the city of Porto.

## 📺 Demonstration

![NutriLink-AI Demo](demo.webm)

> ⚠️ **Disclaimer:** This project was developed purely as a proof of concept and practice run for the **HackerRank Orchestrate Hackathon** (August 1st, 2026). To accelerate development, UI components, addresses, and geographic coordinates were AI-generated and may not reflect accurate real-world locations.

---

## 🚀 Key Features

* **Automated Food Triage:** Analyzes food items against target audiences to approve/reject suitability, detect allergens, and flag handling requirements.
* **Smart Beneficiary Matching:** Filters local IPSS/institutions based on dietary restrictions and matches food donations to the most appropriate receiver.
* **Logistics & Fleet Dispatching:** Dynamically assigns available couriers based on vehicle type and cargo capacity.
* **Real-Time Interactive Map:** Renders live, smooth vehicle movement along real road networks (via OSRM) using Streamlit and Folium.
* **Multi-Delivery Support:** Manages multiple concurrent active orders and courier routes simultaneously.

---

## 🛠️ Tech Stack

* **Language:** Python 3.12+
* **AI & Multi-Agent Framework:** Google Gemini API (`gemini-3.5-flash-lite` / `gemini-2.5-flash`), LangChain
* **Structured Data Validation:** Pydantic
* **Dashboard UI & Mapping:** Streamlit, Folium (Leaflet.js)
* **Routing Engine:** OSRM (Open Source Routing Machine API)

---

## 🤖 Multi-Agent Workflow

```
[ Surplus Food Input ]
          │
          ▼
┌───────────────────┐
│  Agente 1:        │ ──(Rejeitado)──► [ Processo Terminado ]
│  Triagem          │
└─────────┬─────────┘
          │ (Aprovado)
          ▼
┌───────────────────┐
│  Agente 2:        │ ──► [ Filtra Alérgenos e Seleciona IPSS ]
│  Matching IPSS    │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  Agente 3:        │ ──► [ Seleciona Estafeta & Calcula Rota OSRM ]
│  Logística        │
└─────────┬─────────┘
          │
          ▼
[ Mapa Interativo em Tempo Real ]
```

---

## 📦 Installation & Setup

### 1. Clone the repository
```bash
git clone https://github.com/DiogoMotaMoreira/NutriLink-AI.git
cd NutriLink-AI
```

### 2. Create and activate a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Create a `.env` file in the root directory and add your Google Gemini API Key:
```env
GOOGLE_API_KEY=your_gemini_api_key_here
# or GEMINI_API_KEY=your_gemini_api_key_here
```

### 5. Run the Application
```bash
streamlit run app.py
```

---

## 🔮 Future Improvements
Since this is an experimental prototype, there is plenty of room for enhancement:
* Adding comprehensive nutritional and temperature-control metadata for food items.
* Integrating real-world APIs for live traffic conditions and courier GPS.
* Supporting dynamic multi-stop pickup and delivery route optimization.

---

## 🤝 Contributing
Contributions are welcome! Feel free to open an Issue or submit a Pull Request to help improve agent decision-making, UI features, or routing efficiency.

---

## 📄 License
This project is open-source and available under the MIT License.