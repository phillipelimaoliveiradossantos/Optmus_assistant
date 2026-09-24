"""
app.py
------
Front-end do chatbot (Streamlit).

- Barra de chat para o usuário digitar a dúvida.
- Menu lateral (hambúrguer, recolhido por padrão) com o histórico das
  conversas — título gerado pela própria IA, com base no OBJETIVO real
  da pergunta (não só cortando o começo da frase).
- Imagem de fundo desfocada em tela cheia (detectada automaticamente
  dentro de assets/, não importa o nome/extensão do arquivo).
- Tema claro/escuro controlado por um ícone próprio (☀️ / 🌙), sem usar
  o menu nativo do Streamlit (que foi escondido, junto com o "Deploy").
- Menu lateral fecha ao clicar fora dele, além do botão de fechar.
- A resposta da IA vem da função `send_message_to_ai` em api_client.py.

Como rodar:
    pip install -r requirements.txt
    streamlit run app.py
"""

import base64
import io
import json
import os
import re
import sys
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image
import streamlit as st
import streamlit.components.v1 as components
from streamlit.web import cli as stcli

from api_client import call_api, get_next_resolution, stream_message_to_ai
from auth_service import get_auth

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DA PÁGINA
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="AI Assistant",
    page_icon="⛟",
    layout="wide",
    initial_sidebar_state="collapsed",  # menu começa fechado (estilo hambúrguer)
)

# Injeta o script JS para fechar o menu lateral ao clicar fora dele
components.html(
    """
    <script>
    const doc = window.parent.document;
    doc.addEventListener('click', function(e) {
        const sidebar = doc.querySelector('section[data-testid="stSidebar"]');
        const sidebarNav = doc.querySelector('button[aria-label="Close sidebar"]') || doc.querySelector('button[aria-label="Fechar barra lateral"]');
        if (sidebar && !sidebar.contains(e.target) && sidebarNav && sidebar.getAttribute('aria-expanded') === 'true') {
            // Se o clique for fora da sidebar, simula o clique para fechar
            sidebarNav.click();
        }
    }, true);
    </script>
    """,
    height=0,
    width=0,
)

ASSETS_DIR = Path(__file__).parent / "assets"
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
MAX_TITLE_LENGTH = 42
TICKET_DIR = Path(__file__).parent / "tickets"
HISTORY_DIR = Path(os.getenv("LOCALAPPDATA", Path.home() / ".optimus_truck")) / "OptimusTruck"
HISTORY_FILE = HISTORY_DIR / "chat_history.json"
TICKET_FIELDS = (
    ("nome_usuario", "nome completo"),
    ("hostname", "hostname ou nome da máquina"),
    ("impacto_trabalho", "se o problema impede diretamente seu trabalho (sim/não e como)"),
    ("impacto_outros", "se o problema afeta outras pessoas (sim/não e quem)"),
    ("localizacao", "localização (prédio, andar e sala)"),
    ("contato", "telefone e/ou e-mail"),
)

# ---------------------------------------------------------------------------
# PALETAS DE COR
# ---------------------------------------------------------------------------

TEMAS = {
    "claro": {
        "app_bg": "#FDFDFD",
        "sidebar_bg": "#FFFFFF",
        "sidebar_text": "#000000",  # Cor do texto/título da sidebar no Tema Claro
        "text": "#FFFFFF",
        "subtext": "#FFFFFF",
        "button_bg": "#A4A2A2",
        "button_text": "#FFFFFF",
        "input_text": "#FFFFFF",
        "border": "#A4A2A2",
        "icon_color": "#111111",
        "black": "#ffffff",
        "send_button_bg": "#FFFFFF",
        "send_button_icon": "#111111",
        "menu": "#FFFFFF",
        "background": "#A4A2A2", # cor para o fundo do input (chat)
        "idioma_fundo": "#FFFFFF",
        "idioma_texto": "#111111"
    },
    "escuro": {
        "app_bg": "#FFFFFF",
        "sidebar_bg": "#030303",
        "sidebar_text": "#FFFFFF",  # Cor do texto/título da sidebar no Tema Escuro
        "text": "#000000",
        "subtext": "#000000",
        "button_bg": "#4B4B4B",
        "button_text": "#FFFFFF",
        "input_text": "#FFFFFF",
        "border": "#4B4B4B",
        "icon_color": "#FFFFFF",
        "black": "#000000",
        "send_button_bg": "#FFFCFC",
        "send_button_icon": "#000000",
        "menu": "#030303",
        "background": "#4B4B4B",
        "idioma_fundo": "#000000",
        "idioma_texto": "#000000"
    },
}

IDIOMAS = {
    "en": {
        "history": "💬 History",
        "new_conversation": "➕ New conversation",
        "open_ticket": "🎫 Open ticket",
        "delete_history": "Delete all history",
        "delete_question": "Delete all history from this machine?",
        "delete": "Delete",
        "cancel": "Cancel",
        "empty_history": "No saved conversations.",
        "ticket_title": "Tell support the details",
        "ticket_caption": "Review everything before sending. Fields marked with * are required.",
        "full_name": "Full name *",
        "hostname": "Hostname or machine name",
        "work_impact": "Does the problem directly prevent your work? *",
        "location": "Location (building, floor and room) *",
        "contact": "Phone and/or email *",
        "others_impact": "Does the problem affect other people? *",
        "category": "Category",
        "priority": "Priority",
        "subject": "Subject *",
        "description": "Problem description *",
        "description_hint": "Tell us what happened and which message appeared.",
        "attempts": "What have you tried?",
        "attempts_hint": "List the steps already taken and the result.",
        "authorization": "I confirm that I reviewed the information and authorize sending it to support. No passwords or access codes are included. *",
        "send_ticket": "Send ticket",
        "back_chat": "Back to chat",
        "required_error": "Fill in the required fields and confirm authorization.",
        "missing": " Missing:",
        "choice_title": "How would you like to contact support?",
        "choice_description": "Start a chat to try to solve the problem now or send a complete ticket directly.",
        "start_chat": "💬 Start chat",
        "subtitle": "Welcome to the Daimler Truck service desk. I am Optimus Truck, the official Daimler Truck bot! I am here to help. How can I help you today?",
        "chat_placeholder": "Type your question...",
        "thinking": "Thinking...",
        "checking": "Checking another solution...",
        "ticket_saved": "Ticket saved as",
    },
    "pt": {
        "history": "💬 Histórico",
        "new_conversation": "➕ Nova conversa",
        "open_ticket": "🎫 Abrir ticket",
        "delete_history": "Apagar todo o histórico",
        "delete_question": "Apagar todo o histórico desta máquina?",
        "delete": "Apagar",
        "cancel": "Cancelar",
        "empty_history": "Nenhuma conversa salva.",
        "ticket_title": "Conte os detalhes ao suporte",
        "ticket_caption": "Revise tudo antes de enviar. Campos com * são obrigatórios.",
        "full_name": "Nome completo *",
        "hostname": "Hostname ou nome da máquina",
        "work_impact": "O problema impede diretamente seu trabalho? *",
        "location": "Localização (prédio, andar e sala) *",
        "contact": "Telefone e/ou e-mail *",
        "others_impact": "O problema afeta outras pessoas? *",
        "category": "Categoria",
        "priority": "Prioridade",
        "subject": "Assunto *",
        "description": "Descrição do problema *",
        "description_hint": "Conte o que aconteceu e qual mensagem apareceu.",
        "attempts": "O que você já tentou?",
        "attempts_hint": "Liste os passos já realizados e o resultado.",
        "authorization": "Confirmo que revisei as informações e autorizo o envio destes dados à equipe de suporte. Não inclui senhas ou códigos de acesso. *",
        "send_ticket": "Enviar ticket",
        "back_chat": "Voltar para o chat",
        "required_error": "Preencha os campos obrigatórios e confirme a autorização de envio.",
        "missing": " Faltando:",
        "choice_title": "Como você quer falar com o suporte?",
        "choice_description": "Comece uma conversa para tentar resolver o problema agora ou envie um ticket completo diretamente.",
        "start_chat": "💬 Iniciar chat",
        "subtitle": "",
        "chat_placeholder": "Digite sua pergunta...",
        "thinking": "Pensando...",
        "checking": "Consultando outra orientação...",
        "ticket_saved": "Ticket salvo como",
    },
    "es": {
        "history": "💬 Historial",
        "new_conversation": "➕ Nueva conversación",
        "open_ticket": "🎫 Abrir ticket",
        "delete_history": "Eliminar todo el historial",
        "delete_question": "¿Eliminar todo el historial de esta máquina?",
        "delete": "Eliminar",
        "cancel": "Cancelar",
        "empty_history": "No hay conversaciones guardadas.",
        "ticket_title": "Cuéntale los detalles al soporte",
        "ticket_caption": "Revisa todo antes de enviar. Los campos con * son obligatorios.",
        "full_name": "Nombre completo *",
        "hostname": "Hostname o nombre de la máquina",
        "work_impact": "¿El problema impide directamente tu trabajo? *",
        "location": "Ubicación (edificio, planta y sala) *",
        "contact": "Teléfono y/o correo electrónico *",
        "others_impact": "¿El problema afecta a otras personas? *",
        "category": "Categoría",
        "priority": "Prioridad",
        "subject": "Asunto *",
        "description": "Descripción del problema *",
        "description_hint": "Cuenta qué ocurrió y qué mensaje apareció.",
        "attempts": "¿Qué has intentado?",
        "attempts_hint": "Enumera los pasos realizados y el resultado.",
        "authorization": "Confirmo que revisé la información y autorizo enviarla al soporte. No incluye contraseñas ni códigos de acceso. *",
        "send_ticket": "Enviar ticket",
        "back_chat": "Volver al chat",
        "required_error": "Completa los campos obligatorios y confirma la autorización.",
        "missing": " Faltan:",
        "choice_title": "¿Cómo quieres contactar con soporte?",
        "choice_description": "Inicia un chat para intentar resolver el problema ahora o envía un ticket completo directamente.",
        "start_chat": "💬 Iniciar chat",
        "subtitle": "Bienvenido al servicio de soporte de Daimler Truck. Soy Optimus Truck, el bot oficial de Daimler Truck. Estoy aquí para ayudarte. ¿Cómo puedo ayudarte hoy?",
        "chat_placeholder": "Escribe tu pregunta...",
        "thinking": "Pensando...",
        "checking": "Consultando otra solución...",
        "ticket_saved": "Ticket guardado como",
    },
}

LANDING_TEXTS = {
    "en": {
        "kicker": "Your intelligent support",
        "title": "Clear answers.<br><em>Work in motion.</em>",
        "description": "Optimus Truck brings technical guidance, knowledge base and ticket creation together in one place.",
        "login": "Sign in",
        "register": "Create account",
        "service": "Daimler Truck · Service desk",
        "access": "24/7 access",
        "one_place": "1 place for your conversations",
        "faster": "Faster resolution",
        "language": "Language",
    },
    "pt": {
        "kicker": "Seu suporte inteligente",
        "title": "Respostas claras.<br><em>Trabalho em movimento.</em>",
        "description": "O Optimus Truck reúne orientação técnica, base de conhecimento e abertura de chamados em um único lugar.",
        "login": "Entrar na conta",
        "register": "Criar conta",
        "service": "Daimler Truck · Service desk",
        "access": "Acesso 24/7",
        "one_place": "1 lugar para suas conversas",
        "faster": "Resolução mais rápida",
        "language": "Idioma",
    },
    "es": {
        "kicker": "Tu soporte inteligente",
        "title": "Respuestas claras.<br><em>Trabajo en movimiento.</em>",
        "description": "Optimus Truck reúne orientación técnica, base de conocimiento y creación de tickets en un solo lugar.",
        "login": "Iniciar sesión",
        "register": "Crear cuenta",
        "service": "Daimler Truck · Service desk",
        "access": "Acceso 24/7",
        "one_place": "1 lugar para tus conversaciones",
        "faster": "Resolución más rápida",
        "language": "Idioma",
    },
}

AUTH_TEXTS = {
    "en": {
        "login_title": "Sign in to Optimus Truck", "login_caption": "Access your history and continue where you left off.",
        "email": "Email", "password": "Password", "email_placeholder": "you@company.com", "password_placeholder": "Your password",
        "login_action": "Sign in", "register_link": "I do not have an account", "missing_login": "Enter your email and password.",
        "register_title": "Create your account", "register_caption": "Create your access to keep your conversations organized.",
        "name": "Name", "name_placeholder": "What should we call you?", "confirm_password": "Confirm password", "register_action": "Create account",
        "password_hint": "At least 6 characters", "missing_register": "Fill in all fields.", "password_error": "Passwords must match and contain at least 6 characters.",
        "already_account": "I already have an account", "created": "Account created. Confirm your email and sign in.",
    },
    "pt": {
        "login_title": "Entrar no Optimus Truck", "login_caption": "Acesse seu histórico e continue de onde parou.",
        "email": "E-mail", "password": "Senha", "email_placeholder": "voce@empresa.com", "password_placeholder": "Sua senha",
        "login_action": "Entrar", "register_link": "Ainda não tenho conta", "missing_login": "Informe seu e-mail e sua senha.",
        "register_title": "Criar sua conta", "register_caption": "Crie seu acesso para manter suas conversas organizadas.",
        "name": "Nome", "name_placeholder": "Como devemos chamar você?", "confirm_password": "Confirmar senha", "register_action": "Cadastrar",
        "password_hint": "Mínimo de 6 caracteres", "missing_register": "Preencha todos os campos.", "password_error": "As senhas precisam coincidir e ter pelo menos 6 caracteres.",
        "already_account": "Já tenho uma conta", "created": "Conta criada. Confirme seu e-mail e faça login.",
    },
    "es": {
        "login_title": "Iniciar sesión en Optimus Truck", "login_caption": "Accede a tu historial y continúa donde lo dejaste.",
        "email": "Correo electrónico", "password": "Contraseña", "email_placeholder": "tu@empresa.com", "password_placeholder": "Tu contraseña",
        "login_action": "Iniciar sesión", "register_link": "Aún no tengo cuenta", "missing_login": "Ingresa tu correo y contraseña.",
        "register_title": "Crear tu cuenta", "register_caption": "Crea tu acceso para mantener tus conversaciones organizadas.",
        "name": "Nombre", "name_placeholder": "¿Cómo debemos llamarte?", "confirm_password": "Confirmar contraseña", "register_action": "Crear cuenta",
        "password_hint": "Mínimo 6 caracteres", "missing_register": "Completa todos los campos.", "password_error": "Las contraseñas deben coincidir y tener al menos 6 caracteres.",
        "already_account": "Ya tengo una cuenta", "created": "Cuenta creada. Confirma tu correo e inicia sesión.",
    },
}

# ---------------------------------------------------------------------------
# ESTADO DA SESSÃO E MÉTODOS AUXILIARES
# ---------------------------------------------------------------------------

def init_state():
    if "conversations" not in st.session_state:
        st.session_state.conversations = carregar_historico()
    if "current_id" not in st.session_state:
        if st.session_state.conversations:
            st.session_state.current_id = next(reversed(st.session_state.conversations))
        else:
            nova_conversa(selecionar=True)
    if "tema" not in st.session_state:
        st.session_state.tema = "escuro"
    if "idioma" not in st.session_state:
        st.session_state.idioma = "en"


def history_file_for_user() -> Path:
    user_id = st.session_state.get("auth_user", {}).get("id")
    if not user_id:
        return HISTORY_FILE
    return HISTORY_DIR / "users" / f"{user_id}.json"


def textos():
    return IDIOMAS[st.session_state.idioma]


def selecionar_idioma(idioma: str):
    st.session_state.idioma = idioma


def carregar_historico() -> dict:
    history_file = history_file_for_user()
    if not history_file.exists():
        return {}

    try:
        historico = json.loads(history_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(historico, dict):
        return {}

    conversas_validas = {}
    for conv_id, conversa in historico.items():
        if not isinstance(conv_id, str) or not isinstance(conversa, dict):
            continue
        conversa.setdefault("title", "New conversation")
        conversa.setdefault("messages", [])
        conversa.setdefault("resolution_attempts", [])
        conversa.setdefault("ticket_data", {})
        conversa.setdefault("ticket_step", None)
        conversa.setdefault("entry_mode", "chat" if conversa["messages"] else "choice")
        conversas_validas[conv_id] = conversa
    return conversas_validas


def salvar_historico():
    try:
        history_file = history_file_for_user()
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_file.write_text(
            json.dumps(st.session_state.conversations, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def nova_conversa(
    selecionar: bool = True,
    entry_mode: str = "choice",
    persistir: bool = True,
):
    conv_id = str(uuid.uuid4())
    st.session_state.conversations[conv_id] = {
        "title": "New conversation",
        "messages": [],
        "resolution_attempts": [],
        "ticket_data": {},
        "ticket_step": None,
        "entry_mode": entry_mode,
    }
    if selecionar:
        st.session_state.current_id = conv_id
    if persistir:
        salvar_historico()
    return conv_id


def apagar_historico():
    st.session_state.conversations = {}
    nova_conversa(entry_mode="chat", persistir=False)
    try:
        history_file = history_file_for_user()
        if history_file.exists():
            history_file.unlink()
    except OSError:
        pass


def sair_da_conta():
    get_auth(st.session_state.get("auth_session")).sign_out()
    for chave in ("auth_user", "conversations", "current_id", "ticket_modal_open"):
        st.session_state.pop(chave, None)
    st.session_state.pop("auth_session", None)


def conversa_atual():
    conversa = st.session_state.conversations[st.session_state.current_id]
    conversa.setdefault("resolution_attempts", [])
    conversa.setdefault("ticket_data", {})
    conversa.setdefault("ticket_step", None)
    conversa.setdefault("entry_mode", "chat" if conversa["messages"] else "choice")
    return conversa


def alternar_tema():
    st.session_state.tema = "escuro" if st.session_state.tema == "claro" else "claro"


def _texto_sem_acentos(texto: str) -> str:
    normalizado = unicodedata.normalize("NFKD", texto.lower())
    return "".join(caractere for caractere in normalizado if not unicodedata.combining(caractere))


def usuario_indica_falha(texto: str) -> bool:
    texto_normalizado = _texto_sem_acentos(texto)
    padroes = (
        r"\bnao resolveu\b",
        r"\bnao funcionou\b",
        r"\bnao consegui\b",
        r"\bnao deu certo\b",
        r"\bnao ajudou\b",
        r"\bnao respondeu\b",
        r"\bcontinua (com|sem|dando|apresentando)\b",
        r"\bainda (nao|est[aá])\b",
        r"\bsem sucesso\b",
        r"\bproblema continua\b",
        r"\bdidn.?t work\b",
        r"\bnot working\b",
        r"\bstill (doesn.?t|does not|not)\b",
    )
    return any(re.search(padrao, texto_normalizado) for padrao in padroes)


def usuario_solicita_ticket(texto: str) -> bool:
    texto_normalizado = _texto_sem_acentos(texto)
    padroes = (
        r"\babrir\s+(um\s+)?(ticket|chamado|atendimento)\b",
        r"\b(quero|preciso|gostaria de|posso)\s+abrir\s+(um\s+)?(ticket|chamado|atendimento)\b",
        r"\b(help\s*desk|suporte)\b.*\b(ticket|chamado|atendimento)\b",
        r"\b(ticket|chamado)\b.*\b(help\s*desk|suporte)\b",
    )
    return any(re.search(padrao, texto_normalizado) for padrao in padroes)


def salvar_ticket(conv: dict) -> Path:
    TICKET_DIR.mkdir(exist_ok=True)
    identificador = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    caminho = TICKET_DIR / f"ticket_{identificador}.txt"
    dados = conv["ticket_data"]
    caminho.write_text(
        "Daimler Truck - Ticket de atendimento\n"
        f"Data: {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"Nome: {dados.get('nome_usuario', '')}\n"
        f"Problema principal: {dados.get('problema_principal', '')}\n"
        f"Hostname da maquina: {dados.get('hostname', '')}\n"
        f"Impede diretamente o trabalho: {dados.get('impacto_trabalho', '')}\n"
        f"Afeta outras pessoas: {dados.get('impacto_outros', '')}\n"
        f"Localizacao: {dados.get('localizacao', '')}\n"
        f"Contato: {dados.get('contato', '')}\n"
        "Orientacoes ja tentadas:\n"
        + "\n---\n".join(conv.get("resolution_attempts", []))
        + "\n",
        encoding="utf-8",
    )
    return caminho


def salvar_ticket_direto(conv: dict, dados: dict) -> Path:
    conv["ticket_data"] = dados
    tentativas = dados.get("tentativas", "").strip()
    conv["resolution_attempts"] = [tentativas] if tentativas else []
    salvar_historico()
    return salvar_ticket(conv)


def registrar_dado_do_ticket(conv: dict, resposta_usuario: str) -> str:
    indice = conv["ticket_step"]
    campo, descricao = TICKET_FIELDS[indice]
    conv["ticket_data"][campo] = resposta_usuario.strip()
    proximo_indice = indice + 1
    if proximo_indice < len(TICKET_FIELDS):
        conv["ticket_step"] = proximo_indice
        return f"Obrigado. Agora informe seu {TICKET_FIELDS[proximo_indice][1]}."

    caminho = salvar_ticket(conv)
    conv["ticket_step"] = None
    return (
        "Obrigado. Registrei todos os dados necessários e salvei o atendimento "
        f"em `{caminho.name}`. Por favor, abra um ticket com a equipe de Help Desk "
        "e informe que os dados já foram coletados para o atendimento."
    )


def iniciar_coleta_do_ticket(conv: dict, mensagem_inicial: str | None = None) -> str:
    mensagens_usuario = [
        mensagem["content"]
        for mensagem in conv["messages"]
        if mensagem.get("role") == "user"
    ]
    descricoes = [
        mensagem for mensagem in mensagens_usuario
        if not usuario_indica_falha(mensagem) and not usuario_solicita_ticket(mensagem)
    ]
    conv["ticket_data"]["problema_principal"] = descricoes[-1] if descricoes else "Não informado"
    perfil = st.session_state.get("auth_user", {}).get("profile", {})
    nome = st.session_state.get("auth_user", {}).get("name", "")
    localizacao = " / ".join(
        parte for parte in (perfil.get("local_trabalho"), perfil.get("andar"), perfil.get("sala")) if parte
    )
    contato = perfil.get("telefone", "")
    if perfil.get("melhor_contato") == "email":
        contato = st.session_state.get("auth_user", {}).get("email", contato)
    conv["ticket_data"].update({
        "nome_usuario": nome,
        "localizacao": localizacao,
        "contato": contato,
    })
    conv["profile_confirmation_pending"] = bool(nome or localizacao or contato)
    conv["ticket_step"] = 0
    if conv["profile_confirmation_pending"]:
        dados = ", ".join(
            valor for valor in (nome, localizacao, contato) if valor
        )
        return (
            f"{mensagem_inicial + chr(10) + chr(10) if mensagem_inicial else ''}"
            f"Encontrei estes dados na sua conta: {dados}. Eles estão corretos? "
            "Responda sim para usá-los ou não para informar dados diferentes."
        )
    orientacao = (
        "Sinto muito que não tenha resolvido. Vou registrar um atendimento. "
        "O problema principal já foi identificado e não vou perguntar isso novamente. "
        "Primeiro, informe seu nome completo."
    )
    if mensagem_inicial:
        return (
            f"{mensagem_inicial}\n\n"
            "Vou registrar um atendimento. O problema principal já foi identificado "
            "e não vou perguntar isso novamente. Primeiro, informe seu nome completo."
        )
    return orientacao


def resposta_indica_erro_api(texto: str) -> bool:
    texto = texto.upper()
    return (
        "⚠️ ERRO AO OBTER RESPOSTA" in texto
        or "RESOURCE_EXHAUSTED" in texto
        or "UNAVAILABLE" in texto
        or "SEM COTA" in texto
        or "NÃO FOI POSSÍVEL CONSULTAR" in texto
        or "NAO FOI POSSIVEL CONSULTAR" in texto
    )


def truncar_titulo(texto: str) -> str:
    texto = texto.strip().replace("\n", " ")
    if len(texto) <= MAX_TITLE_LENGTH:
        return texto
    return texto[:MAX_TITLE_LENGTH].rstrip() + "..."


# ---------------------------------------------------------------------------
# GERAÇÃO DO TÍTULO DO HISTÓRICO
# ---------------------------------------------------------------------------

_TITULO_PADROES = [
    r"^(oi+|ol[áa]|e a[íi]|opa|bom dia|boa tarde|boa noite)[\s,!.?]*",
    r"^(tudo bem|como vai|como (voc[eê]|vc) est[áa])[\s,!.?]*",
    r"^estou aqui para\s+",
    r"^eu (queria|gostaria de|quero|preciso de|preciso|necessito de)\s+",
    r"^(queria|gostaria de|quero|preciso de|preciso|necessito de)\s+",
    r"^por favor,?\s+",
    r"^(voc[eê]|vc) (pode|poderia)( me)?( ajudar( com)?)?\s*",
    r"^pode(ria)? me ajudar( com)?\s*",
    r"^fazer (o|a|um|uma)\s+",
    r"^fazer\s+",
    r"^sobre\s+",
    r"^solicitar\s+",
    r"^pedir\s+",
    r"^reportar\s+",
    r"^informar (sobre)?\s*",
    r"^abrir (um )?chamado (para|sobre)?\s+",
    r"^(hi+|hello+|hey+)[\s,!.?]*",
    r"^(how are you|good morning|good afternoon|good evening)[\s,!.?]*",
    r"^i am here to\s+",
    r"^i('m| am)\s+",
    r"^i (would like to|want to|need to|need)\s+",
    r"^(please|could you|can you)( help( me)?( with)?)?\s*",
    r"^to\s+",
    r"^request(ing)?\s+",
    r"^open(ing)? (a )?ticket (for|about)?\s+",
    r"^(a|o|um|uma|as|os|an|the)\s+",
]


def gerar_titulo(texto: str) -> str:
    resultado = texto.strip().lower()

    mudou = True
    while mudou:
        mudou = False
        for padrao in _TITULO_PADROES:
            novo = re.sub(padrao, "", resultado, flags=re.IGNORECASE)
            if novo != resultado:
                resultado = novo.strip()
                mudou = True

    resultado = resultado.strip(" ,.!?").strip()

    if not resultado:
        resultado = texto.strip()

    resultado = resultado[0].upper() + resultado[1:] if resultado else "New conversation"
    return truncar_titulo(resultado)


def gerar_titulo_com_ia(mensagem: str) -> str | None:
    prompt = (
        "Summarize the main topic and intent of the following user message "
        "in 3 to 6 words. Reply with ONLY the short title itself — no "
        "punctuation, no quotes, no explanations, no prefixes like 'Title:'.\n\n"
        f"Message: {mensagem}"
    )

    resultado = call_api("ai", {"question": prompt, "history": []})
    if not resultado["ok"]:
        return None

    data = resultado["data"]
    if isinstance(data, dict):
        texto = None
        for key in ("answer", "response", "message", "text", "result"):
            if key in data:
                texto = str(data[key])
                break
        if texto is None:
            texto = str(data)
    else:
        texto = str(data)

    texto = texto.strip().strip('"').strip("'").strip(".").strip()

    if not texto or len(texto) > 60 or "\n" in texto:
        return None

    texto = texto[0].upper() + texto[1:]
    return truncar_titulo(texto)


# ---------------------------------------------------------------------------
# BACKGROUND DESFOCADO
# ---------------------------------------------------------------------------

def encontrar_imagem_fundo() -> Path | None:
    if not ASSETS_DIR.exists():
        return None
    for arquivo in sorted(ASSETS_DIR.iterdir()):
        if arquivo.is_file() and arquivo.suffix.lower() in IMAGE_EXTENSIONS:
            return arquivo
    return None

AVATAR_EXTENSIONS = (".gif", ".png", ".jpg", ".jpeg", ".webp")


def encontrar_avatar_assistente() -> Path | None:
    if not ASSETS_DIR.exists():
        return None
    for arquivo in ASSETS_DIR.iterdir():
        if arquivo.is_file() and arquivo.stem.lower() == "avatar" and arquivo.suffix.lower() in AVATAR_EXTENSIONS:
            return arquivo
    return None

@st.cache_data(show_spinner=False)
def carregar_imagem_otimizada(path_str: str, mtime: float, max_largura: int = 1600, qualidade: int = 70):
    path = Path(path_str)
    if not path.exists():
        return None
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            if img.width > max_largura:
                proporcao = max_largura / img.width
                nova_altura = int(img.height * proporcao)
                img = img.resize((max_largura, nova_altura), Image.LANCZOS)
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=qualidade, optimize=True)
            return base64.b64encode(buffer.getvalue()).decode()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# ESTILO GERAL
# ---------------------------------------------------------------------------

def aplicar_estilo():
    tema = TEMAS[st.session_state.tema]
    superficie = tema["menu"]
    texto_superficie = tema["sidebar_text"]
    fundo_campo = tema["menu"] if st.session_state.tema == "claro" else tema["background"]
    borda_modal = "transparent" if st.session_state.tema == "escuro" else tema["border"]
    filtro_lixeira = "brightness(0)" if st.session_state.tema == "claro" else "brightness(0) invert(1)"
    idioma_fundo = "#000000" if st.session_state.tema == "escuro" else "#FFFFFF"
    idioma_texto = "#FFFFFF" if st.session_state.tema == "escuro" else "#111111"
    idioma_seta = "#111111" if st.session_state.tema == "claro" else idioma_texto
    tema_fundo = "#000000" if st.session_state.tema == "escuro" else "#FFFFFF"
    tema_icone = "#FFFFFF" if st.session_state.tema == "escuro" else "#111111"

    imagem_path = encontrar_imagem_fundo()
    img_b64 = None
    if imagem_path:
        mtime = imagem_path.stat().st_mtime
        img_b64 = carregar_imagem_otimizada(str(imagem_path), mtime)

    bg_layer_css = ""
    if img_b64:
        bg_layer_css = f"""
        [data-testid="stAppViewContainer"] {{
            position: relative;
        }}

        [data-testid="stAppViewContainer"]::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background-image: url("data:image/jpeg;base64,{img_b64}");
            background-size: cover;
            background-position: center;
            pointer-events: none;
            filter: blur(5px);
            transform: scale(1.05);
            opacity: 0.90;
        }}

        [data-testid="stAppViewContainer"] > .main {{
            position: relative;
            z-index: 1;
        }}
        """

    st.markdown(
        f"""
        <style>
        {bg_layer_css}

        #MainMenu {{ visibility: hidden; }}
        [data-testid="stDeployButton"] {{ display: none !important; }}
        .stDeployButton {{ display: none !important; }}
        [data-testid="stStatusWidget"] {{ visibility: hidden; }}
        footer {{ visibility: hidden; }}

        .main .block-container {{
            padding-top: 0.5rem !important;
            padding-bottom: 2rem !important;
        }}

        [data-testid="stAppViewContainer"] > .main {{
            padding-top: 0 !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    init_state()
    aplicar_estilo()

    if not img_b64:
        arquivos = []
        if ASSETS_DIR.exists():
            arquivos = [f.name for f in ASSETS_DIR.iterdir() if f.name != ".gitkeep"]

        if arquivos:
            st.warning(
                f"Found these files in `{ASSETS_DIR}`: {', '.join(arquivos)} — "
                "but none of them is a valid image (jpg, jpeg, png or webp), or the "
                "file could not be opened. Check whether the file is corrupted.",
                icon="🖼️",
            )
        else:
            st.warning(
                f"The folder `{ASSETS_DIR}` is empty. Place an image file "
                "(jpg, jpeg, png or webp) there to enable the blurred background.",
                icon="🖼️",
            )


# ---------------------------------------------------------------------------
# FECHAR O MENU CLICANDO FORA DELE
# ---------------------------------------------------------------------------

def ativar_fechar_ao_clicar_fora():
    st.html(
        """
        <script>
        (function() {
            const parentDoc = window.parent.document;

            function localizarBotaoFechar(sidebar) {
                const seletores = [
                    'button[data-testid="stSidebarCollapseButton"]',
                    '[data-testid="stSidebarCollapseButton"] button',
                    '[data-testid="stSidebarCollapseButton"]',
                    'button[aria-label*="Close" i]',
                    'button[aria-label*="Collapse" i]',
                    'button[title*="Close" i]',
                    'button[title*="Collapse" i]'
                ];
                for (const seletor of seletores) {
                    const candidato = parentDoc.querySelector(seletor);
                    if (candidato) return candidato.closest('button') || candidato;
                }

                const rectSidebar = sidebar.getBoundingClientRect();
                const botoes = sidebar.querySelectorAll('button');
                for (const botao of botoes) {
                    const rectBotao = botao.getBoundingClientRect();
                    if (rectBotao.top <= rectSidebar.top + 120 &&
                        rectBotao.right >= rectSidebar.right - 100) {
                        return botao;
                    }
                }
                return null;
            }

            function listenerCliqueFora(event) {
                const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar) return;

                // Verifica se o menu lateral está efetivamente visível na tela
                const rect = sidebar.getBoundingClientRect();
                const estaAberto = rect.width > 50 && rect.left >= 0;

                if (!estaAberto) return;

                // A seta de recolher fica dentro da sidebar, mas deve fechá-la.
                const botaoFechar = localizarBotaoFechar(sidebar);
                const alvo = event.target.closest ? event.target.closest('button') : null;
                const alvoSeta = event.target.closest && event.target.closest(
                    '[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapsedControl"], [data-testid="collapsedControl"]'
                );
                const eRegiaoDaSeta = event.clientY <= rect.top + 100 &&
                                      event.clientX >= rect.right - 110;
                if (botaoFechar && (botaoFechar.contains(event.target) || alvo === botaoFechar || alvoSeta || eRegiaoDaSeta)) {
                    botaoFechar.click();
                    return;
                }

                // Se o clique foi dentro do próprio menu lateral, ignora
                if (sidebar.contains(event.target)) return;

                // Se o clique foi no botão hambúrguer/toggle de abrir/fechar, ignora
                const toggle = parentDoc.querySelector('[data-testid="stSidebarCollapsedControl"]');
                if (toggle && toggle.contains(event.target)) return;

                // Fecha o menu quando o clique ocorreu fora dele.
                if (botaoFechar) {
                    botaoFechar.click();
                }
            }

            // Remove ouvinte antigo se existir para evitar duplicidade e registra no window.parent
            if (window.parent.__sidebarClickListener) {
                parentDoc.removeEventListener('pointerdown', window.parent.__sidebarClickListener, true);
            }
            window.parent.__sidebarClickListener = listenerCliqueFora;
            parentDoc.addEventListener('pointerdown', listenerCliqueFora, true);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


def fechar_sidebar_via_js():
    st.html(
        """
        <script>
        (function() {
            const parentDoc = window.parent.document;
            function fecharSeAberta() {
                const sidebar = parentDoc.querySelector('section[data-testid="stSidebar"]');
                if (!sidebar || sidebar.getBoundingClientRect().width <= 50) return;

                const seletores = [
                    'button[data-testid="stSidebarCollapseButton"]',
                    '[data-testid="stSidebarCollapseButton"] button',
                    '[data-testid="stSidebarCollapseButton"]',
                    'button[aria-label*="Collapse" i]',
                    'button[aria-label*="Close" i]',
                    'button[title*="Collapse" i]',
                    'button[title*="Close" i]'
                ];
                for (const seletor of seletores) {
                    const botao = parentDoc.querySelector(seletor);
                    if (botao) {
                        (botao.closest('button') || botao).click();
                        return;
                    }
                }
            }

            [0, 120, 300].forEach(function(atraso) {
                window.parent.setTimeout(fecharSeAberta, atraso);
            });
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


# ---------------------------------------------------------------------------
# ROLAGEM APOS ENVIO DO CHAT
# ---------------------------------------------------------------------------

def ativar_rolagem_apos_enter():
    st.html(
        """
        <script>
        (function() {
            const parentDoc = window.parent.document;

            function rolarChatParaFim() {
                const ancora = parentDoc.querySelector('#chat-bottom-anchor');
                const mensagens = parentDoc.querySelectorAll('[data-testid="stChatMessage"]');
                const alvo = ancora || mensagens[mensagens.length - 1];
                if (alvo) alvo.scrollIntoView({ behavior: 'auto', block: 'end' });

                const elementos = parentDoc.querySelectorAll(
                    '[data-testid="stAppViewContainer"], [data-testid="stMain"], section.main, .main'
                );
                elementos.forEach(function(elemento) {
                    elemento.scrollTop = elemento.scrollHeight;
                });
                if (parentDoc.scrollingElement) {
                    parentDoc.scrollingElement.scrollTop = parentDoc.scrollingElement.scrollHeight;
                }
            }

            if (window.parent.__chatEnterScrollListener) {
                parentDoc.removeEventListener('keydown', window.parent.__chatEnterScrollListener, true);
            }

            window.parent.__chatEnterScrollListener = function(evento) {
                const campo = evento.target;
                const eCampoDoChat = campo && (
                    campo.closest('[data-testid="stChatInput"]')
                );
                if (!eCampoDoChat || evento.key !== 'Enter' || evento.shiftKey) return;

                [80, 300, 700, 1200].forEach(function(atraso) {
                    window.parent.setTimeout(rolarChatParaFim, atraso);
                });
            };
            parentDoc.addEventListener('keydown', window.parent.__chatEnterScrollListener, true);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


# ---------------------------------------------------------------------------
# REFORÇO VIA JAVASCRIPT
# ---------------------------------------------------------------------------

def reforcar_ajustes_via_js(tema: dict):
    tema_json = json.dumps(tema)

    st.html(
        f"""
        <script>
        (function() {{
            const tema = {tema_json};
            const parentDoc = window.parent.document;

            function escondeDeploy() {{
                const elementos = parentDoc.querySelectorAll('button, a, span');
                elementos.forEach(function(el) {{
                    const texto = (el.innerText || el.textContent || '').trim();
                    if (texto === 'Deploy') {{
                        el.style.setProperty('display', 'none', 'important');
                        if (el.parentElement) {{
                            el.parentElement.style.setProperty('display', 'none', 'important');
                        }}
                    }}
                }});
            }}

            function arrumaSetaDoMenu() {{
                const candidatos = parentDoc.querySelectorAll(
                    '[data-testid*="ollapse" i]'
                );
                candidatos.forEach(function(el) {{
                    el.style.setProperty('background-color', 'rgba(255,255,255,0.9)', 'important');
                    el.style.setProperty('border-radius', '8px', 'important');
                    el.style.setProperty('padding', '4px', 'important');

                    const svg = el.querySelector('svg');
                    if (svg) {{
                        svg.style.setProperty('fill', '#000000', 'important');
                        svg.style.setProperty('stroke', '#000000', 'important');
                        svg.style.setProperty('color', '#000000', 'important');
                        svg.style.setProperty('width', '1.6rem', 'important');
                        svg.style.setProperty('height', '1.6rem', 'important');
                    }}
                }});
            }}

            function rolarParaFim(elementoFoco) {{
                if (elementoFoco && elementoFoco.scrollIntoView) {{
                    elementoFoco.scrollIntoView({{ behavior: 'smooth', block: 'end' }});
                }}

                const ancora = parentDoc.querySelector('#chat-bottom-anchor');
                if (ancora) {{
                    ancora.scrollIntoView({{ behavior: 'smooth', block: 'end' }});
                }}

                const seletores = [
                    '[data-testid="stAppViewContainer"]',
                    '[data-testid="stMain"]',
                    'section.main',
                    '.main',
                    'html',
                    'body'
                ];
                seletores.forEach(function(seletor) {{
                    const elemento = parentDoc.querySelector(seletor);
                    if (elemento) {{
                        elemento.scrollTop = elemento.scrollHeight;
                    }}
                }});

                const mensagens = parentDoc.querySelectorAll('[data-testid="stChatMessage"]');
                const ultimaMensagem = mensagens[mensagens.length - 1];
                if (ultimaMensagem) {{
                    ultimaMensagem.scrollIntoView({{ behavior: 'smooth', block: 'end' }});
                }}
            }}

            function arrumaChatInput() {{
                const textarea = parentDoc.querySelector(
                    '[data-testid="stChatInput"] textarea'
                );
                if (!textarea) return;

                textarea.style.setProperty('color', tema.input_text, 'important');
                textarea.style.setProperty('caret-color', tema.input_text, 'important');
                textarea.style.setProperty('-webkit-text-fill-color', tema.input_text, 'important');

                if (!textarea.__autoScrollAtivo) {{
                    textarea.__autoScrollAtivo = true;
                    textarea.addEventListener('input', function() {{
                        window.parent.requestAnimationFrame(function() {{
                            rolarParaFim(textarea);
                        }});
                    }});
                    textarea.addEventListener('keydown', function(evento) {{
                        if (evento.key === 'Enter' && !evento.shiftKey) {{
                            window.setTimeout(function() {{ rolarParaFim(); }}, 100);
                            window.setTimeout(function() {{ rolarParaFim(); }}, 700);
                        }}
                    }});
                }}

                const container = textarea.closest('[data-testid="stChatInputContainer"]') || textarea.closest('div');
                if (container) {{
                    container.style.setProperty('background-color', tema.background, 'important');
                    container.style.setProperty('border', '1px solid ' + tema.border, 'important');
                    container.style.setProperty('border-radius', '16px', 'important');

                    const campoInterno = textarea.closest('[data-baseweb="textarea"]') || textarea.parentElement;
                    if (campoInterno) {{
                        campoInterno.style.setProperty('background-color', tema.background, 'important');
                    }}

                    const botaoEnviar = container.querySelector('button');
                    if (botaoEnviar) {{
                        botaoEnviar.style.setProperty('background-color', tema.send_button_bg, 'important');
                        const svgEnviar = botaoEnviar.querySelector('svg');
                        if (svgEnviar) {{
                            svgEnviar.style.setProperty('fill', tema.send_button_icon, 'important');
                            svgEnviar.style.setProperty('color', tema.send_button_icon, 'important');
                        }}
                    }}
                }}

                const larguraJanela = window.parent.innerWidth;
                let el = textarea;
                for (let i = 0; i < 6 && el.parentElement; i++) {{
                    el = el.parentElement;
                    const rect = el.getBoundingClientRect();
                    const eFaixaCompleta = rect.width >= larguraJanela - 4;

                    if (eFaixaCompleta) {{
                        el.style.setProperty('background', 'transparent', 'important');
                        el.style.setProperty('background-color', 'transparent', 'important');
                        el.style.setProperty('backdrop-filter', 'none', 'important');
                        el.style.setProperty('box-shadow', 'none', 'important');
                    }}
                }}
            }}

            function arrumaBotaoTema() {{
                const botoes = parentDoc.querySelectorAll('button');
                botoes.forEach(function(el) {{
                    const texto = (el.innerText || el.textContent || '').trim();
                    if (texto === '☀️' || texto === '🌙') {{
                        el.style.setProperty('background-color', 'transparent', 'important');
                        el.style.setProperty('background', 'transparent', 'important');
                        el.style.setProperty('border', 'none', 'important');
                        el.style.setProperty('box-shadow', 'none', 'important');
                        if (el.parentElement) {{
                            el.parentElement.style.setProperty('background-color', 'transparent', 'important');
                            el.parentElement.style.setProperty('background', 'transparent', 'important');
                        }}
                    }}
                }});
            }}

            function arrumaSeletoresDeIdioma() {{
                const seletores = parentDoc.querySelectorAll(
                    '[class*="st-key-chat_language_selector"], [class*="st-key-ticket_language_selector"]'
                );
                const texto = tema.black === '#000000' ? '#FFFFFF' : '#111111';
                const fundo = tema.black === '#000000' ? '#000000' : '#FFFFFF';
                const seta = tema.black === '#000000' ? '#FFFFFF' : '#111111';
                seletores.forEach(function(seletor) {{
                    seletor.querySelectorAll('[data-baseweb="select"] > div, [data-baseweb="select"] div').forEach(function(el) {{
                        el.style.setProperty('background-color', fundo, 'important');
                        el.style.setProperty('background', fundo, 'important');
                        el.style.setProperty('color', texto, 'important');
                        el.style.setProperty('border-color', tema.border, 'important');
                    }});
                    seletor.querySelectorAll('span').forEach(function(el) {{
                        el.style.setProperty('color', texto, 'important');
                        el.style.setProperty('fill', texto, 'important');
                        el.style.setProperty('stroke', texto, 'important');
                    }});
                    seletor.querySelectorAll('svg, path').forEach(function(el) {{
                        el.style.setProperty('color', seta, 'important');
                        el.style.setProperty('fill', seta, 'important');
                        el.style.setProperty('stroke', seta, 'important');
                    }});
                }});
            }}

            function aumentaBaloesDeChat() {{
                const balões = parentDoc.querySelectorAll(
                    '[data-testid*="ChatMessage" i]'
                );
                balões.forEach(function(el) {{
                    el.style.setProperty('padding', '1rem 1.25rem', 'important');
                    el.style.setProperty('margin-bottom', '0.9rem', 'important');
                    el.style.setProperty('border-radius', '14px', 'important');
                    el.style.setProperty('font-size', '1.05rem', 'important');
                    el.style.setProperty('line-height', '1.5', 'important');
                }});
            }}

            function aplicarTudo() {{
                try {{ escondeDeploy(); }} catch (e) {{}}
                try {{ arrumaSetaDoMenu(); }} catch (e) {{}}
                try {{ arrumaChatInput(); }} catch (e) {{}}
                try {{ aumentaBaloesDeChat(); }} catch (e) {{}}
                try {{ arrumaBotaoTema(); }} catch (e) {{}}
                try {{ arrumaSeletoresDeIdioma(); }} catch (e) {{}}
            }}

            aplicarTudo();
            window.setTimeout(function() {{ rolarParaFim(); }}, 150);

            if (!window.__ajustesObserverAtivo) {{
                window.__ajustesObserverAtivo = true;
                const observer = new MutationObserver(function() {{
                    aplicarTudo();
                    window.clearTimeout(window.__scrollChatTimeout);
                    window.__scrollChatTimeout = window.setTimeout(function() {{
                        rolarParaFim();
                    }}, 120);
                }});
                observer.observe(parentDoc.body, {{ childList: true, subtree: true }});
            }} else {{
                aplicarTudo();
            }}
        }})();
        </script>
        """,
    )


# ---------------------------------------------------------------------------
# SIDEBAR — HISTÓRICO
# ---------------------------------------------------------------------------

def render_sidebar():
    t = textos()
    with st.sidebar:
        with st.container(key="sidebar_header"):
            topo, acoes = st.columns([6.7, 1.8], vertical_alignment="center")
            with topo:
                st.markdown("<h1>Daimler Truck</h1>", unsafe_allow_html=True)
            with acoes:
                sair, perfil = st.columns(2, gap="small")
                with sair:
                    if st.button("🚪", key="logout_button", help="Sair da conta"):
                        sair_da_conta()
                        st.rerun()
                with perfil:
                    if st.button("👤", key="profile_button", help="Dados pessoais"):
                        st.session_state.profile_modal_open = True
                        st.rerun()
        if st.session_state.get("profile_modal_open", False):
            st.session_state.profile_modal_open = False
            render_profile_modal()
        titulo_historico, acao_historico = st.columns([8, 1])
        with titulo_historico:
            st.markdown(f'<div class="history-title">{t["history"]}</div>', unsafe_allow_html=True)
        with acao_historico:
            if st.button("🗑️", key="apagar_historico", help=t["delete_history"]):
                st.session_state.confirmar_apagar_historico = True
                st.rerun()

        if st.session_state.get("confirmar_apagar_historico", False):
            st.warning(t["delete_question"])
            confirmar, cancelar = st.columns(2)
            with confirmar:
                if st.button(t["delete"], key="confirmar_apagar", use_container_width=True):
                    apagar_historico()
                    st.session_state.confirmar_apagar_historico = False
                    st.rerun()
            with cancelar:
                if st.button(t["cancel"], key="cancelar_apagar", use_container_width=True):
                    st.session_state.confirmar_apagar_historico = False
                    st.rerun()

        if st.button(t["new_conversation"], use_container_width=True):
            nova_conversa(entry_mode="chat")
            st.session_state.fechar_sidebar_apos_nova = True
            st.rerun()

        if st.button(t["open_ticket"], use_container_width=True):
            st.session_state.ticket_modal_open = True
            st.rerun()

        st.divider()

        ids_ordenados = list(st.session_state.conversations.keys())[::-1]
        encontrou_historico = False

        for conv_id in ids_ordenados:
            conv = st.session_state.conversations[conv_id]
            if not conv["messages"] and conv["title"] == "New conversation":
                continue
            encontrou_historico = True
            is_current = conv_id == st.session_state.current_id

            label = ("📍 " if is_current else "") + conv["title"]
            if st.button(label, key=f"hist_{conv_id}", use_container_width=True):
                st.session_state.current_id = conv_id
                st.rerun()

        if not encontrou_historico:
            st.caption(t["empty_history"])


# ---------------------------------------------------------------------------
# ÁREA PRINCIPAL — CHAT
# ---------------------------------------------------------------------------

@st.dialog("Support ticket", width="medium", dismissible=True)
def render_ticket_modal():
    conv = conversa_atual()
    t = textos()
    categorias = {
        "en": ("General support", "Access", "Hardware", "Network", "Software"),
        "pt": ("Suporte geral", "Acesso", "Hardware", "Rede", "Software"),
        "es": ("Soporte general", "Acceso", "Hardware", "Red", "Software"),
    }[st.session_state.idioma]
    prioridades = {
        "en": ("Normal", "High", "Urgent"),
        "pt": ("Normal", "Alta", "Urgente"),
        "es": ("Normal", "Alta", "Urgente"),
    }[st.session_state.idioma]

    titulo_ticket, seletor_ticket = st.columns([7, 1])
    with titulo_ticket:
        st.markdown(f"### {t['ticket_title']}")
    with seletor_ticket:
        idioma_ticket = st.selectbox(
            "Language",
            ("EN", "PT", "ES"),
            index=("en", "pt", "es").index(st.session_state.idioma),
            key="ticket_language_selector",
            label_visibility="collapsed",
        )
    idioma_ticket_codigo = {"EN": "en", "PT": "pt", "ES": "es"}[idioma_ticket]
    if idioma_ticket_codigo != st.session_state.idioma:
        selecionar_idioma(idioma_ticket_codigo)
        st.rerun(scope="fragment")

    st.caption(t["ticket_caption"])
    with st.form("ticket_form"):
        col1, col2 = st.columns(2)
        with col1:
            nome = st.text_input(t["full_name"], key="ticket_nome")
            hostname = st.text_input(t["hostname"], key="ticket_hostname")
            impacto_trabalho = st.text_area(
                t["work_impact"],
                placeholder=t["work_impact"],
                height=90,
                key="ticket_impacto_trabalho",
            )
            localizacao = st.text_input(t["location"], key="ticket_localizacao")
        with col2:
            contato = st.text_input(t["contact"], key="ticket_contato")
            impacto_outros = st.text_area(
                t["others_impact"],
                placeholder=t["others_impact"],
                height=90,
                key="ticket_impacto_outros",
            )
            categoria = st.selectbox(
                t["category"],
                categorias,
            )
            prioridade = st.selectbox(t["priority"], prioridades)

        assunto = st.text_input(t["subject"], key="ticket_assunto")
        problema_principal = st.text_area(
            t["description"],
            placeholder=t["description_hint"],
            height=120,
            key="ticket_descricao",
        )
        tentativas = st.text_area(
            t["attempts"],
            placeholder=t["attempts_hint"],
            height=90,
            key="ticket_tentativas",
        )
        confirmado = st.checkbox(t["authorization"], key="ticket_confirmado")

        enviar, voltar = st.columns(2)
        with enviar:
            enviar_ticket = st.form_submit_button(t["send_ticket"], type="primary", use_container_width=True)
        with voltar:
            voltar_chat = st.form_submit_button(t["back_chat"], use_container_width=True)

    if voltar_chat:
        st.session_state.ticket_modal_open = False
        st.rerun()

    if enviar_ticket:
        obrigatorios = {
            "nome": nome,
            "contato": contato,
            "impacto do trabalho": impacto_trabalho,
            "impacto em outras pessoas": impacto_outros,
            "localização": localizacao,
            "assunto": assunto,
            "descrição do problema": problema_principal,
        }
        faltantes = [campo for campo, valor in obrigatorios.items() if not valor.strip()]
        if faltantes or not confirmado:
            mensagem = t["required_error"]
            if faltantes:
                mensagem += t["missing"] + " " + ", ".join(faltantes) + "."
            st.error(mensagem)
            return

        dados = {
            "nome_usuario": nome,
            "hostname": hostname,
            "impacto_trabalho": impacto_trabalho,
            "impacto_outros": impacto_outros,
            "localizacao": localizacao,
            "contato": contato,
            "problema_principal": f"[{categoria} | Prioridade: {prioridade}] {assunto}: {problema_principal}",
            "tentativas": tentativas,
        }
        caminho = salvar_ticket_direto(conv, dados)
        conv["entry_mode"] = "chat"
        st.session_state.ticket_modal_open = False
        st.success(f"{t['ticket_saved']} {caminho.name}.")
        st.rerun()


def render_entry_choice():
    t = textos()
    with st.container(key="entry_choice"):
        st.markdown(
            '<div class="entry-choice">'
            f'<h2>{t["choice_title"]}</h2>'
            f'<p>{t["choice_description"]}</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        col_chat, col_ticket = st.columns(2)
        with col_chat:
            if st.button(t["start_chat"], type="primary", use_container_width=True):
                conversa_atual()["entry_mode"] = "chat"
                st.rerun()
        with col_ticket:
            if st.button(t["open_ticket"], use_container_width=True):
                st.session_state.ticket_modal_open = True
                st.rerun()

def render_chat():
    conv = conversa_atual()
    t = textos()

    avatar_path = encontrar_avatar_assistente()
    avatar_assistente = str(avatar_path) if avatar_path else None
    col_titulo, col_idioma, col_tema = st.columns([10, 1, 0.85], vertical_alignment="center")

    with col_titulo:
        st.markdown('<div class="chat-title">Optimus Truck</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="chat-subtitle">{t["subtitle"]}</div>',
            unsafe_allow_html=True,
        )

    with col_idioma:
        idioma_chat = st.selectbox(
            "Language",
            ("EN", "PT", "ES"),
            index=("en", "pt", "es").index(st.session_state.idioma),
            key="chat_language_selector",
            label_visibility="collapsed",
        )
        idioma_chat_codigo = {"EN": "en", "PT": "pt", "ES": "es"}[idioma_chat]
        if idioma_chat_codigo != st.session_state.idioma:
            selecionar_idioma(idioma_chat_codigo)
            st.rerun()

    with col_tema:
        with st.container(key="tema_toggle"):
            icone = "☀️" if st.session_state.tema == "escuro" else "🌙"
            if st.button(icone, key="alternar_tema", help="Toggle light/dark theme"):
                alternar_tema()
                st.rerun()

    if conv["entry_mode"] == "choice" and not conv["messages"]:
        render_entry_choice()
        return

    for msg in conv["messages"]:
        avatar = avatar_assistente if msg["role"] == "assistant" else None
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])

    pergunta = st.chat_input(t["chat_placeholder"])

    if pergunta:
        if not conv["messages"]:
            titulo_ia = gerar_titulo_com_ia(pergunta)
            conv["title"] = titulo_ia if titulo_ia else gerar_titulo(pergunta)

        conv["messages"].append({"role": "user", "content": pergunta})
        with st.chat_message("user"):
            st.markdown(pergunta)

        with st.chat_message("assistant", avatar=avatar_assistente):
            if conv.get("profile_confirmation_pending"):
                confirmou = _texto_sem_acentos(pergunta).strip() in {"sim", "s", "yes", "y", "correto", "corretos"}
                conv["profile_confirmation_pending"] = False
                if confirmou:
                    pendentes = [
                        indice for indice, (campo, _) in enumerate(TICKET_FIELDS)
                        if not conv["ticket_data"].get(campo)
                    ]
                    if pendentes:
                        conv["ticket_step"] = pendentes[0]
                        resposta = f"Perfeito. Agora informe seu {TICKET_FIELDS[pendentes[0]][1]}."
                    else:
                        conv["ticket_step"] = None
                        resposta = "Perfeito. Os dados da sua conta foram confirmados. Descreva o problema para eu registrar o ticket."
                else:
                    conv["ticket_step"] = 0
                    resposta = "Tudo bem. Vou confirmar os dados manualmente. Primeiro, informe seu nome completo."
                st.markdown(resposta)
            elif conv["ticket_step"] is not None:
                resposta = registrar_dado_do_ticket(conv, pergunta)
                st.markdown(resposta)
            elif usuario_solicita_ticket(pergunta):
                resposta = iniciar_coleta_do_ticket(conv)
                st.markdown(resposta)
            elif usuario_indica_falha(pergunta):
                with st.spinner(t["checking"]):
                    resposta = get_next_resolution(
                        pergunta,
                        conv["messages"],
                        conv["resolution_attempts"],
                    )

                if not resposta or "NO_SECOND_SOLUTION" in resposta.upper():
                    resposta = iniciar_coleta_do_ticket(conv)
                elif resposta_indica_erro_api(resposta):
                    resposta = iniciar_coleta_do_ticket(conv)
                else:
                    conv["resolution_attempts"].append(resposta)
                st.markdown(resposta)
            else:
                with st.spinner(t["thinking"]):
                    resposta = ""
                    mensagem_stream = st.empty()
                    for trecho in stream_message_to_ai(pergunta, conv["messages"]):
                        resposta += trecho
                        mensagem_stream.markdown(resposta + "▌")
                    mensagem_stream.markdown(resposta)

        conv["messages"].append({"role": "assistant", "content": resposta})
        salvar_historico()
        st.rerun()

    st.markdown('<div id="chat-bottom-anchor" style="height: 1px; scroll-margin-bottom: 110px;"></div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# PORTA DE ENTRADA E AUTENTICACAO
# ---------------------------------------------------------------------------

def render_landing_style():
    imagem_path = encontrar_imagem_fundo()
    img_b64 = None
    if imagem_path:
        img_b64 = carregar_imagem_otimizada(str(imagem_path), imagem_path.stat().st_mtime, 1800, 78)
    background = f"url(data:image/jpeg;base64,{img_b64})" if img_b64 else "linear-gradient(135deg, #101111 0%, #25251e 100%)"
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
        #MainMenu, [data-testid="stDeployButton"], footer, [data-testid="stStatusWidget"] {{ display: none !important; }}
        [data-testid="stAppViewContainer"] {{ background: #111210; }}
        [data-testid="stAppViewContainer"]::before {{
            content: ""; position: fixed; inset: 0; z-index: 0; background-image: {background};
            background-size: cover; background-position: center; filter: saturate(.9) brightness(.96);
        }}
        [data-testid="stAppViewContainer"]::after {{
            content: ""; position: fixed; inset: 0; z-index: 0;
            background: radial-gradient(circle at 78% 22%, rgba(218, 235, 73, .12), transparent 30%),
                        linear-gradient(115deg, rgba(13, 14, 13, .42) 8%, rgba(13, 14, 13, .16) 62%, rgba(13, 14, 13, .02));
        }}
        [data-testid="stHeader"] {{ background: transparent !important; }}
        html, body {{ overflow-y:scroll !important; overflow-x:hidden !important; scrollbar-gutter:stable !important; }}
        html::-webkit-scrollbar, body::-webkit-scrollbar {{ width:10px !important; height:0 !important; }}
        html::-webkit-scrollbar-track, body::-webkit-scrollbar-track {{ background:rgba(0,0,0,.18) !important; }}
        html::-webkit-scrollbar-thumb, body::-webkit-scrollbar-thumb {{ background:rgba(255,255,255,.62) !important; border-radius:8px !important; border:2px solid transparent !important; background-clip:padding-box !important; }}
        [data-testid="stAppViewContainer"] {{ min-height:100vh !important; overflow:visible !important; }}
        [data-testid="stMain"] {{ overflow:visible !important; }}
        .main .block-container {{ position: relative; z-index: 1; max-width: 1240px; padding: .2rem 4rem 8rem !important; min-height:115vh !important; overscroll-behavior-y:auto !important; }}
        .landing-nav {{ display:flex; align-items:center; justify-content:space-between; animation: rise .7s ease both; position:relative; top:0; }}
        .landing-brand {{ color:#ffffff; font:700 1.05rem 'Space Grotesk', sans-serif; letter-spacing:.02em; text-shadow:0 2px 12px rgba(0,0,0,.55); }}
        .landing-brand span {{ display:inline-block; width:10px; height:10px; margin-right:10px; background:#ffe83b; border-radius:50%; box-shadow:0 0 24px #ffe83b; }}
        .landing-status {{ color:#ffffff; font:600 .78rem 'DM Sans', sans-serif; letter-spacing:.12em; text-transform:uppercase; text-shadow:0 2px 10px rgba(0,0,0,.55); }}
        [class*="st-key-landing_language"] {{ position:relative !important; z-index:8 !important; width:4rem !important; margin:-2.2rem 0 0 auto !important; transform:translateY(-.7rem) !important; }}
        [class*="st-key-landing_language"] label {{ display:none !important; }}
        [class*="st-key-landing_language"] [data-baseweb="select"] > div {{ min-height:1.65rem !important; height:1.65rem !important; padding:0 .25rem !important; font-size:.75rem !important; background:rgba(10,12,10,.48) !important; border:1px solid rgba(255,255,255,.45) !important; color:#ffffff !important; }}
        [class*="st-key-landing_language"] [data-baseweb="select"] span, [class*="st-key-landing_language"] svg {{ color:#ffffff !important; fill:#ffffff !important; stroke:#ffffff !important; }}
        .landing-hero {{ min-height: 0; display:flex; align-items:center; padding: 0 0 .2rem; position:relative; top:-1.2rem; }}
        .landing-copy {{ max-width: 740px; animation: rise .8s .12s ease both; }}
        .landing-kicker {{ color:#ffe83b; font:800 .82rem 'DM Sans',sans-serif; letter-spacing:.16em; text-transform:uppercase; margin-bottom:1.35rem; text-shadow:0 2px 14px rgba(0,0,0,.72), 0 0 12px rgba(255,232,59,.22); }}
        .landing-title {{ color:#ffffff; font:700 clamp(3rem, 6.4vw, 6rem)/.94 'Space Grotesk', sans-serif; letter-spacing:-.045em; margin:0; text-shadow:0 3px 16px rgba(0,0,0,.62); }}
        .landing-title em {{ color:#ffe83b; font-style:normal; text-shadow:0 3px 18px rgba(0,0,0,.7), 0 0 16px rgba(255,232,59,.2); }}
        .landing-description {{ color:#ffffff; font:600 1.08rem/1.6 'DM Sans',sans-serif; max-width:550px; margin:1.8rem 0 2.4rem; text-shadow:0 2px 14px rgba(0,0,0,.78); }}
        .landing-proof {{ display:flex; gap:2.5rem; color:#ffffff; font:500 .84rem 'DM Sans',sans-serif; margin-top:0; position:relative; top:-1rem; text-shadow:0 2px 10px rgba(0,0,0,.58); }}
        .landing-proof strong {{ display:block; color:#ffffff; font:700 1.35rem 'Space Grotesk',sans-serif; margin-bottom:.25rem; }}
        div[data-testid="stHorizontalBlock"] {{ gap: .9rem; }}
        [class*="st-key-landing_actions"] {{ position:relative !important; z-index:5 !important; pointer-events:auto !important; margin-top:-.8rem !important; top:-1rem !important; }}
        [class*="st-key-landing_actions"] button {{ min-height:3.35rem !important; border-radius:999px !important; font:600 .92rem 'DM Sans',sans-serif !important; transition:transform .2s ease, box-shadow .2s ease !important; position:relative !important; z-index:6 !important; pointer-events:auto !important; }}
        [class*="st-key-landing_actions"] button:hover {{ transform:translateY(-3px); box-shadow:0 12px 28px rgba(0,0,0,.3) !important; }}
        [class*="st-key-landing_login_button"] button {{
            background:#ffe83b !important;
            background-color:#ffe83b !important;
            border-color:#ffe83b !important;
            color:#151711 !important;
        }}
        [class*="st-key-landing_login_button"] button p {{ color:#151711 !important; }}
        [class*="st-key-landing_register_button"] button {{
            background:rgba(255,255,255,.13) !important;
            background-color:rgba(255,255,255,.13) !important;
            border:1px solid rgba(255,255,255,.48) !important;
            color:#f4f5ed !important;
        }}
        [class*="st-key-landing_register_button"] button p {{ color:#f4f5ed !important; }}
        .landing-features {{ display:grid; grid-template-columns:repeat(3,1fr); gap:1px; background:rgba(255,255,255,.18); border-top:1px solid rgba(255,255,255,.18); animation: rise .8s .3s ease both; position:relative; top:0; }}
        .landing-feature {{ background:rgba(14,15,14,.64); padding:1.25rem 1.35rem; backdrop-filter:blur(12px); }}
        .landing-feature b {{ display:block; color:#f4f5ed; font:600 .95rem 'Space Grotesk',sans-serif; margin-bottom:.38rem; }}
        .landing-feature span {{ color:rgba(244,245,237,.60); font:400 .8rem/1.45 'DM Sans',sans-serif; }}
        [data-testid="stDialog"] {{ font-family:'DM Sans',sans-serif; }}
        [data-testid="stDialog"] > div {{ border:1px solid rgba(217,235,75,.35) !important; border-radius:22px !important; background:#171914 !important; }}
        [data-testid="stDialog"] h1, [data-testid="stDialog"] h2, [data-testid="stDialog"] h3, [data-testid="stDialog"] label, [data-testid="stDialog"] p {{ color:#f4f5ed !important; }}
        [data-testid="stDialog"] input {{ background:#252821 !important; border:1px solid rgba(255,255,255,.16) !important; color:#f4f5ed !important; border-radius:10px !important; }}
        [data-testid="stDialog"] button[kind="primary"], [data-testid="stDialog"] button[data-testid="stBaseButton-primary"] {{ background:#ffe83b !important; border:1px solid #ffe83b !important; color:#151711 !important; }}
        [data-testid="stDialog"] button[kind="primary"] p, [data-testid="stDialog"] button[data-testid="stBaseButton-primary"] p {{ color:#151711 !important; }}
        [data-testid="stDialog"] form button[type="submit"],
        [data-testid="stDialog"] form button[data-testid="stBaseButton-primary"] {{
            background:#ffe83b !important;
            background-color:#ffe83b !important;
            border:1px solid #ffe83b !important;
            color:#151711 !important;
        }}
        [data-testid="stDialog"] form button[type="submit"] p,
        [data-testid="stDialog"] form button[data-testid="stBaseButton-primary"] p {{ color:#151711 !important; }}
        [data-testid="stDialog"] form button {{
            background:#ffe83b !important;
            background-color:#ffe83b !important;
            border:1px solid #ffe83b !important;
            color:#151711 !important;
        }}
        [data-testid="stDialog"] form button p,
        [data-testid="stDialog"] form button span {{ color:#151711 !important; }}
        [data-testid="stDialog"] button {{ border-radius:10px !important; }}
        @keyframes rise {{ from {{ opacity:0; transform:translateY(18px); }} to {{ opacity:1; transform:translateY(0); }} }}
        @media (max-width:700px) {{ .main .block-container {{ padding:1rem 1.4rem 1.2rem !important; }} .landing-hero {{ padding:2rem 0 1.3rem; }} .landing-title {{ font-size:3.4rem; }} .landing-features {{ grid-template-columns:1fr; }} .landing-proof {{ gap:1.1rem; }} .landing-status {{ display:none; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            const app = doc.querySelector('[data-testid="stAppViewContainer"]');
            const main = doc.querySelector('[data-testid="stMain"]');
            const candidates = [app, main, doc.scrollingElement, doc.documentElement, doc.body].filter(Boolean);
            const scrollTarget = candidates.find(function(element) {
                return element.scrollHeight > element.clientHeight;
            }) || app || doc.scrollingElement || doc.documentElement;

            scrollTarget.style.setProperty('overflow-y', 'auto', 'important');
            scrollTarget.style.setProperty('overflow-x', 'hidden', 'important');

            if (window.parent.__landingWheelListener) {
                doc.removeEventListener('wheel', window.parent.__landingWheelListener, true);
            }
            window.parent.__landingWheelListener = function(event) {
                if (!scrollTarget) return;
                const canScroll = scrollTarget.scrollHeight > scrollTarget.clientHeight;
                if (!canScroll) return;
                event.preventDefault();
                scrollTarget.scrollTop += event.deltaY;
            };
            doc.addEventListener('wheel', window.parent.__landingWheelListener, {capture:true, passive:false});
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )
    st.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            if (window.parent.__authModalEnterListener) {
                doc.removeEventListener('keydown', window.parent.__authModalEnterListener, true);
            }
            window.parent.__authModalEnterListener = function(event) {
                if (event.key !== 'Enter' || event.shiftKey) return;
                const dialog = event.target.closest('[data-testid="stDialog"]');
                const form = event.target.closest('form');
                if (!dialog || !form) return;
                const submit = form.querySelector('button[type="submit"]');
                if (!submit) return;
                event.preventDefault();
                submit.click();
            };
            doc.addEventListener('keydown', window.parent.__authModalEnterListener, true);
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )

    st.html(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            function styleLandingButtons() {
                doc.querySelectorAll('button').forEach(function(button) {
                    const text = (button.innerText || button.textContent || '').trim();
                    const isLogin = text === 'Entrar na conta' || button.closest('[class*="st-key-landing_login_button"]');
                    const isRegister = text === 'Criar conta' || button.closest('[class*="st-key-landing_register_button"]');
                    const inAuthDialog = button.closest('[data-testid="stDialog"] form');
                    const isModalSubmit = inAuthDialog && button.type === 'submit';
                    if (!isLogin && !isRegister && !isModalSubmit) return;
                    const isYellow = isLogin || isModalSubmit;
                    const color = isYellow ? '#ffe83b' : 'rgba(255,255,255,.13)';
                    const border = isYellow ? '#ffe83b' : 'rgba(255,255,255,.48)';
                    const textColor = isYellow ? '#151711' : '#f4f5ed';
                    button.style.setProperty('ba
                    button.style.setProperty('color', textColor, 'important');
                    button.querySelectorAll('p, span').forEach(function(child) {
                        child.style.setProperty('color', textColor, 'important');ckground', color, 'important');
                    button.style.setProperty('background-color', color, 'important');
                    button.style.setProperty('border-color', border, 'important');
                    });
                });
            }
            styleLandingButtons();
            if (window.parent.__landingButtonObserver) {
                window.parent.__landingButtonObserver.disconnect();
            }
            window.parent.__landingButtonObserver = new MutationObserver(styleLandingButtons);
            window.parent.__landingButtonObserver.observe(doc.body, {childList:true, subtree:true});
        })();
        </script>
        """,
        unsafe_allow_javascript=True,
    )


@st.dialog("Dados pessoais", dismissible=True)
def render_profile_modal():
    usuario = st.session_state.get("auth_user", {})
    perfil = usuario.get("profile", {})
    st.caption("Esses dados serão usados para preencher seus tickets.")
    with st.form("profile_form", enter_to_submit=True):
        nome = st.text_input("Nome", value=usuario.get("name", ""))
        local_trabalho = st.text_input("Local de trabalho", value=perfil.get("local_trabalho", ""))
        andar = st.text_input("Andar", value=perfil.get("andar", ""))
        sala = st.text_input("Sala", value=perfil.get("sala", ""))
        horario = st.text_input("Horário de trabalho", value=perfil.get("horario_trabalho", ""))
        contato = st.selectbox(
            "Melhor contato",
            ("email", "telefone"),
            index=0 if perfil.get("melhor_contato", "email") == "email" else 1,
        )
        telefone = st.text_input("Telefone", value=perfil.get("telefone", ""))
        salvar = st.form_submit_button("Salvar dados", type="primary", use_container_width=True)
    if salvar:
        novo_perfil = {
            "local_trabalho": local_trabalho.strip(),
            "andar": andar.strip(),
            "sala": sala.strip(),
            "horario_trabalho": horario.strip(),
            "melhor_contato": contato,
            "telefone": telefone.strip(),
        }
        result = get_auth(st.session_state.get("auth_session")).update_profile(
            usuario.get("id", ""), novo_perfil, nome
        )
        if not result["ok"]:
            st.error(result["error"])
            return
        usuario["name"] = nome.strip() or usuario.get("name", "Usuário")
        usuario["profile"] = novo_perfil
        st.session_state.auth_user = usuario
        st.session_state.profile_modal_open = False
        st.success("Dados pessoais atualizados.")
        st.rerun()


@st.dialog("Optimus Truck", dismissible=True)
def render_login_modal():
    t = AUTH_TEXTS[st.session_state.get("idioma", "en")]
    st.markdown(f"## {t['login_title']}")
    st.caption(t["login_caption"])
    with st.form("login_form", enter_to_submit=True):
        email = st.text_input(t["email"], placeholder=t["email_placeholder"])
        password = st.text_input(t["password"], type="password", placeholder=t["password_placeholder"])
        submit = st.form_submit_button(t["login_action"], type="secondary", use_container_width=True)
    if submit:
        if not email.strip() or not password:
            st.error(t["missing_login"])
            return
        result = get_auth().sign_in(email, password)
        if not result["ok"]:
            st.error(result["error"])
            return
        st.session_state.auth_user = result["user"]
        st.session_state.auth_session = result.get("session", {})
        st.session_state.auth_modal = None
        st.rerun()
    if st.button(t["register_link"], use_container_width=True):
        st.session_state.auth_modal = "register"
        st.rerun()


@st.dialog("Optimus Truck", dismissible=True)
def render_register_modal():
    t = AUTH_TEXTS[st.session_state.get("idioma", "en")]
    st.markdown(f"## {t['register_title']}")
    st.caption(t["register_caption"])
    with st.form("register_form", enter_to_submit=True):
        name = st.text_input(t["name"], placeholder=t["name_placeholder"])
        email = st.text_input(t["email"], placeholder=t["email_placeholder"])
        password = st.text_input(t["password"], type="password", placeholder=t["password_hint"])
        confirmation = st.text_input(t["confirm_password"], type="password")
        submit = st.form_submit_button(t["register_action"], type="secondary", use_container_width=True)
    if submit:
        if not name.strip() or not email.strip() or not password:
            st.error(t["missing_register"])
            return
        if len(password) < 6 or password != confirmation:
            st.error(t["password_error"])
            return
        result = get_auth().sign_up(name, email, password)
        if not result["ok"]:
            st.error(result["error"])
            return
        st.session_state.auth_modal = "login"
        st.session_state.registered_message = t["created"]
        st.rerun()
    if st.button(t["already_account"], use_container_width=True):
        st.session_state.auth_modal = "login"
        st.rerun()


def render_landing():
    st.session_state.setdefault("auth_modal", None)
    st.session_state.setdefault("idioma", "en")
    t = LANDING_TEXTS[st.session_state.idioma]
    render_landing_style()
    st.markdown(
        f'<div class="landing-nav"><div class="landing-brand"><span></span>OPTIMUS TRUCK</div><div class="landing-status">{t["service"]}</div></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="landing_language"):
        idioma = st.selectbox(
            t["language"],
            ("EN", "PT", "ES"),
            index=("en", "pt", "es").index(st.session_state.idioma),
            key="landing_language_selector",
            label_visibility="collapsed",
        )
    idioma_codigo = {"EN": "en", "PT": "pt", "ES": "es"}[idioma]
    if idioma_codigo != st.session_state.idioma:
        st.session_state.idioma = idioma_codigo
        st.session_state.auth_modal = None
        st.rerun()
    st.markdown(
        f'<div class="landing-hero"><div class="landing-copy"><div class="landing-kicker">{t["kicker"]}</div><h1 class="landing-title">{t["title"]}</h1><p class="landing-description">{t["description"]}</p></div></div>',
        unsafe_allow_html=True,
    )
    with st.container(key="landing_actions"):
        entrar, cadastrar, _ = st.columns([1.1, 1.1, 2.8])
        with entrar:
            st.button(
                t["login"],
                type="primary",
                use_container_width=True,
                key="landing_login_button",
                on_click=lambda: st.session_state.update(auth_modal="login"),
            )
        with cadastrar:
            st.button(
                t["register"],
                use_container_width=True,
                key="landing_register_button",
                on_click=lambda: st.session_state.update(auth_modal="register"),
            )
    st.markdown(
        f'<div class="landing-proof"><div><strong>24/7</strong>{t["access"]}</div><div><strong>1 lugar</strong>{t["one_place"]}</div><div><strong>+ rápido</strong>{t["faster"]}</div></div><div class="landing-features"><div class="landing-feature"><b>Contexto preservado</b><span>{t["one_place"]}</span></div><div class="landing-feature"><b>Orientação confiável</b><span>{t["description"]}</span></div><div class="landing-feature"><b>Escalonamento simples</b><span>{t["faster"]}</span></div></div>',
        unsafe_allow_html=True,
    )
    registered_message = st.session_state.pop("registered_message", None)
    if registered_message:
        st.toast(registered_message)
    if st.session_state.auth_modal == "login":
        render_login_modal()
    elif st.session_state.auth_modal == "register":
        render_register_modal()


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    if "auth_user" not in st.session_state:
        render_landing()
        return
    init_state()
    st.session_state.setdefault("ticket_modal_open", False)
    aplicar_estilo()
    ativar_fechar_ao_clicar_fora()
    ativar_rolagem_apos_enter()
    reforcar_ajustes_via_js(TEMAS[st.session_state.tema])
    render_sidebar()
    render_chat()
    if st.session_state.pop("fechar_sidebar_apos_nova", False):
        fechar_sidebar_via_js()
    if st.session_state.ticket_modal_open:
        st.session_state.ticket_modal_open = False
        render_ticket_modal()


if __name__ == "__main__":
    if st.runtime.exists():
        main()
    else:
        sys.argv = ["streamlit", "run", sys.argv[0]]
        sys.exit(stcli.main())