import os
from dotenv import load_dotenv
import streamlit as st
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from supabase import create_client
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# Configuração da página Streamlit
st.set_page_config(
    page_title="CMB - Capital",
    page_icon="🏗️",
    layout="wide"
)

# Configurações do SMTP
SMTP_USER = "Controle BLD CMB Capital"
SMTP_PASS = "VxDk0im9xWjDqgQM"
EMAIL_FROM = "bld@cmbcapital.com.br"
SMTP_HOST = "mail.smtp2go.com"
SMTP_PORT = 2525

# Estilo CSS personalizado
st.markdown("""
    <style>
    .stButton>button {
        width: 100%;
        height: 3em;
        font-size: 20px;
        background-color: #FF4B4B !important;
        color: white !important;
        border: none !important;
        padding: 0.5rem 1rem !important;
        border-radius: 5px !important;
        transition: all 0.3s ease !important;
    }
    .stButton>button:hover {
        background-color: #FF3333 !important;
        box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2) !important;
    }
    .stButton>button:disabled {
        background-color: #4f4f4f !important;
        cursor: not-allowed !important;
        opacity: 0.6 !important;
    }
    </style>
    """, unsafe_allow_html=True)

def enviar_email(total_registros):
    # Preparar o corpo do email
    assunto = "Coleta de Lotes VivaReal Concluída"
    corpo = f"""
    Boa tarde,

    A coleta de lotes do VivaReal foi concluída com sucesso.
    Total de lotes coletados: {total_registros}

    Detalhes da coleta:
    - Fonte: VivaReal
    - Localidade: Eusébio, CE
    - Data: {datetime.now().strftime('%d/%m/%Y')}

    Atenciosamente,
    Equipe de Coleta de Dados
    """

    # Configurar o email
    msg = MIMEMultipart()
    msg['From'] = EMAIL_FROM
    msg['To'] = 'rhuanmateuscmb@gmail.com'  # Ou lista de destinatários
    msg['Subject'] = assunto

    msg.attach(MIMEText(corpo, 'plain'))

    try:
        # Enviar email
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        print("Email enviado com sucesso!")
        return True
    except Exception as e:
        print(f"Erro ao enviar email: {e}")
        return False

class SupabaseManager:
    def __init__(self):
        """
        Inicializa o cliente Supabase com segredos do Streamlit
        """
        self.supabase_url = st.secrets['supabase_urlt']
        self.supabase_key = st.secrets['supabase_keyt']
        
        if not self.supabase_url or not self.supabase_key:
            raise ValueError("Supabase URL e Key são necessários")
        
        self.client = create_client(self.supabase_url, self.supabase_key)

    def inserir_lotes(self, df: pd.DataFrame):
        """
        Insere dados de lotes no Supabase em lote para maior eficiência
        """
        # Verificar último ID no banco
        result = self.client.table('lotes').select('id').order('id', desc=True).limit(1).execute()
        ultimo_id = result.data[0]['id'] if result.data else 0
        
        # Adicionar data de coleta
        df['data_coleta'] = datetime.now().strftime('%Y-%m-%d')
        
        # Adicionar IDs sequenciais a partir do último ID
        df['id'] = range(ultimo_id + 1, ultimo_id + len(df) + 1)
        
        # Preparar registros
        lotes = df.to_dict('records')
        
        try:
            # Inserção em lote
            response = self.client.table('lotes').insert(lotes).execute()
            return len(lotes)
        except Exception as e:
            st.error(f"Erro ao inserir lotes: {e}")
            return 0
        
    def buscar_historico(self):
        """
        Busca o histórico de coletas agrupado por data
        """
        try:
            # Query para agrupar registros por data_coleta e contar
            query = """
            select data_coleta, count(*) as total
            from lotes
            group by data_coleta
            order by data_coleta desc
            """
            
            result = self.client.rpc('get_coleta_historico').execute()
            return result.data
        except Exception as e:
            st.error(f"Erro ao buscar histórico: {e}")
            return []

def configurar_driver():
    options = webdriver.ChromeOptions()
    
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option('excludeSwitches', ['enable-automation'])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument(f'user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--enable-javascript')
    options.add_argument('--disable-gpu')
    options.add_argument('--accept-language=pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7')
    options.add_argument('--accept=text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8')
    options.add_argument('--disable-notifications')
    options.add_argument('--disable-popup-blocking')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-features=VizDisplayCompositor')
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.binary_location = '/usr/bin/chromium'  # Importante para o Streamlit Cloud
    
    return webdriver.Chrome(options=options)

def scroll_primeira_vez(driver):
    wait = WebDriverWait(driver, 20)
    try:
        for _ in range(5):  # Repete 5 vezes
            next_button = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-testid="next-page"]')))
            driver.execute_script("arguments[0].scrollIntoView();", next_button)
            time.sleep(3)  # Espera 3 segundos após cada rolagem
    except Exception as e:
        print(f"Erro ao rolar até o botão: {e}")

def limpar_numero(texto):
    return int(''.join(filter(str.isdigit, texto)))

def extrair_dados(driver):
    wait = WebDriverWait(driver, 20)
    try:
        articles = wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, '[data-cy="rp-property-cd"]')))
        
        dados = []
        for card in articles:
            try:
                localidade = card.find_element(By.CSS_SELECTOR, '[data-cy="rp-cardProperty-location-txt"]').text
                endereco = card.find_element(By.CSS_SELECTOR, '[data-cy="rp-cardProperty-street-txt"]').text
                area_texto = card.find_element(By.CSS_SELECTOR, '[data-cy="rp-cardProperty-propertyArea-txt"]').text.replace('²', '')
                preco_texto = card.find_element(By.CSS_SELECTOR, '[data-cy="rp-cardProperty-price-txt"] .l-text--variant-heading-small').text
                link = card.find_element(By.CSS_SELECTOR, 'a').get_attribute('href')
                
                area = limpar_numero(area_texto)
                preco = limpar_numero(preco_texto)
                
                dados.append({
                    'localidade': localidade,
                    'endereco': endereco,
                    'area': area,
                    'preco': preco,
                    'link': link
                })
            except Exception as e:
                print(f"Erro ao extrair dados do card: {e}")
                continue
                
        return dados
    except TimeoutException:
        st.error("Timeout ao carregar cards")
        return []

def navegar_paginas(driver, num_paginas=1):
    dados_totais = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for pagina in range(1, num_paginas + 1):
        status_text.text(f'Processando página {pagina} de {num_paginas}')
        progress_bar.progress(pagina/num_paginas)
        
        if pagina == 1:
            scroll_primeira_vez(driver)
        else:
            next_button = driver.find_element(By.CSS_SELECTOR, '[data-testid="next-page"]')
            next_button.click()
            time.sleep(2)
            scroll_primeira_vez(driver)
            
        dados_totais.extend(extrair_dados(driver))
    
    progress_bar.progress(1.0)
    status_text.text('Captura finalizada!')
    return dados_totais

def main():
    # Título e descrição
    st.title("🏗️ Coleta Informações Gerais Terrenos - VivaReal")
    
    with st.container():
        st.markdown("""
            <p style='text-align: center; color: #666; margin-bottom: 2rem;'>
                Coleta de dados de terrenos à venda em Eusébio, Ceará
            </p>
        """, unsafe_allow_html=True)
        
        # Container de informações
        with st.expander("ℹ️ Informações sobre a coleta", expanded=True):
            st.markdown("""
            - Serão coletadas 12 páginas de resultados
            - Apenas terrenos em Eusébio/CE
            - Dados salvos automaticamente no Supabase
            - Notificação por email após conclusão
            """)
    
    # Container principal
    supabase_manager = SupabaseManager()
    
    # Botões lado a lado
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🚀 Iniciar Coleta", use_container_width=True):
            with st.spinner("Iniciando coleta de dados..."):
                url = "https://www.vivareal.com.br/venda/ceara/eusebio/lote-terreno_residencial/"
                driver = configurar_driver()
                
                try:
                    driver.get(url)
                    
                    dados = navegar_paginas(driver, 12)
                    
                    if dados:
                        df = pd.DataFrame(dados)
                        st.success(f"✅ Captura finalizada! {len(dados)} lotes encontrados.")
                        
                        # Inserir no Supabase
                        lotes_inseridos = supabase_manager.inserir_lotes(df)
                        st.success(f"✅ {lotes_inseridos} lotes inseridos no Supabase")
                        
                        # Enviar email
                        if enviar_email(len(df)):
                            st.success("✅ Email de notificação enviado")
                        
                        # Mostrar dados e botão de download
                        st.dataframe(df)
                        csv = df.to_csv(index=False).encode('utf-8')
                        st.download_button(
                            "📥 Download CSV",
                            csv,
                            "lotes.csv",
                            "text/csv",
                            key='download-csv'
                        )
                        
                        st.balloons()
                    else:
                        st.error("❌ Nenhum dado foi capturado. Tente novamente.")
                        
                except Exception as e:
                    st.error(f"❌ Erro durante a execução: {str(e)}")
                finally:
                    driver.quit()
    
    with col2:
        if st.button("📊 Ver Histórico", type="secondary", use_container_width=True):
            historico = supabase_manager.buscar_historico()
            if historico:
                st.markdown("### 📅 Histórico de Coletas")
                for registro in historico:
                    st.info(f"{registro['data_coleta']}: {registro['total']} registros")
            else:
                st.info("Nenhuma coleta registrada")

if __name__ == '__main__':
    main()
