"""Autenticacao Supabase usada pela porta de entrada do chatbot."""

from __future__ import annotations

import os
from typing import Any

from config import SUPABASE_KEY, SUPABASE_URL

try:
    from supabase import create_client
except ImportError:  # Permite abrir a tela inicial antes de instalar dependencias.
    create_client = None


class SupabaseAuth:
    def __init__(self, session: dict | None = None) -> None:
        self.url = os.getenv("SUPABASE_URL", SUPABASE_URL)
        self.key = os.getenv("SUPABASE_KEY", os.getenv("SUPABASE_ANON_KEY", SUPABASE_KEY))
        self.client: Any = None
        self.error = ""
        if self.url and self.key and create_client:
            try:
                self.client = create_client(self.url, self.key)
                if session and session.get("access_token") and session.get("refresh_token"):
                    self.client.auth.set_session(
                        session["access_token"],
                        session["refresh_token"],
                    )
            except Exception as exc:
                self.error = f"Não foi possível iniciar o Supabase: {exc}"
        elif not create_client:
            self.error = "Instale a dependência supabase com: pip install -r requirements.txt"

    @property
    def configured(self) -> bool:
        return self.client is not None

    def sign_in(self, email: str, password: str) -> dict:
        if not self.client:
            return {"ok": False, "error": self.error or "Configure SUPABASE_URL e SUPABASE_KEY."}
        try:
            response = self.client.auth.sign_in_with_password(
                {"email": email.strip(), "password": password}
            )
            user = response.user
            if not user:
                return {"ok": False, "error": "O Supabase não retornou um usuário válido."}

            # Mescla os dados salvos da tabela perfis_usuario caso existam
            user_dict = _user_to_dict(user)
            db_profile = self.get_profile(str(user.id))
            if db_profile:
                user_dict["profile"].update(db_profile)

            return {"ok": True, "user": user_dict, "session": _session_to_dict(response.session)}
        except Exception as exc:
            return {"ok": False, "error": _friendly_error(exc)}

    def sign_up(self, name: str, email: str, password: str) -> dict:
        if not self.client:
            return {"ok": False, "error": self.error or "Configure SUPABASE_URL e SUPABASE_KEY."}
        try:
            response = self.client.auth.sign_up(
                {
                    "email": email.strip(),
                    "password": password,
                    "options": {"data": {"nome": name.strip()}},
                }
            )
            if not response.user:
                return {"ok": False, "error": "Não foi possível criar a conta."}

            # Cria a linha inicial na tabela perfis_usuario
            try:
                self.client.table("perfis_usuario").upsert({
                    "usuario_id": str(response.user.id),
                    "nome": name.strip()
                }).execute()
            except Exception:
                pass

            return {"ok": True, "user": _user_to_dict(response.user), "session": _session_to_dict(response.session)}
        except Exception as exc:
            return {"ok": False, "error": _friendly_error(exc)}

    def sign_out(self) -> None:
        if self.client:
            try:
                self.client.auth.sign_out()
            except Exception:
                pass

    def update_profile(self, user_id: str, profile: dict, name: str = "") -> dict:
        if not self.client:
            return {"ok": False, "error": self.error or "Configure SUPABASE_URL e SUPABASE_KEY."}
        try:
            metadata = {"perfil": profile}
            if name.strip():
                metadata["nome"] = name.strip()
            response = self.client.auth.update_user({"data": metadata})
            if not response.user or str(response.user.id) != str(user_id):
                return {"ok": False, "error": "Não foi possível atualizar o perfil da conta."}

            # Salva/Atualiza os dados pessoais diretamente na tabela perfis_usuario
            payload = {
                "usuario_id": str(user_id),
                "nome": name.strip() or response.user.user_metadata.get("nome", ""),
                "local_trabalho": profile.get("local_trabalho"),
                "andar": profile.get("andar"),
                "sala": profile.get("sala"),
                "horario_trabalho": profile.get("horario_trabalho"),
                "melhor_contato": profile.get("melhor_contato", "email"),
                "telefone": profile.get("telefone"),
            }
            # Remove campos vazios para preservar dados existentes
            payload = {k: v for k, v in payload.items() if v is not None}
            self.client.table("perfis_usuario").upsert(payload, on_conflict="usuario_id").execute()

            return {"ok": True, "profile": profile}
        except Exception as exc:
            return {"ok": False, "error": _friendly_error(exc)}

    def get_profile(self, user_id: str) -> dict:
        """Busca os dados do perfil armazenados na tabela perfis_usuario."""
        if not self.client:
            return {}
        try:
            res = self.client.table("perfis_usuario").select("*").eq("usuario_id", str(user_id)).execute()
            if res.data and len(res.data) > 0:
                return res.data[0]
        except Exception:
            pass
        return {}


def _user_to_dict(user: Any) -> dict:
    metadata = getattr(user, "user_metadata", {}) or {}
    return {
        "id": str(user.id),
        "email": user.email or "",
        "name": metadata.get("nome") or metadata.get("name") or (user.email or "Usuário").split("@")[0],
        "profile": metadata.get("perfil") or {},
    }


def _session_to_dict(session: Any) -> dict:
    if not session:
        return {}
    return {
        "access_token": getattr(session, "access_token", ""),
        "refresh_token": getattr(session, "refresh_token", ""),
    }


def _friendly_error(error: Exception) -> str:
    message = str(error)
    lowered = message.lower()
    if "invalid login credentials" in lowered:
        return "E-mail ou senha incorretos."
    if "user already registered" in lowered:
        return "Este e-mail já está cadastrado."
    if "email not confirmed" in lowered:
        return "Confirme seu e-mail antes de entrar."
    return message or "Não foi possível concluir a operação."


def get_auth(session: dict | None = None) -> SupabaseAuth:
    return SupabaseAuth(session=session)