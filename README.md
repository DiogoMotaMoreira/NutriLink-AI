# Relatório de Especificação do Projeto: **ZeroWaste-Crew**

---

## 1. Contexto e Enquadramento do Problema

### O Problema do Mundo Real

O desperdício alimentar em estabelecimentos comerciais (supermercados, restaurantes, padarias e produtores) ocorre maioritariamente devido à **falta de tempo e de coordenação logística** na janela crítica antes do fecho do estabelecimento ou do prazo de validade dos produtos.

Atualmente, a doação de excedentes sofre dos seguintes estrangulamentos:

* **Inoperacionalidade manual:** Processos lentos e baseados na intervenção humana para registar, aprovar e agendar entregas.
* **Riscos de segurança alimentar:** Falta de rastreio de alérgenos e de condições de conservação (ex.: cadeia do frio).
* **Fricção logística:** Dificuldade em alocar rapidamente transportes adequados para pequenos volumes num curto espaço de tempo.

### A Visão da Solução

Desenvolver um **Sistema Multiagente Autónomo (Orchestrator-Workers)** que automatize 100% do processo de resgate alimentar. O sistema recebe um alerta de excedente e executa de forma assíncrona, sem intervenção humana, a validação de segurança, a seleção da instituição beneficiária e a atribuição da logística de transporte.

---

## 2. Objetivos Principais

* **Zero Intervenção Humana (100% Automático):** Eliminar a necessidade de aprovação manual (*Human-in-the-loop*) para garantir respostas em minutos.
* **Segurança e Conformidade Alimentar:** Garantir que nenhum produto com risco de alérgenos ou contaminação seja entregue a beneficiários vulneráveis.
* **Otimização de Rotas e Recursos:** Casar o volume do excedente com o tipo de veículo adequado (ex.: mota para volumes pequenos, carro para grandes volumes).
* **Rastreabilidade e Estado Centralizado:** Manter um registo auditável (*Blackboard*) com todas as etapas e decisões tomadas durante a missão.

---

## 3. Requisitos Funcionais

```
[ Input Global do Doador ]
            │
            ▼
┌─────────────────────────┐
│   ORCHESTRATOR (Cérebro)│
└───────────┬─────────────┘
            │
            ├───► 1. Worker de Triagem (Valida Segurança & Alérgenos)
            │      └─► Reprovado? Interrompe a missão.
            │      └─► Aprovado? Avança para o passo 2.
            │
            ├───► 2. Worker Recetor (Casamento Social & IPSS)
            │      └─► Seleciona local e horário de entrega.
            │
            └───► 3. Worker Logístico (Atribuição de Frota)
                   └─► Aloca estafeta/veículo e ativa missão.

```

### RF-01: Receção e Estruturação do Input Global

* O sistema deve aceitar um *payload* contendo:
* **Dados do Alimento:** Nome, tipo, descrição do rótulo e quantidade/volume.
* **Dados Temporais:** Validade e horário de fecho do estabelecimento.
* **Dados de Localização e Acesso:** Morada de recolha, condições de conservação (ex.: refrigerado/temperatura ambiente) e instruções de acesso ao local.



### RF-02: Triagem e Auditoria de Segurança (Worker de Triagem)

* Analisar o produto quanto a prazos de validade e risco de contaminação.
* Identificar e extrair automaticamente a lista de **alérgenos detetados**.
* Definir os **cuidados de transporte** (ex.: necessidade de mala térmica).
* Decidir se o produto é **Aprovado** ou **Rejeitado**.
* *Critério de Paragem:* Se o produto for rejeitado, a missão deve ser interrompida imediatamente, registando o motivo.

### RF-03: Alocação e Correspondência Social (Worker Recetor)

* Cruzar os dados dos produtos aprovados com o perfil de instituições de solidariedade (IPSSs) e famílias vulneráveis.
* Validar que as restrições alimentares da instituição parceira não colidem com os alérgenos identificados no produto.
* Definir o **local de entrega**, a **janela horária** e as instruções de receção.

### RF-04: Gestão e Atribuição Logística (Worker Logístico)

* Determinar o tipo de veículo necessário com base no volume e nos cuidados de transporte.
* Gerar/Atribuir automaticamente os dados do estafeta:
* Nome e contacto.
* Tipo de veículo, modelo e matrícula.
* Instruções adicionais de transporte.


* Alterar o estado da missão para `EM_TRANSITO`.

### RF-05: Gestão de Estado Centralizado (Blackboard)

* O sistema deve manter um objeto partilhado (*Blackboard*) que armazena a evolução dos dados ao longo do pipeline de execução.

---

## 4. Requisitos Não-Funcionais

### RNF-01: Validação de Dados e Tipagem Estrita

* Toda a comunicação entre agentes deve ser validada estruturalmente (ex.: através de esquemas Pydantic/JSON Schema) para evitar falhas em tempo de execução causadas por alucinações de modelos de linguagem.

### RNF-02: Desempenho e Latência

* O ciclo completo de processamento (desde a entrada do input até à atribuição do estafeta) não deve exceder **30 segundos**.

### RNF-03: Desacoplamento de Configurações

* As personas, objetivos e instruções de cada agente, assim como a definição das tarefas, devem estar isoladas em ficheiros de configuração (ex.: YAML/JSON), separando o comportamento do agente da lógica do código Python.

### RNF-04: Robustez e Controlo de Erros

* O Orchestrator deve gerir exceções em caso de respostas inválidas de um Worker, permitindo re-tentativas (retry mechanism) antes de cancelar a missão com estado de erro.

---

## 5. Requisitos de Testes e Validação do Sistema

Para validar a eficácia do sistema em ambiente de simulação, devem ser testados os seguintes cenários:

1. **Cenário de Sucesso (Happy Path):**
* Input com alimentos frescos dentro da validade e sem conflitos graves.
* *Resultado esperado:* Triagem aprovada $\rightarrow$ Recetor atribuído $\rightarrow$ Estafeta alocado $\rightarrow$ Estado: `EM_TRANSITO`.


2. **Cenário de Rejeição por Segurança Alimentar:**
* Input com produto fora da validade ou sem informação mínima de conservação.
* *Resultado esperado:* Triagem rejeitada $\rightarrow$ Motivo registado no Blackboard $\rightarrow$ Processo interrompido sem acionar o Recetor ou Logística.


3. **Cenário de Incompatibilidade de Alérgenos:**
* Input com produto contendo vestígios de amendoim/glúten.
* *Resultado esperado:* O Worker Recetor escolhe obrigatoriamente uma instituição sem restrições ou alertas para esses ingredientes.