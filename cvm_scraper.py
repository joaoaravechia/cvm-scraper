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
        "cnpj_busca": "08915927000163",
        "output_file": "patrimonio_liquido_cvm_08915927.xlsx",
    },
    {
        "cnpj": "06.175.696/0001-73",
        "cnpj_busca": "06175696000173",
        "output_file": "patrimonio_liquido_cvm_06175696.xlsx",
    },
]

BUSCA_URL = "https://cvmweb.cvm.gov.br/SWB/Sistemas/SCW/CPublica/FormBuscaPartic.aspx?TpConsult=6"


def create_driver():
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(60)
    return driver


def buscar_fundo_cda(driver, cnpj_busca):
    """Busca o fundo pelo CNPJ e navega até a página CDA (Composição da Carteira)."""
    print(f"Buscando fundo {cnpj_busca} ...")
    driver.get(BUSCA_URL)
    time.sleep(2)

    # Preencher CNPJ e clicar em Continuar
    campo = driver.find_element(By.ID, "txtCNPJNome")
    campo.clear()
    campo.send_keys(cnpj_busca)
    driver.find_element(By.ID, "btnContinuar").click()
    time.sleep(3)

    # Na página de resultados, clicar no link do fundo (contém PK_PARTIC)
    links = driver.find_elements(By.CSS_SELECTOR, "a[href*='PK_PARTIC']")
    if not links:
        # Pode ser que os resultados estejam dentro de um frame
        frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
        for frame in frames:
            try:
                driver.switch_to.frame(frame)
                links = driver.find_elements(By.CSS_SELECTOR, "a[href*='PK_PARTIC']")
                if links:
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

    if not links:
        # Tentar pegar todos os links para debug
        all_links = driver.find_elements(By.TAG_NAME, "a")
        print(f"Links encontrados: {len(all_links)}")
        for link in all_links[:10]:
            print(f"  {link.get_attribute('href')} - {link.text}")
        raise Exception(f"Nenhum link com PK_PARTIC encontrado para {cnpj_busca}")

    # Clicar no primeiro resultado
    links[0].click()
    time.sleep(3)

    # Agora estamos na página do fundo. Procurar link para CDA (Composição da Carteira)
    driver.switch_to.default_content()

    # A página do fundo pode usar frames
    frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
    for frame in frames:
        try:
            driver.switch_to.frame(frame)
            cda_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Composi")
            if cda_links:
                cda_links[0].click()
                time.sleep(3)
                return
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()

    # Tentar sem frames
    cda_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Composi")
    if cda_links:
        cda_links[0].click()
        time.sleep(3)
        return

    # Se não encontrou "Composição", pode já estar na página CDA
    if driver.find_elements(By.ID, "ddCOMPTC"):
        return

    raise Exception(f"Não foi possível navegar até CDA para {cnpj_busca}")


def scrape_fundo(driver, fundo):
    cnpj = fundo["cnpj"]
    cnpj_busca = fundo["cnpj_busca"]
    output_file = fundo["output_file"]

    print(f"\n--- Processando CNPJ: {cnpj} ---")

    buscar_fundo_cda(driver, cnpj_busca)

    # Garantir que estamos no conteúdo correto (pode estar em frame)
    if not driver.find_elements(By.ID, "ddCOMPTC"):
        driver.switch_to.default_content()
        frames = driver.find_elements(By.TAG_NAME, "frame") + driver.find_elements(By.TAG_NAME, "iframe")
        for frame in frames:
            try:
                driver.switch_to.frame(frame)
                if driver.find_elements(By.ID, "ddCOMPTC"):
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

    sel = Select(driver.find_element(By.ID, "ddCOMPTC"))
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

    # Extrair tabela de aplicações
    aplics_table = driver.find_element(By.ID, "dlAplics")
    aplics_html = aplics_table.get_attribute("outerHTML")
    tables = pd.read_html(StringIO(aplics_html))

    if not tables:
        print(f"ERRO: Nenhuma tabela encontrada para {cnpj}.")
        return

    df = tables[0]

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
    df = df[["Ativo", "Valores - Mercado"]]

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

    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        resumo = pd.DataFrame({
            "Campo": ["Fundo", "CNPJ", "Competência", "Patrimônio Líquido", "Data Recebimento"],
            "Valor": [fund_name, cnpj, competencia, pl_value, pl_date],
        })
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        df.to_excel(writer, sheet_name="Composicao_Carteira", index=False)

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

    # Voltar ao default content para o próximo fundo
    driver.switch_to.default_content()


def main():
    print("CVM FundosReg - Extrator de Composição da Carteira")

    driver = create_driver()

    try:
        for fundo in FUNDOS:
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
