"""
Extrai dados da Composição da Carteira de fundos
do site CVM FundosReg e salva em Excel separado por fundo.

Variáveis de ambiente opcionais:
  INPUT_COMPETENCIA  - competência no formato MM/AAAA (ex: "02/2026"). Vazio = mais recente.
  INPUT_CNPJS        - CNPJs separados por vírgula (apenas dígitos). Vazio = todos.
"""

import os
import time
import sys
import pandas as pd
from io import StringIO
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select


FUNDOS = [
    {
        "cnpj": "08.915.927/0001-63",
        "pk_partic": "289707",
        "output_file": "patrimonio_liquido_cvm_08915927.xlsx",
    },
    {
        "cnpj": "06.175.696/0001-73",
        "pk_partic": "280545",
        "output_file": "patrimonio_liquido_cvm_06175696.xlsx",
    },
]


def get_fundos_filtrados():
    """Retorna lista de fundos filtrada por INPUT_CNPJS (se definido)."""
    cnpjs_input = os.environ.get("INPUT_CNPJS", "").strip()
    if not cnpjs_input:
        return FUNDOS

    # Normalizar: apenas dígitos para comparação
    cnpjs_solicitados = set()
    for c in cnpjs_input.split(","):
        digits = "".join(ch for ch in c.strip() if ch.isdigit())
        if digits:
            cnpjs_solicitados.add(digits)

    filtrados = []
    for fundo in FUNDOS:
        fundo_digits = "".join(ch for ch in fundo["cnpj"] if ch.isdigit())
        if fundo_digits in cnpjs_solicitados:
            filtrados.append(fundo)

    if not filtrados:
        print(f"AVISO: Nenhum fundo encontrado para CNPJs: {cnpjs_input}")
        print(f"CNPJs disponíveis: {[f['cnpj'] for f in FUNDOS]}")
        sys.exit(1)

    return filtrados


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(120)
    return driver


def extract_table(driver):
    """Extrai a tabela de aplicações (dlAplics ou dlAplicsConf)."""
    # Tentar tabela normal primeiro, depois confidencial
    for table_id in ["dlAplics", "dlAplicsConf"]:
        elements = driver.find_elements(By.ID, table_id)
        if elements:
            return elements[0], table_id
    return None, None


def parse_table(df, table_id):
    """Ajusta headers e filtra colunas da tabela extraída."""
    if len(df) > 3:
        row2 = df.iloc[2].tolist()
        row3 = df.iloc[3].tolist()
        headers = []
        for r2, r3 in zip(row2, row3):
            r2_str = str(r2).strip() if pd.notna(r2) else ""
            r3_str = str(r3).strip() if pd.notna(r3) else ""
            if r3_str and r3_str != r2_str:
                headers.append(f"{r2_str} - {r3_str}" if r2_str else r3_str)
            else:
                headers.append(r2_str)
        df = df.iloc[4:]
        df.columns = headers
    else:
        row1 = df.iloc[1].tolist()
        df = df.iloc[2:]
        df.columns = [str(c).strip() for c in row1]

    df = df.reset_index(drop=True)
    df = df.dropna(how="all")

    # Encontrar coluna de Ativo e Valores - Mercado
    ativo_col = None
    mercado_col = None
    for col in df.columns:
        col_lower = col.lower()
        if "ativo" in col_lower:
            ativo_col = col
        if "mercado" in col_lower:
            mercado_col = col

    if not ativo_col:
        ativo_col = df.columns[0]
    if not mercado_col:
        # Pegar a penúltima coluna numérica (geralmente Mercado)
        for col in reversed(df.columns.tolist()):
            vals = df[col].astype(str).str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            try:
                vals.astype(float)
                mercado_col = col
                break
            except (ValueError, TypeError):
                continue

    if not mercado_col:
        mercado_col = df.columns[-2]

    df = df[[ativo_col, mercado_col]]
    df.columns = ["Ativo", "Valores - Mercado"]

    # Converter formato BR (1.234,56) para float
    df["Valores - Mercado"] = (
        df["Valores - Mercado"]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    return df


def scrape_fundo(driver, fundo):
    cnpj = fundo["cnpj"]
    pk_partic = fundo["pk_partic"]
    output_file = fundo["output_file"]

    print(f"\n--- Processando CNPJ: {cnpj} ---")

    url = f"https://cvmweb.cvm.gov.br/SWB/Sistemas/SCW/CPublica/CDA/CPublicaCDA.aspx?PK_PARTIC={pk_partic}&SemFrame="
    print(f"Acessando {url} ...")
    for tentativa in range(3):
        try:
            driver.get(url)
            break
        except Exception as e:
            print(f"Tentativa {tentativa + 1}/3 falhou: {e}")
            if tentativa == 2:
                raise
            time.sleep(5)
    time.sleep(3)

    sel = Select(driver.find_element(By.ID, "ddCOMPTC"))

    competencia_input = os.environ.get("INPUT_COMPETENCIA", "").strip()
    if competencia_input:
        opcoes = [o.text.strip() for o in sel.options]
        if competencia_input in opcoes:
            sel.select_by_visible_text(competencia_input)
            time.sleep(3)
            sel = Select(driver.find_element(By.ID, "ddCOMPTC"))
        else:
            print(f"AVISO: Competência '{competencia_input}' não encontrada. Opções: {opcoes}")
            print("Usando competência padrão (mais recente).")

    competencia = sel.first_selected_option.text
    print(f"Competência: {competencia}")

    pl_value = driver.find_element(By.ID, "lbPatrimLiq").text
    pl_date = driver.find_element(By.ID, "lbDtRegDoc").text

    rows = driver.find_elements(By.CSS_SELECTOR, "#tabAtivos tr")
    fund_name = rows[1].text if len(rows) > 1 else "N/A"

    print(f"Fundo: {fund_name}")
    print(f"CNPJ: {cnpj}")
    print(f"Patrimônio Líquido: {pl_value}")
    print(f"Data Recebimento: {pl_date}")
    print()

    # Extrair tabela (normal ou confidencial)
    table_el, table_id = extract_table(driver)
    if not table_el:
        print(f"ERRO: Nenhuma tabela encontrada para {cnpj}.")
        return

    print(f"Tabela encontrada: {table_id}")
    table_html = table_el.get_attribute("outerHTML")
    tables = pd.read_html(StringIO(table_html))

    if not tables:
        print(f"ERRO: Não foi possível parsear tabela para {cnpj}.")
        return

    df = parse_table(tables[0], table_id)

    print(f"Tabela extraída: {df.shape[0]} linhas x {df.shape[1]} colunas")
    print(df.to_string(index=False))
    print()

    # Salvar em Excel
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        resumo = pd.DataFrame({
            "Campo": ["Fundo", "CNPJ", "Competência", "Patrimônio Líquido", "Data Recebimento"],
            "Valor": [fund_name, cnpj, competencia, pl_value, pl_date],
        })
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        df.to_excel(writer, sheet_name="Composicao_Carteira", index=False)

        # Aba Share
        df_share = df.copy()
        df_share["Ativo"] = (
            df_share["Ativo"]
            .str.split(r"(?:Cod\.|Descrição:)", regex=True)
            .str[0]
            .str.strip()
        )
        df_share = df_share.groupby("Ativo", as_index=False)["Valores - Mercado"].sum()
        total = df_share["Valores - Mercado"].sum()
        df_share["Share"] = df_share["Valores - Mercado"] / total
        df_share = df_share.sort_values("Valores - Mercado", ascending=False).reset_index(drop=True)

        print("Share:")
        print(df_share.to_string(index=False))
        print()

        df_share.to_excel(writer, sheet_name="Share", index=False)

    print(f"Arquivo salvo: {output_file}")


def main():
    print("CVM FundosReg - Extrator de Composição da Carteira")

    fundos = get_fundos_filtrados()
    print(f"Fundos a processar: {[f['cnpj'] for f in fundos]}")

    comp = os.environ.get("INPUT_COMPETENCIA", "").strip()
    if comp:
        print(f"Competência solicitada: {comp}")

    driver = create_driver()

    try:
        for fundo in fundos:
            scrape_fundo(driver, fundo)
        print("\nSucesso! Todos os fundos processados.")
    except Exception as e:
        print(f"\nERRO: {e}")
        driver.save_screenshot("cvm_error.png")
        print("Screenshot salvo: cvm_error.png")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
