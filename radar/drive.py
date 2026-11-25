"""Google Drive (Shared Drive) через сервисный аккаунт.

Сервисный аккаунт нужно добавить в Shared Drive с ролью «Менеджер контента».
Ключ JSON передаётся в переменной GOOGLE_SERVICE_ACCOUNT_JSON (сам JSON или base64 от него).
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/drive"]
FOLDER = "application/vnd.google-apps.folder"


class Drive:
    def __init__(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        raw = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
        if not raw:
            raise SystemExit("GOOGLE_SERVICE_ACCOUNT_JSON не задан")
        if not raw.startswith("{"):
            raw = base64.b64decode(raw).decode()
        creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=SCOPES)
        self.svc = build("drive", "v3", credentials=creds, cache_discovery=False)

    def _find(self, name: str, parent: str, mime: str | None = None) -> str | None:
        q = f"name = '{name.replace(chr(39), chr(92) + chr(39))}' and '{parent}' in parents and trashed = false"
        if mime:
            q += f" and mimeType = '{mime}'"
        res = self.svc.files().list(q=q, fields="files(id)", supportsAllDrives=True,
                                    includeItemsFromAllDrives=True, corpora="allDrives").execute()
        files = res.get("files", [])
        return files[0]["id"] if files else None

    def folder(self, name: str, parent: str) -> str:
        fid = self._find(name, parent, FOLDER)
        if fid:
            return fid
        meta = {"name": name, "mimeType": FOLDER, "parents": [parent]}
        return self.svc.files().create(body=meta, fields="id", supportsAllDrives=True).execute()["id"]

    def upload(self, path: Path, parent: str, name: str | None = None,
               convert_to: str | None = None, mime: str | None = None) -> dict:
        """Загружает файл (перезаписывает одноимённый). convert_to — Google-тип (Docs/Sheets)."""
        from googleapiclient.http import MediaFileUpload

        name = name or path.name
        mime = mime or mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        media = MediaFileUpload(str(path), mimetype=mime, resumable=path.stat().st_size > 5 * 2**20)
        existing = self._find(name, parent, convert_to)
        fields = "id, webViewLink"
        if existing:
            return self.svc.files().update(fileId=existing, media_body=media, fields=fields,
                                           supportsAllDrives=True).execute()
        meta = {"name": name, "parents": [parent]}
        if convert_to:
            meta["mimeType"] = convert_to
        return self.svc.files().create(body=meta, media_body=media, fields=fields,
                                       supportsAllDrives=True).execute()

    def link(self, file_id: str) -> str:
        return self.svc.files().get(fileId=file_id, fields="webViewLink",
                                    supportsAllDrives=True).execute()["webViewLink"]


DOC = "application/vnd.google-apps.document"
SHEET = "application/vnd.google-apps.spreadsheet"
