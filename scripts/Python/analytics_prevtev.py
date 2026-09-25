"""Página Streamlit de analytics da PREVTEV.

Executa scripts/Python/export.py para atualizar o export/export.json a partir
do Firestore e exibe as mesmas análises construídas em analytics.ipynb.
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
EXPORT_SCRIPT = PROJECT_ROOT / "scripts" / "Python" / "export.py"
EXPORT_JSON = PROJECT_ROOT / "export" / "export.json"

COLORS = ["#EC0E73", "#041266", "#C830A0", "#FAAFB1"]

st.set_page_config(page_title="Analytics PREVTEV", layout="wide")


# ── Execução do export ────────────────────────────────────────────────────────
def run_export() -> tuple[bool, str]:
    """Roda scripts/Python/export.py e retorna (sucesso, saida/erro)."""
    try:
        result = subprocess.run(
            [sys.executable, str(EXPORT_SCRIPT)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            return False, result.stderr or result.stdout
        return True, result.stdout
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


# ── Carga e preparação dos dados ──────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def load_raw_data(json_path: str, mtime: float) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_prevtev_json(file_path: Path) -> Optional[pd.DataFrame]:
    """Lê o export.json da PREVTEV e retorna um DataFrame unificado normalizado."""
    if not file_path.exists():
        logger.error("Arquivo não encontrado: %s", file_path)
        return None

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    users_data = data.get("usuarios", {})
    if not users_data:
        logger.warning("Nenhum registro de usuário encontrado no JSON.")
        return pd.DataFrame()

    processed_rows = []
    for user_id, user_info in users_data.items():
        row = {
            "user_id": user_id,
            "nomeCompleto": user_info.get("nomeCompleto"),
            "email": user_info.get("email"),
            "profissionalSaude": user_info.get("profissionalSaude"),
            "crmCpf": user_info.get("crmCpf"),
            "isAceitoLGPD": user_info.get("isAceitoLGPD"),
            "nomeCalculadora": user_info.get("nomeCalculadora"),
            "preenchimento_dt": (
                pd.to_datetime(user_info.get("createdAt"), format="ISO8601", errors="coerce").strftime("%Y-%m-%d")
                if user_info.get("createdAt")
                else None
            ),
            "resultado": user_info.get("resultado"),
        }

        for q in user_info.get("questions", []):
            q_title = q.get("question")
            if not q_title:
                continue
            if "selectedOption" in q:
                row[q_title] = q.get("selectedOption")
            elif "selectedValue" in q:
                row[q_title] = q.get("selectedValue")
            elif "subQuestions" in q:
                selected = [sub.get("text") for sub in q.get("subQuestions", []) if sub.get("selected") == "Sim"]
                row[q_title] = ", ".join(selected) if selected else "Nenhum"

        processed_rows.append(row)

    df = pd.DataFrame(processed_rows)
    logger.info("Sucesso: %d registros processados e normalizados", len(df))
    return df


def build_df_usuarios(data: dict) -> pd.DataFrame:
    df = pd.DataFrame.from_dict(data["usuarios"], orient="index").reset_index()
    df = df.rename(columns={"index": "user_id"})
    df = df.dropna(subset=["createdAt"])
    df = df[df["questions"].apply(str) != "[]"]
    df["preenchimento_dt"] = pd.to_datetime(df["createdAt"], format="ISO8601", errors="coerce")
    df["preenchimento_dt"] = df["preenchimento_dt"].dt.strftime("%Y-%m-%d")
    df = df.astype({"preenchimento_dt": "datetime64[ns]"})
    df = df[df["preenchimento_dt"] >= datetime.strptime("2025-07-01T01:26:36.610Z", "%Y-%m-%dT%H:%M:%S.%fZ")]
    return df


def build_resultado(df_usuarios: pd.DataFrame) -> pd.DataFrame:
    df_aux = df_usuarios[["user_id", "questions", "nomeCalculadora", "preenchimento_dt", "resultado"]].explode(
        "questions"
    )
    df_pergunta_resp = pd.json_normalize(df_aux["questions"])
    df_pergunta_resp["user_id"] = df_aux["user_id"].values
    df_pergunta_resp["nomeCalculadora"] = df_aux["nomeCalculadora"].values
    df_pergunta_resp["preenchimento_dt"] = df_aux["preenchimento_dt"].values
    df_pergunta_resp["Answer"] = df_pergunta_resp["selectedOption"].combine_first(df_pergunta_resp["selectedValue"])
    df_pergunta_resp["resultado"] = df_aux["resultado"].values

    resultado = df_pergunta_resp[
        ["user_id", "nomeCalculadora", "preenchimento_dt", "question", "Answer", "resultado"]
    ].copy()
    resultado = resultado[
        ~resultado["question"].isin(
            ["Fatores de risco pré-existentes", "Fatores de risco obstétricos", "Fatores de risco transitórios"]
        )
    ]
    resultado["question"] = resultado["question"].str.strip()
    resultado = resultado.dropna(subset=["nomeCalculadora"])
    resultado["mes_ano"] = resultado["preenchimento_dt"].dt.to_period("M").astype(str)
    return resultado


# ── Seções da página ──────────────────────────────────────────────────────────
def secao_lista_medicos(df_usuarios: pd.DataFrame) -> None:
    st.header("1. Lista de Médicos")

    df_lista_medicos = df_usuarios[
        ["user_id", "nomeCompleto", "email", "profissionalSaude", "crmCpf", "nomeCalculadora", "preenchimento_dt"]
    ].copy()
    df_lista_medicos = df_lista_medicos[df_lista_medicos["profissionalSaude"] == True]  # noqa: E712
    df_lista_medicos = df_lista_medicos[df_lista_medicos["email"].notnull()]
    df_lista_medicos = df_lista_medicos[df_lista_medicos["email"] != "NI"]
    df_lista_medicos = df_lista_medicos.drop_duplicates(subset="crmCpf", keep="first")

    st.dataframe(df_lista_medicos, width='stretch')

    buffer = BytesIO()
    df_lista_medicos.to_excel(buffer, index=False)
    st.download_button(
        "Baixar lista de médicos (.xlsx)",
        data=buffer.getvalue(),
        file_name=f"lista_medicos_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


def secao_dataset_calculadoras(export_json_path: Path) -> None:
    st.header("2. Dataset de uso e de respostas")

    df_all = parse_prevtev_json(export_json_path)
    if df_all is None or df_all.empty:
        st.warning("Nenhum dado disponível para montar o dataset de calculadoras.")
        return

    nomes = ["SCORE Caprini", "Padua", "Improve", "ImproveDD", "RCOG"]
    resumo = []
    for nome in nomes:
        df_calc = df_all[df_all["nomeCalculadora"] == nome].dropna(axis=1, how="all")
        resumo.append({"Calculadora": nome, "Registros": len(df_calc), "Colunas": df_calc.shape[1]})

    st.dataframe(pd.DataFrame(resumo), width='stretch', hide_index=True)


def secao_perfil_etario(caprini: pd.DataFrame) -> None:
    st.subheader("a. Perfil etário dos pacientes")

    caprini_idade = caprini[caprini["question"] == "Idade (Anos)"].copy()
    caprini_idade["Answer"] = caprini_idade["Answer"].astype(str)

    idade_counts = caprini_idade["Answer"].value_counts().sort_index()
    fig = px.bar(
        x=idade_counts.index,
        y=idade_counts.values,
        color=idade_counts.index,
        color_discrete_sequence=COLORS,
    )
    fig.update_layout(
        title="Perfil etário dos pacientes avaliados com o Escore Caprini",
        xaxis_title="Idade (Anos)",
        yaxis_title="Pacientes (n)",
        xaxis_tickangle=-45,
        bargap=0.0,
        showlegend=True,
        legend_title_text="Idade (Anos)",
    )
    fig.update_traces(texttemplate="%{y}", textposition="outside")
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width='stretch')

    st.markdown("###### I. Perfil etário dos pacientes ao longo do tempo")
    preenchimentos_idade_tempo = (
        caprini_idade[["user_id", "mes_ano", "Answer"]].groupby(["mes_ano", "Answer"]).size().reset_index(name="Frequência")
    )
    fig = px.line(
        preenchimentos_idade_tempo,
        x="mes_ano",
        y="Frequência",
        color="Answer",
        markers=True,
        color_discrete_sequence=COLORS,
    )
    fig.update_layout(
        title="Evolução do número de preenchimentos do Escore Caprini por faixa etária",
        xaxis_title="Período",
        yaxis_title="Pacientes (n)",
        xaxis_tickangle=-45,
        legend_title_text="Idade (Anos)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width='stretch')

    st.markdown("###### Perfil etário dos pacientes por resultado do score")
    caprini_resultado_idade_perfil = (
        caprini_idade.groupby(["Answer", "resultado"]).size().reset_index(name="Frequência")
    )

    fig = px.bar(
        caprini_resultado_idade_perfil,
        x="resultado",
        y="Frequência",
        color="Answer",
        color_discrete_sequence=COLORS,
        barmode="stack",
    )
    fig.update_layout(
        title="Distribuição dos resultados do Escore Caprini por faixa etária",
        xaxis_title="Resultado",
        yaxis_title="Pacientes (n)",
        xaxis_tickangle=-45,
        legend_title_text="Idade (Anos)",
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width='stretch')

    st.markdown("###### Perfil de cada faixa etária ao longo do tempo")
    frequencia_40menos = caprini_idade.groupby(["resultado", "mes_ano"]).size().reset_index(name="Frequência")
    fig = px.bar(
        frequencia_40menos,
        x="mes_ano",
        y="Frequência",
        color="resultado",
        color_discrete_sequence=px.colors.sequential.Viridis,
        barmode="stack",
    )
    st.plotly_chart(fig, width='stretch')


def secao_perfil_genero(caprini: pd.DataFrame) -> None:
    st.subheader("b. Perfil de Gênero dos pacientes")

    caprini_sexo = caprini[caprini["question"] == "Sexo"].copy()
    caprini_sexo["Answer"] = caprini_sexo["Answer"].astype(str)
    frequencia_sexo = caprini_sexo["Answer"].value_counts().reset_index()
    frequencia_sexo.columns = ["Sexo", "Frequência"]

    fig = px.pie(
        frequencia_sexo,
        names="Sexo",
        values="Frequência",
        color="Sexo",
        color_discrete_sequence=COLORS,
    )
    fig.update_layout(title="Perfil de gênero dos pacientes avaliados com o Escore Caprini")
    st.plotly_chart(fig, width='stretch')


def secao_tipo_cirurgia(caprini: pd.DataFrame) -> None:
    st.subheader("c. Tipo de cirurgia")

    caprini_tipo_cirurgia = caprini[caprini["question"] == "Tipo de cirurgia"].copy()
    caprini_tipo_cirurgia["Answer"] = caprini_tipo_cirurgia["Answer"].astype(str)
    frequencia_tipo_cirurgia = caprini_tipo_cirurgia["Answer"].value_counts().reset_index()
    frequencia_tipo_cirurgia.columns = ["Tipo de Cirurgia", "Frequência"]

    col1, col2 = st.columns(2)
    with col1:
        fig = px.bar(
            frequencia_tipo_cirurgia,
            x="Tipo de Cirurgia",
            y="Frequência",
            color="Tipo de Cirurgia",
            color_discrete_sequence=COLORS,
        )
        fig.update_layout(
            title="Frequência de pacientes por tipo de cirurgia",
            xaxis_title="Tipo de Cirurgia",
            yaxis_title="Pacientes (n)",
        )
        fig.update_traces(texttemplate="%{y}", textposition="outside")
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, width='stretch')

    with col2:
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=frequencia_tipo_cirurgia["Tipo de Cirurgia"],
                    values=frequencia_tipo_cirurgia["Frequência"],
                    hole=0.5,
                    marker_colors=COLORS,
                )
            ]
        )
        fig.update_layout(title="Distribuição do tipo de cirurgia")
        st.plotly_chart(fig, width='stretch')


def secao_mobilidade(caprini: pd.DataFrame) -> None:
    st.subheader("d. Mobilidade")

    caprini_mobilidade = caprini[caprini["question"] == "Mobilidade"].copy()
    caprini_mobilidade["Answer"] = caprini_mobilidade["Answer"].astype(str)
    frequencia_mobilidade = caprini_mobilidade["Answer"].value_counts().reset_index()
    frequencia_mobilidade.columns = ["Mobilidade", "Frequência"]

    fig = go.Figure(
        data=[
            go.Pie(
                labels=frequencia_mobilidade["Mobilidade"],
                values=frequencia_mobilidade["Frequência"],
                hole=0.5,
                marker_colors=COLORS,
            )
        ]
    )
    fig.update_layout(title="Avaliação de mobilidade dos pacientes avaliados com o Escore Caprini")
    st.plotly_chart(fig, width='stretch')


def secao_escore_caprini(resultado: pd.DataFrame) -> None:
    st.header("3. Escore de Caprini")

    caprini = resultado[resultado["nomeCalculadora"] == "SCORE Caprini"].copy()
    if caprini.empty:
        st.warning("Nenhum registro do Escore Caprini encontrado no período selecionado.")
        return

    caprini_serie_temporal_frequencia = (
        caprini[["user_id", "mes_ano"]].drop_duplicates().groupby("mes_ano").size().reset_index(name="Frequência")
    )
    fig = px.line(caprini_serie_temporal_frequencia, x="mes_ano", y="Frequência")
    fig.update_layout(
        title="Utilização do Escore Caprini ao longo do tempo",
        xaxis_title="Período",
        yaxis_title="Frequência",
    )
    fig.update_traces(line=dict(color="#EC0E73", width=3), marker=dict(color="#041266", size=8))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=False)
    st.plotly_chart(fig, width='stretch')

    secao_perfil_etario(caprini)
    secao_perfil_genero(caprini)
    secao_tipo_cirurgia(caprini)
    secao_mobilidade(caprini)


# ── Página principal ───────────────────────────────────────────────────────
def main() -> None:
    st.title("Analytics PREVTEV")

    with st.sidebar:
        st.header("Dados")
        if st.button("Atualizar dados (Firestore)", width='stretch'):
            with st.spinner("Executando export.py..."):
                sucesso, saida = run_export()
            if sucesso:
                st.success("Export concluído com sucesso.")
                load_raw_data.clear()
            else:
                st.error(f"Falha ao executar export.py:\n{saida}")

        if EXPORT_JSON.exists():
            mtime = datetime.fromtimestamp(EXPORT_JSON.stat().st_mtime)
            st.caption(f"Última atualização do JSON: {mtime.strftime('%d/%m/%Y %H:%M:%S')}")

    if not EXPORT_JSON.exists():
        st.error(f"Arquivo não encontrado: {EXPORT_JSON}. Clique em 'Atualizar dados' para gerá-lo.")
        return

    data = load_raw_data(str(EXPORT_JSON), EXPORT_JSON.stat().st_mtime)
    df_usuarios = build_df_usuarios(data)
    resultado = build_resultado(df_usuarios)

    secao_lista_medicos(df_usuarios)
    secao_dataset_calculadoras(EXPORT_JSON)
    secao_escore_caprini(resultado)


if __name__ == "__main__":
    main()
