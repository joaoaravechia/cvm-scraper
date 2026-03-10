"""
Extrai dados da Composição da Carteira de fundos
do site CVM FundosReg e salva em Excel separado por fundo.
"""

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
        "pk_partic": "214731",
        "output_file": "patrimonio_liquido_cvm_06175696.xlsx",
    },
]


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    return driver


def scrape_fundo(driver, fundo):
    cnpj = fundo["cnpj"]
    pk_partic = fundo["pk_partic"]
    output_file = fundo["output_file"]

    print(f"--- Processando CNPJ: {cnpj} ---")

    # 1. Acessar página de Composição da Carteira diretamente
    url = f"https://cvmweb.cvm.gov.br/SWB/Sistemas/SCW/CPublica/CDA/CPublicaCDA.aspx?PK_PARTIC={pk_partic}&SemFrame="
    print(f"Acessando {url} ...")
    driver.get(url)
    time.sleep(3)

    # 2. Verificar competência selecionada (já vem a mais recente por padrão)
    sel = Select(driver.find_element(By.ID, "ddCOMPTC"))
    competencia = sel.first_selected_option.text
    print(f"Competência: {competencia}")

    # 3. Extrair Patrimônio Líquido, Data, e info do fundo
    pl_value = driver.find_element(By.ID, "lbPatrimLiq").text
    pl_date = driver.find_element(By.ID, "lbDtRegDoc").text

    rows = driver.find_elements(By.CSS_SELECTOR, "#tabAtivos tr")
    fund_name = rows[1].text if len(rows) > 1 else "N/A"

    print(f"Fundo: {fund_name}")
    print(f"CNPJ: {cnpj}")
    print(f"Patrimônio Líquido: {pl_value}")
    print(f"Data Recebimento: {pl_date}")
    print()

    # 4. Extrair tabela de aplicações (dlAplics)
    aplics_table = driver.find_element(By.ID, "dlAplics")
    aplics_html = aplics_table.get_attribute("outerHTML")
    tables = pd.read_html(StringIO(aplics_html))

    if not tables:
        print(f"ERRO: Nenhuma tabela encontrada para {cnpj}.")
        return

    df = tables[0]

    # Ajustar headers: as primeiras linhas contêm headers multi-nível
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

    # Filtrar apenas colunas Ativo e Valores - Mercado
    df = df[["Ativo", "Valores - Mercado"]]

    # Converter formato BR (1.234,56) para float
    df["Valores - Mercado"] = (
        df["Valores - Mercado"]
        .astype(str)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
        .astype(float)
    )

    print(f"Tabela extraída: {df.shape[0]} linhas x {df.shape[1]} colunas")
    print(df.to_string(index=False))
    print()

    # 5. Salvar em Excel
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
    print()


def main():
    print("CVM FundosReg - Extrator de Composição da Carteira")
    print()

    driver = create_driver()

    try:
        for fundo in FUNDOS:
            scrape_fundo(driver, fundo)
        print("Sucesso! Todos os fundos processados.")
    except Exception as e:
        print(f"\nERRO: {e}")
        driver.save_screenshot("cvm_error.png")
        print("Screenshot salvo: cvm_error.png")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
