"""
api_client.py
--------------
Camada de conexão com APIs e Gemini (com contorno para SSL corporativo e versão de API v1).
"""

import os
import time
import requests
from google import genai
from google.genai import types
from config import API_ENDPOINTS, REQUEST_TIMEOUT
from knowledge_base import buscar_contexto, buscar_resposta_local

# Desativa alertas de requisições inseguras para o módulo requests tradicional
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- CONFIGURAÇÃO DO CLIENTE GEMINI COM BYPASS DE SSL E VERSÃO V1 ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Força o uso da api_version="v1" e desativa a verificação estrita de SSL do proxy corporativo
http_options = types.HttpOptions(
    api_version="v1",
    client_args={"verify": False}
)

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=http_options
)


def _build_headers(endpoint_config: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    api_key = endpoint_config.get("api_key")
    if api_key:
        header_name = endpoint_config.get("auth_header", "Authorization")
        scheme = endpoint_config.get("auth_scheme", "")
        headers[header_name] = f"{scheme}{api_key}"
    return headers


def call_api(api_name: str, payload: dict, method: str = "POST") -> dict:
    """Realiza requisições genéricas para qualquer API cadastrada no config.py."""
    if api_name not in API_ENDPOINTS:
        return {"ok": False, "error": f"API '{api_name}' não está cadastrada em config.py."}

    endpoint = API_ENDPOINTS[api_name]
    url = endpoint.get("url", "")
    
    if not url:
        return {"ok": False, "error": f"A URL da API '{api_name}' não está configurada."}

    headers = _build_headers(endpoint)

    try:
        if method.upper() == "GET":
            response = requests.get(url, params=payload, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)
        else:
            response = requests.post(url, json=payload, headers=headers, timeout=REQUEST_TIMEOUT, verify=False)

        response.raise_for_status()
        return {"ok": True, "data": response.json()}

    except requests.exceptions.ConnectionError:
        return {"ok": False, "error": f"Não foi possível conectar à API '{api_name}' em {url}."}
    except requests.exceptions.Timeout:
        return {"ok": False, "error": f"A API '{api_name}' demorou demais para responder (timeout)."}
    except requests.exceptions.HTTPError as e:
        return {"ok": False, "error": f"Erro HTTP na API '{api_name}': {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Erro inesperado ao chamar '{api_name}': {e}"}


def _build_ai_prompt(question: str, history: list[dict] = None) -> str:
    historico = history or []
    mensagens_recentes = historico[-6:]
    contexto_busca = "\n".join(
        str(mensagem.get("content", ""))
        for mensagem in mensagens_recentes
        if mensagem.get("content")
    )
    # A pergunta atual deve pesar mais que respostas anteriores, que podem
    # conter uma conclusao incorreta sobre a ausencia de documentos.
    contexto = buscar_contexto(f"{question}\n{contexto_busca}")
    instrucoes = (
        "Responda sempre no mesmo idioma usado na PERGUNTA. "
        "O idioma dos DOCUMENTOS serve apenas como fonte e nunca deve definir "
        "o idioma da resposta. Use os documentos como fonte principal. "
        "Se houver DOCUMENTOS abaixo, trate-os como evidencia obrigatoria e "
        "responda com base neles. Nao diga que a informacao nao foi encontrada "
        "quando os DOCUMENTOS apresentarem uma orientacao relacionada, mesmo "
        "que a pergunta tenha erros de digitacao ou use outro idioma. "
        "Considere o HISTORICO para entender perguntas curtas, continuacoes e "
        "erros simples de digitacao, sem inventar informacoes. "
        "Nao exija que a pergunta use as mesmas palavras dos documentos: "
        "interprete o significado e relacione a situacao descrita pelo usuario "
        "aos trechos mais adequados. "
        "Se a resposta nao estiver nos documentos, diga claramente que essa "
        "informacao nao foi encontrada na base e nao invente dados.\n\n"
    )
    historico_formatado = "\n".join(
        f"{mensagem.get('role', 'user').upper()}: {mensagem.get('content', '')}"
        for mensagem in mensagens_recentes
    )
    referencia = f"HISTORICO DA CONVERSA:\n{historico_formatado}\n\n"
    if contexto:
        return f"{instrucoes}{referencia}DOCUMENTOS:\n{contexto}\n\nPERGUNTA:\n{question}"
    return (
        f"{instrucoes}{referencia}Nao foram encontrados trechos relevantes nos documentos locais. "
        f"Responda com conhecimento geral, deixando claro quando nao souber.\n\n"
        f"PERGUNTA:\n{question}"
    )


def stream_message_to_ai(question: str, history: list[dict] = None):
    """Gera partes da resposta conforme o Gemini as disponibiliza."""
    resposta_local = buscar_resposta_local(question)
    if resposta_local:
        yield resposta_local
        return

    for tentativa in range(2):
        try:
            chat = client.chats.create(model="gemini-3.6-flash")
            response_stream = chat.send_message_stream(
                message=_build_ai_prompt(question, history),
            )
            encontrou_texto = False
            for response in response_stream:
                texto = getattr(response, "text", None)
                if texto:
                    encontrou_texto = True
                    yield texto
            if not encontrou_texto:
                yield "⚠️ O modelo não retornou nenhum texto."
            return
        except Exception as e:
            erro = str(e)
            if "429" in erro or "RESOURCE_EXHAUSTED" in erro:
                resposta_local = buscar_resposta_local(question)
                if resposta_local:
                    yield resposta_local
                    return
                yield "No momento, o assistente está temporariamente sem cota para consultar a IA."
                return

            erro_temporario = "503" in erro or "UNAVAILABLE" in erro
            if tentativa == 0 and erro_temporario:
                time.sleep(1)
                continue
            resposta_local = buscar_resposta_local(question)
            if resposta_local:
                yield resposta_local
                return
            yield (
                "Não foi possível consultar o assistente neste momento. "
                "Tente novamente em instantes ou informe que não conseguiu resolver "
                "para iniciarmos o atendimento do Help Desk."
            )
            return


def send_message_to_ai(question: str, history: list[dict] = None) -> str:
    """Mantem uma versao sincrona para chamadas existentes."""
    return "".join(stream_message_to_ai(question, history))


def get_next_resolution(question: str, history: list[dict], attempts: list[str]) -> str:
    """Solicita uma proxima orientacao do KB sem repetir tentativas anteriores."""
    tentativas = "\n".join(f"- {tentativa}" for tentativa in attempts) or "- nenhuma"
    prompt = (
        "O usuario informou que a orientacao anterior nao resolveu o problema. "
        "Consulte os DOCUMENTOS e proponha uma unica proxima acao pratica, "
        "diferente das tentativas abaixo. Nao repita nenhuma tentativa anterior. "
        "Responda no idioma da ultima mensagem do usuario. "
        "Se os documentos nao apresentarem outra acao segura e concreta, responda "
        "exatamente NO_SECOND_SOLUTION. Nao invente procedimentos.\n\n"
        f"TENTATIVAS ANTERIORES:\n{tentativas}\n\n"
        f"SITUACAO ATUAL:\n{question}"
    )
    return send_message_to_ai(prompt, history).strip()