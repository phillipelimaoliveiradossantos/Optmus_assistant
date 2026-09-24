"""
config.py
---------
Configuração centralizada do projeto.
"""

import os

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://bpwuzilnxndpnwypqbwt.supabase.co",
)
# Use somente a chave pública anon neste frontend. Nunca use service_role.
SUPABASE_KEY = os.getenv(
    "SUPABASE_KEY",
    os.getenv("SUPABASE_ANON_KEY", "sb_publishable_QzV0OLo_znY3g9thDP6Icw_vvSRqL_8"),
)

# Configurações de endpoints genéricos (caso utilize outro backend além do Gemini)
API_ENDPOINTS = {
    "db": {
        "url": os.getenv("DB_API_URL", ""),
        "api_key": os.getenv("DB_API_KEY", ""),
        "auth_header": "Authorization",
        "auth_scheme": "Bearer ",
    },
}

REQUEST_TIMEOUT = 60  # segundos