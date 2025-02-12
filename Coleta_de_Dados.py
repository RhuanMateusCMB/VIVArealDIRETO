# Bibliotecas para interface web
import streamlit as st
import streamlit.components.v1 as components

# Gmail API
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
from email.mime.text import MIMEText

# Manipulação de dados
import pandas as pd

# Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

# Utilitários
import time
import random
from datetime import datetime
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass
from supabase import create_client

# Configuração da página Streamlit
st.set_page_config(
    page_title="CMB - Capital",
    page_icon="🏗️",
    layout="wide"
)

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

@dataclass
class ConfiguracaoScraper:
    tempo_espera: int = 10  # Reduzido de 15 para 10
    pausa_rolagem: int = 1  # Reduzido de 2 para 1
    espera_carregamento: int = 2  # Reduzido de 4 para 2
    url_base: str = "https://www.vivareal.com.br/venda/ceara/eusebio/lote-terreno_residencial/"
    tentativas_max: int = 3

class SupabaseManager:
    def __init__(self):
        self.url = st.secrets["SUPABASE_URL"]
        self.key = st.secrets["SUPABASE_KEY"]
        self.supabase = create_client(self.url, self.key)

    def inserir_dados(self, df):
        result = self.supabase.table('imoveisdireto').select('id').order('id.desc').limit(1).execute()
        ultimo_id = result.data[0]['id'] if result.data else 0
        
        df['id'] = df['id'].apply(lambda x: x + ultimo_id)
        df['data_coleta'] = pd.to_datetime(df['data_coleta']).dt.strftime('%Y-%m-%d')
        
        registros = df.to_dict('records')
        self.supabase.table('imoveisdireto').insert(registros).execute()

    def verificar_coleta_hoje(self):
        try:
            hoje = datetime.now().strftime('%Y-%m-%d')
            result = self.supabase.table('imoveisdireto').select('data_coleta').eq('data_coleta', hoje).execute()
            return len(result.data) > 0
        except Exception as e:
            st.error(f"Erro ao verificar coleta: {str(e)}")
            return True

    def buscar_historico(self):
        try:
            result = self.supabase.rpc(
                'get_coleta_historico',
                {}).execute()
            return result.data
        except Exception as e:
            st.error(f"Erro ao buscar histórico: {str(e)}")
            return []

class GmailSender:
    def __init__(self):
        self.creds = Credentials.from_authorized_user_info(
            info={
                "client_id": st.secrets["GOOGLE_CREDENTIALS"]["client_id"],
                "client_secret": st.secrets["GOOGLE_CREDENTIALS"]["client_secret"],
                "refresh_token": st.secrets["GOOGLE_CREDENTIALS"]["refresh_token"]
            },
            scopes=['https://www.googleapis.com/auth/gmail.send']
        )
        self.service = build('gmail', 'v1', credentials=self.creds)

    def enviar_email(self, total_registros):
        message = MIMEText(f"Coleta de lotes do site VivaReal foi concluída com sucesso. Total de dados coletados: {total_registros}")
        message['to'] = 'cabf05@gmail.com'
        message['subject'] = 'Coleta VivaReal Concluída'
        message['from'] = st.secrets["GOOGLE_CREDENTIALS"]["client_email"]
        
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        
        try:
            self.service.users().messages().send(
                userId='me', body={'raw': raw}).execute()
            return True
        except Exception as e:
            st.error(f"Erro ao enviar email: {str(e)}")
            return False

class ScraperVivaReal:
    def __init__(self, config: ConfiguracaoScraper):
        self.config = config
        self.logger = self._configurar_logger()

    @staticmethod
    def _configurar_logger() -> logging.Logger:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        return logging.getLogger(__name__)

    def _get_random_user_agent(self):
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.0.0 Safari/537.36'
        ]
        return random.choice(user_agents)

    def _configurar_navegador(self) -> webdriver.Chrome:
        try:
            opcoes_chrome = Options()
            opcoes_chrome.add_argument('--disable-blink-features=AutomationControlled')
            opcoes_chrome.add_experimental_option('excludeSwitches', ['enable-automation'])
            opcoes_chrome.add_experimental_option('useAutomationExtension', False)
            opcoes_chrome.add_argument('--headless=new')
            opcoes_chrome.add_argument('--no-sandbox')
            opcoes_chrome.add_argument('--disable-dev-shm-usage')
            opcoes_chrome.add_argument('--window-size=1920,1080')
            opcoes_chrome.add_argument('--disable-blink-features=AutomationControlled')
            opcoes_chrome.add_argument('--enable-javascript')
            
            user_agent = self._get_random_user_agent()
            opcoes_chrome.add_argument(f'--user-agent={user_agent}')
            opcoes_chrome.add_argument('--accept-language=pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7')
            opcoes_chrome.add_argument('--accept=text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8')
            
            opcoes_chrome.add_argument('--disable-notifications')
            opcoes_chrome.add_argument('--disable-popup-blocking')
            opcoes_chrome.add_argument('--disable-extensions')
            opcoes_chrome.add_argument('--disable-gpu')
            
            service = Service("/usr/bin/chromedriver")
            navegador = webdriver.Chrome(service=service, options=opcoes_chrome)
            
            navegador.execute_cdp_cmd('Network.setUserAgentOverride', {
                "userAgent": user_agent,
                "platform": "Windows NT 10.0; Win64; x64"
            })
            
            navegador.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            navegador.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt']})")
            navegador.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
            
            return navegador
        except Exception as e:
            self.logger.error(f"Erro ao configurar navegador: {str(e)}")
            return None

    def _verificar_pagina_carregada(self, navegador: webdriver.Chrome) -> bool:
        try:
            return navegador.execute_script("return document.readyState") == "complete"
        except Exception:
            return False

    def _capturar_localizacao(self, navegador: webdriver.Chrome) -> tuple:
        try:
            time.sleep(self.config.espera_carregamento)

            try:
                localizacao_elemento = WebDriverWait(navegador, self.config.tempo_espera).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.listings-wrapper'))
                )
                texto_localizacao = localizacao_elemento.text.strip()
                if texto_localizacao:
                    partes = texto_localizacao.split(' - ')
                    if len(partes) == 2:
                        return partes[0], partes[1].strip()
            except Exception:
                pass
    
            url_parts = navegador.current_url.split('/')
            for i, part in enumerate(url_parts):
                if part == 'ceara':
                    return 'Eusébio', 'CE'
                    
            return 'Eusébio', 'CE'
    
        except Exception as e:
            self.logger.error(f"Erro ao capturar localização: {str(e)}")
            return 'Eusébio', 'CE'

    def _rolar_pagina(self, navegador: webdriver.Chrome) -> None:
        try:
            altura_total = navegador.execute_script("return document.body.scrollHeight")
            altura_atual = 0
            passo = altura_total / 4
            
            for _ in range(4):
                altura_atual += passo
                navegador.execute_script(f"window.scrollTo(0, {altura_atual});")
                time.sleep(random.uniform(0.5, 1.0))
                
            navegador.execute_script(f"window.scrollTo(0, {altura_total - 200});")
            time.sleep(1)
        except Exception as e:
            self.logger.error(f"Erro ao rolar página: {str(e)}")

    def _extrair_dados_imovel(self, imovel: webdriver.remote.webelement.WebElement,
                    id_global: int, pagina: int) -> Optional[Dict]:
        try:
            wait = WebDriverWait(imovel, 10)
            
            try:
                preco_elemento = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="rp-cardProperty-price-txt"] p:first-child'))
                )
                preco_texto = preco_elemento.text
            except Exception as e:
                self.logger.warning(f"Erro ao extrair preço: {e}")
                return None

            try:
                area_elemento = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-cy="rp-cardProperty-propertyArea-txt"]'))
                )
                area_texto = area_elemento.text
            except Exception as e:
                self.logger.warning(f"Erro ao extrair área: {e}")
                return None

            def converter_preco(texto: str) -> float:
                try:
                    numero = texto.replace('R$', '').replace('.', '').replace(',', '.').strip()
                    return float(numero)
                except (ValueError, AttributeError):
                    return 0.0

            def converter_area(texto: str) -> float:
                try:
                    numero = texto.replace('m²', '').replace(',', '.').strip()
                    return float(numero)
                except (ValueError, AttributeError):
                    return 0.0

            preco = converter_preco(preco_texto)
            area = converter_area(area_texto)
            preco_m2 = round(preco / area, 2) if area > 0 else 0.0

            try:
                titulo = imovel.find_element(By.CSS_SELECTOR, 'span.property-card__title').text
            except Exception:
                titulo = "Título não disponível"

            try:
                endereco = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'span[class*="address"]'))
                ).text
            except Exception:
                endereco = "Endereço não disponível"

            try:
                link = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'a[class*="property-card__content-link"]'))
                ).get_attribute('href')
            except Exception:
                link = ""

            if preco == 0 or area == 0:
                self.logger.warning(f"Dados incompletos para imóvel ID {id_global}: Preço={preco}, Área={area}")
                return None

            return {
                'id': id_global,
                'titulo': titulo,
                'endereco': endereco,
                'area_m2': area,
                'preco_real': preco,
                'preco_m2': preco_m2,
                'link': link,
                'pagina': pagina,
                'data_coleta': datetime.now().strftime("%Y-%m-%d"),
                'estado': '',
                'localidade': ''
            }

        except Exception as e:
            self.logger.error(f"Erro ao extrair dados: {str(e)}")
            return None

    def _encontrar_botao_proxima(self, espera: WebDriverWait) -> Optional[webdriver.remote.webelement.WebElement]:
        seletores = [
            "//button[contains(., 'Próxima página')]",
            "//a[contains(., 'Próxima página')]",
            "//button[@title='Próxima página']",
            "//a[@title='Próxima página']"
        ]

        for seletor in seletores:
            try:
                return espera.until(EC.element_to_be_clickable((By.XPATH, seletor)))
            except:
                continue
        return None

    def coletar_dados(self, num_paginas: int = 32) -> Optional[pd.DataFrame]:
        navegador = None
        todos_dados: List[Dict] = []
        id_global = 0
        progresso = st.progress(0)
        status = st.empty()
    
        try:
            self.logger.info("Iniciando coleta de dados...")
            navegador = self._configurar_navegador()
            if navegador is None:
                st.error("Não foi possível inicializar o navegador")
                return None
    
            espera = WebDriverWait(navegador, self.config.tempo_espera)
            navegador.get(self.config.url_base)
            self.logger.info("Navegador acessou a URL com sucesso")
            self.logger.info(f"URL atual: {navegador.current_url}")
            
            # Aguarda carregamento inicial
            for _ in range(30):
                if self._verificar_pagina_carregada(navegador):
                    self.logger.info("Página carregada completamente")
                    break
                time.sleep(1)
            
            # Primeira rolagem para carregar conteúdo
            self._rolar_pagina(navegador)
            self.logger.info("Primeira rolagem concluída")
            
            try:
                self.logger.info("Procurando lista de resultados...")
                lista_resultados = espera.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 'div.listings-wrapper, div.ListingCard_result-card__ie9wP'))
                )
                self.logger.info("Lista de resultados encontrada")
                self.logger.info(f"HTML da lista: {lista_resultados.get_attribute('outerHTML')[:200]}...")
            except Exception as e:
                self.logger.error(f"Não foi possível encontrar a lista de resultados. Erro: {str(e)}")
                self.logger.error(f"HTML da página: {navegador.page_source[:500]}...")
                return None
    
            localidade, estado = self._capturar_localizacao(navegador)
            if not localidade or not estado:
                st.error("Não foi possível capturar a localização")
                return None
    
            for pagina in range(1, num_paginas + 1):
                try:
                    status.text(f"⏳ Processando página {pagina}/{num_paginas}")
                    progresso.progress(pagina / num_paginas)
                    self.logger.info(f"Processando página {pagina}")
                    
                    # Pausa aleatória reduzida
                    time.sleep(random.uniform(0.5, 1.5))
                    
                    self._rolar_pagina(navegador)
                    self.logger.info(f"Rolagem da página {pagina} concluída")
    
                    imoveis = None
                    for tentativa in range(3):
                        try:
                            self.logger.info(f"Tentativa {tentativa + 1} de encontrar imóveis...")
                            imoveis = espera.until(EC.presence_of_all_elements_located(
                                (By.CSS_SELECTOR, 'div.ListingCard_result-card__ie9wP')
                            ))
                            self.logger.info(f"Encontrados {len(imoveis)} imóveis")
                            if imoveis:
                                break
                            time.sleep(5)
                        except Exception as e:
                            self.logger.error(f"Erro na tentativa {tentativa + 1}: {str(e)}")
                            time.sleep(5)
                            continue
    
                    if not imoveis:
                        self.logger.warning(f"Sem imóveis na página {pagina}")
                        break
    
                    self.logger.info(f"Iniciando processamento de {len(imoveis)} imóveis")
                    for imovel in imoveis:
                        id_global += 1
                        if dados := self._extrair_dados_imovel(imovel, id_global, pagina):
                            dados['estado'] = estado
                            dados['localidade'] = localidade
                            todos_dados.append(dados)
                            self.logger.info(f"Imóvel {id_global} processado com sucesso")
    
                    if pagina < num_paginas:
                        self.logger.info("Procurando botão próxima página...")
                        botao_proxima = self._encontrar_botao_proxima(espera)
                        if not botao_proxima:
                            self.logger.warning("Botão próxima página não encontrado")
                            break
                        
                        self.logger.info("Clicando no botão próxima página...")
                        navegador.execute_script("arguments[0].click();", botao_proxima)
                        time.sleep(1)  # Reduzido de 2 para 1 segundo
                        self.logger.info("Aguardando carregamento da próxima página...")
                        
                        # Aguarda o carregamento da nova página
                        for _ in range(10):
                            if self._verificar_pagina_carregada(navegador):
                                self.logger.info("Nova página carregada")
                                break
                            time.sleep(0.5)
    
                except Exception as e:
                    self.logger.error(f"Erro na página {pagina}: {str(e)}")
                    continue
    
            self.logger.info(f"Coleta finalizada. Total de {len(todos_dados)} imóveis coletados")
            return pd.DataFrame(todos_dados) if todos_dados else None
    
        except Exception as e:
            self.logger.error(f"Erro crítico: {str(e)}")
            st.error(f"Erro durante a coleta: {str(e)}")
            return None
    
        finally:
            if navegador:
                try:
                    navegador.quit()
                except Exception as e:
                    self.logger.error(f"Erro ao fechar navegador: {str(e)}")

def main():
    try:
        # Título e descrição
        st.title("🏗️ Coleta Informações Gerais Terrenos - Eusebio, CE")
        
        with st.container():
            st.markdown("""
                <p style='text-align: center; color: #666; margin-bottom: 2rem;'>
                    Coleta de dados de terrenos à venda em Eusébio, Ceará
                </p>
            """, unsafe_allow_html=True)
            
            # Container de informações
            with st.expander("ℹ️ Informações sobre a coleta", expanded=True):
                st.markdown("""
                - Serão coletadas 32 páginas de resultados
                - Apenas terrenos em Eusébio/CE
                """)
        
        # Container principal
        db = SupabaseManager()
        coleta_realizada = db.verificar_coleta_hoje()

        # Aviso de coleta já realizada
        if coleta_realizada:
            st.warning("Coleta já realizada hoje. Nova coleta disponível amanhã.", icon="⚠️")

        # Botões lado a lado
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Iniciar Coleta", disabled=coleta_realizada, use_container_width=True):
                with st.spinner("Iniciando coleta de dados..."):
                    config = ConfiguracaoScraper()
                    scraper = ScraperVivaReal(config)
                    df = scraper.coletar_dados()
                    
                    if df is not None:
                        try:
                            db.inserir_dados(df)
                            gmail = GmailSender()
                            gmail.enviar_email(len(df))
                            st.success("✅ Dados coletados e salvos com sucesso!")
                            st.balloons()
                            time.sleep(2)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao salvar no banco: {str(e)}")

        with col2:
            if st.button("📊 Ver Histórico", type="secondary", use_container_width=True):
                historico = db.buscar_historico()
                if historico:
                    st.markdown("### 📅 Histórico de Coletas")
                    for registro in historico:
                        st.info(f"{registro['data_coleta']}: {registro['total']} registros")
                else:
                    st.info("Nenhuma coleta registrada")
                    
    except Exception as e:
        st.error(f"❌ Erro inesperado: {str(e)}")

if __name__ == "__main__":
    main()
