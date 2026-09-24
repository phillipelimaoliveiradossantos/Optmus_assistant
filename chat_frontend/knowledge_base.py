"""Busca local de trechos relevantes nos documentos da aplicacao."""

import csv
from difflib import SequenceMatcher
import io
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree


DOCUMENTS_DIR = Path(__file__).parent / "documents"
SUPPORTED_TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json"}
MAX_DOCUMENT_CHARS = 120_000
MAX_CONTEXT_CHARS = 12_000
CHUNK_SIZE = 1_200
CHUNK_OVERLAP = 200


def _read_document(path: Path) -> str:
    if path.suffix.lower() in SUPPORTED_TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8", errors="ignore")

    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if path.suffix.lower() == ".docx":
        try:
            from docx import Document
        except ImportError:
            # DOCX is a ZIP package; keep the knowledge base usable when the
            # optional python-docx dependency is unavailable.
            try:
                with zipfile.ZipFile(path) as arquivo_zip:
                    xml = arquivo_zip.read("word/document.xml")
                raiz = ElementTree.fromstring(xml)
                namespaces = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragrafos = []
                for paragrafo in raiz.findall(".//w:p", namespaces):
                    textos = [no.text or "" for no in paragrafo.findall(".//w:t", namespaces)]
                    paragrafos.append("".join(textos))
                return "\n".join(paragrafos)
            except (KeyError, OSError, ElementTree.ParseError):
                return ""
        document = Document(str(path))
        return "\n".join(paragraph.text for paragraph in document.paragraphs)

    return ""


def _normalizar(texto: str) -> list[str]:
    return re.findall(r"[\wÀ-ÿ]+", texto.lower())


def _tem_termo_aproximado(termos: set[str], alvo: str) -> bool:
    return any(
        termo == alvo or SequenceMatcher(None, termo, alvo).ratio() >= 0.78
        for termo in termos
    )


def _formatar_texto(path: Path, texto: str) -> str:
    if path.suffix.lower() == ".json":
        try:
            return json.dumps(json.loads(texto), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return texto

    if path.suffix.lower() == ".csv":
        try:
            rows = csv.reader(io.StringIO(texto))
            return "\n".join(" | ".join(row) for row in rows)
        except csv.Error:
            return texto

    return texto


def _chunks(texto: str) -> list[str]:
    texto = texto.strip()[:MAX_DOCUMENT_CHARS]
    if not texto:
        return []

    resultado = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + CHUNK_SIZE, len(texto))
        trecho = texto[inicio:fim].strip()
        if trecho:
            resultado.append(trecho)
        if fim == len(texto):
            break
        inicio = fim - CHUNK_OVERLAP
    return resultado


def buscar_contexto(pergunta: str) -> str:
    """Retorna os trechos mais relacionados à pergunta, ou texto vazio."""
    if not DOCUMENTS_DIR.exists():
        return ""

    termos = set(_normalizar(pergunta))
    termos = {termo for termo in termos if len(termo) > 2}
    candidatos = []
    todos_os_trechos = []

    for path in sorted(DOCUMENTS_DIR.rglob("*")):
        if not path.is_file():
            continue
        try:
            texto = _formatar_texto(path, _read_document(path))
        except (OSError, ValueError):
            continue

        for trecho in _chunks(texto):
            palavras = set(_normalizar(trecho))
            pontuacao = len(termos & palavras)
            todos_os_trechos.append((pontuacao, path.name, trecho))
            if pontuacao:
                candidatos.append((pontuacao, path.name, trecho))

    # Preserve a melhor correspondencia mesmo quando ha apenas uma palavra
    # compartilhada, evitando poluir o prompt com documentos sem relacao.
    if not candidatos:
        candidatos = todos_os_trechos

    candidatos.sort(key=lambda item: item[0], reverse=True)
    partes = []
    total = 0
    for _, nome, trecho in candidatos:
        parte = f"[Documento: {nome}]\n{trecho}"
        if total + len(parte) > MAX_CONTEXT_CHARS:
            break
        partes.append(parte)
        total += len(parte)

    return "\n\n".join(partes)


def buscar_resposta_local(pergunta: str) -> str | None:
    """Retorna uma orientação segura para consultas críticas conhecidas."""
    termos = set(_normalizar(pergunta))
    termos_senha = {"senha", "password"}
    termos_reset = {"reset", "redefinir", "redefinicao", "esqueci", "expirada"}
    if (_tem_termo_aproximado(termos, "senha") and
            any(_tem_termo_aproximado(termos, termo) for termo in termos_reset)):
        contexto = buscar_contexto(pergunta)
        if "Reset de Senha CD" not in contexto:
            return None

        return (
            "Para redefinir sua senha CD (Intranet/WiW), acesse o CMT: Password: "
            "https://login.mercedes-benz.com/password/cd\n\n"
            "- Se você sabe a senha atual ou ela expirou, selecione **Modificar (Modify)**.\n"
            "- Se não sabe a senha atual, mas consegue acessar seu e-mail, selecione "
            "**Redefinir (Reset)**.\n"
            "- Se não consegue redefinir sozinho, peça a um supervisor para usar a opção "
            "**Terceira Pessoa (Third person)**.\n\n"
            "A redefinição deve ser concluída em até dez minutos. A nova senha deve ter "
            "10 a 25 caracteres, com letra maiúscula, minúscula, número e caractere "
            "especial. Consulte o manual em "
            "https://login.mercedes-benz.com/password/cd/guide?continue"
        )

    contexto = buscar_contexto(pergunta)
    contexto_normalizado = contexto.lower()
    pergunta_normalizada = " ".join(termos)
    pergunta_sobre_pdf = (
        any(_tem_termo_aproximado(termos, termo) for termo in ("pdf", "pdfsam"))
        and "pdfsam" in contexto_normalizado
    )
    if pergunta_sobre_pdf:
        return (
            "Sim. O PDFsam Basic é o aplicativo indicado para trabalhar com PDFs. "
            "Ele permite fundir, dividir, misturar, girar e extrair páginas de PDFs.\n\n"
            "Para instalar, solicite **ANDREA VACONDIO PDFSAM BASIC 5.3.0.0 ENU WIN11 "
            "(30005942)** no IT Shop. A instalação é automática; se não ocorrer, "
            "use o Portal da Empresa. Mais informações: "
            "https://pdfsam.org/pt/pdfsam-basic/"
        )

    pergunta_sobre_mocha = "mocha" in termos and any(
        palavra in contexto_normalizado
        for palavra in ("instalação", "instalacao", "installation", "portal da empresa")
    )
    if not pergunta_sobre_mocha:
        return None

    return (
        "O Mocha já vem instalado por padrão e não tem custo de licença para "
        "usuários da MBBras. Para instalar ou reinstalar, faça a solicitação pelo "
        "Portal da Empresa.\n\n"
        "Se a instalação apresentar erro, guarde as informações e imagens do erro "
        "e encaminhe o atendimento ao suporte Onsite da sua localidade."
    )