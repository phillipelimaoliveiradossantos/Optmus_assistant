# Front-end do Chatbot (Streamlit)

Front-end pronto para ser conectado ao backend de IA que já existe.

## Estrutura

```
chat_frontend/
├── app.py             # aplicação principal (UI, chat, histórico)
├── api_client.py      # camada genérica de chamadas às APIs
├── config.py          # ÚNICO arquivo onde você cadastra as APIs (IA, banco, outras)
├── knowledge_base.py   # busca dos trechos relevantes nos documentos
├── documents/          # coloque aqui os documentos usados como base pela IA
├── assets/
│   └── background.jpg # coloque aqui a sua imagem de fundo
├── requirements.txt
└── README.md
```

## Autenticação com Supabase

A tela inicial usa o Supabase Auth para login e cadastro. Não coloque a
`service_role key` no frontend: use somente a chave pública `anon`.

1. No Supabase, abra **Project Settings > API** e copie a URL e a chave `anon`.
2. Configure as variáveis antes de iniciar o Streamlit:

```powershell
$env:SUPABASE_URL = "https://seu-projeto.supabase.co"
$env:SUPABASE_KEY = "sua-chave-anon"
streamlit run app.py
```

3. Em **Authentication > Providers > Email**, habilite e-mail/senha.
4. Se quiser sincronizar o histórico na nuvem, crie uma tabela `historico_conversas`
   com `usuario_id uuid references auth.users(id)`, `papel text`, `mensagem text`
   e `criado_em timestamptz default now()`, além de uma política RLS que permita
   ao usuário acessar apenas as próprias linhas.

Enquanto a integração de persistência remota do histórico não for ativada, o
app salva as conversas localmente em `%LOCALAPPDATA%\OptimusTruck\users\<uuid>.json`.
O UUID já é o mesmo retornado pelo Supabase Auth, então a migração pode ser feita
sem alterar a interface.

## Como rodar

**Opção mais fácil (Windows):** dê duplo clique no arquivo `iniciar.bat`.
Ele instala o que faltar e já abre o app no navegador. Da próxima vez,
é só dar duplo clique de novo — não precisa instalar nada outra vez.

**Opção mais fácil (Mac/Linux):** no terminal, dentro da pasta, rode uma
vez `chmod +x iniciar.sh` (só na primeira vez, para dar permissão), depois
pode dar duplo clique em `iniciar.sh` ou rodar `./iniciar.sh`.

**Manual (qualquer sistema):**
```bash
pip install -r requirements.txt
streamlit run app.py
```
A instalação (`pip install`) só precisa ser feita uma vez. Nas próximas
vezes, só `streamlit run app.py` já é suficiente.

A aplicação abre em `http://localhost:8501`.

## Escalonamento para o Help Desk

Quando o usuário informa que uma orientação não resolveu, a IA consulta a
base novamente e tenta indicar uma etapa diferente. Se não houver outra
orientação segura no material, o chat coleta nome, ID ou patrimônio da
máquina, localização, contato e descrição do problema.

Depois da coleta, os dados são salvos automaticamente como um arquivo `.txt`
na pasta `tickets/`. O usuário é orientado a abrir o ticket com o Help Desk.

## Base de conhecimento da IA

Coloque os documentos que a IA deve consultar dentro da pasta `documents/`.
São aceitos arquivos `.txt`, `.md`, `.csv`, `.json`, `.pdf` e `.docx`.

Antes de cada resposta, o sistema procura nos documentos os trechos que têm
mais palavras em comum com a pergunta e envia somente os trechos relevantes
ao Gemini. Se nenhum trecho for encontrado, a IA é instruída a deixar isso
claro em vez de inventar uma resposta baseada na base local.

Depois de adicionar ou alterar documentos, basta fazer a próxima pergunta no
chat; não é necessário cadastrar os nomes dos arquivos no código.

## Conectar aos backends (IA, banco de dados, e outras que aparecerem)

Como você ainda não sabe todas as APIs que vai ter (sabe que terá a da IA e
provavelmente uma de banco de dados, mas pode surgir mais), a configuração
foi feita de forma centralizada em **`config.py`** — é o único lugar que
você precisa editar quando uma nova API aparecer.

1. **Cadastre a API em `config.py`**, dentro do dicionário `API_ENDPOINTS`.
   Já vem com dois exemplos prontos: `"ai"` (a IA do chat) e `"db"` (banco
   de dados). Para cada uma, defina:
   - `url` — endereço do endpoint (pode usar variável de ambiente, ex:
     `export AI_API_URL="https://seu-backend.com/chat"`)
   - `api_key` — se precisar de autenticação
   - `auth_header` / `auth_scheme` — como o token é enviado no header

2. **Se surgir uma terceira API**, copie o bloco de exemplo comentado em
   `config.py` (`"outra_api": {...}`), preencha e dê o nome que quiser.
   Não precisa mudar mais nada.

3. **Para chamar qualquer API cadastrada**, use a função genérica em
   `api_client.py`:
   ```python
   from api_client import call_api
   resultado = call_api("db", {"query": "algo"})
   ```
   Ela já trata erro de conexão, timeout, HTTP e retorna
   `{"ok": True, "data": ...}` ou `{"ok": False, "error": "..."}`.

4. **A API da IA do chat já está conectada** através da função
   `send_message_to_ai(pergunta, historico)`, usada em `app.py`. Só falta
   você ajustar em `api_client.py` (trecho marcado `AJUSTE AQUI`) qual
   campo do JSON de resposta contém o texto (`answer`, `response`,
   `message`, etc — já tenta os mais comuns automaticamente).

Nenhuma outra parte do front-end precisa ser tocada.

## Imagem de fundo desfocada

Basta colocar **qualquer arquivo de imagem** (`.jpg`, `.jpeg`, `.png` ou
`.webp`, qualquer nome) dentro da pasta `assets/`. O código detecta
automaticamente o primeiro arquivo de imagem que encontrar ali — não
precisa se chamar `background.jpg`. A imagem aparece desfocada cobrindo a
tela toda; como o menu lateral é uma camada por cima, ao abrir ele
naturalmente cobre parte da imagem — isso é esperado.

A imagem é automaticamente redimensionada e comprimida antes de ser usada
(já que ela fica desfocada, não precisa da resolução original — isso
também evita que o app fique lento com fotos grandes, como uma de
1920x1080).

Se nenhuma imagem for encontrada, ou se o arquivo não puder ser aberto
(corrompido, formato não suportado, etc.), a aplicação roda normalmente e
mostra um aviso dizendo o que foi encontrado na pasta.

## Menu lateral (hambúrguer)

O menu começa **recolhido**. Para abrir, clique no ícone **☰** no canto
superior esquerdo da tela (esse ícone já vem nativo do Streamlit). Clicando
de novo, ele fecha. Assim a tela fica limpa e o menu só aparece quando o
usuário quiser ver o histórico.

## Título do histórico (resumo do objetivo)

O título de cada conversa é gerado automaticamente a partir da PRIMEIRA
mensagem, removendo saudações e frases de preenchimento (ex: "olá", "tudo
bem", "estou aqui para", "gostaria de", "por favor", etc.) para deixar só
o objetivo real do usuário.

Exemplo:
```
"ola tudo bem? estou aqui para fazer o reset de senha"  →  "Reset de senha"
```

Isso é feito localmente por regras (função `gerar_titulo()` em `app.py`),
sem precisar chamar a IA — então não gera custo extra de API. Se quiser
ajustar as frases removidas ou adicionar novas, edite a lista
`_TITULO_PADROES` no topo do arquivo `app.py`.

## Histórico / Menu lateral

- Cada conversa vira um item no menu lateral.
- O título do item é gerado automaticamente com base na primeira pergunta
  feita naquela conversa (truncado se for muito longo).
- Botão "➕ Nova conversa" cria uma conversa em branco.
- Clicar em um item do histórico volta para aquela conversa (mensagens ficam
  guardadas em memória durante a sessão do navegador).

> Observação: o histórico é carregado na sessão do Streamlit e também salvo
> localmente em arquivo, para continuar disponível entre reinicializações.

### Histórico local por máquina

As conversas agora também são salvas localmente em
`%LOCALAPPDATA%\OptimusTruck\chat_history.json`. Assim, o histórico continua
disponível depois de fechar o navegador ou o terminal e não é sincronizado
com outras máquinas pelo OneDrive.
