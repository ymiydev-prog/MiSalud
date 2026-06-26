"""Google Sheets exporter — optional mobile view of MiSalud data.

Exports flat tables for easy viewing on mobile. SQLite remains the source of truth.
"""
import json
import logging
from pathlib import Path
from typing import Optional

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .config import GOOGLE_TOKEN_PATH

logger = logging.getLogger(__name__)

SPREADSHEET_TITLE = "MiSalud (vista móvil)"


class SheetsExporter:
    """Export flat views of SQLite data to Google Sheets."""

    def __init__(self):
        if not GOOGLE_TOKEN_PATH.exists():
            raise FileNotFoundError(f"Token not found: {GOOGLE_TOKEN_PATH}")

        with open(GOOGLE_TOKEN_PATH) as f:
            token_data = json.load(f)

        self.creds = Credentials.from_authorized_user_info(token_data)
        self.sheets = build("sheets", "v4", credentials=self.creds)
        self.drive = build("drive", "v3", credentials=self.creds)
        self.spreadsheet_id: Optional[str] = None
        self._init_spreadsheet()

    def _init_spreadsheet(self):
        """Find or create the export spreadsheet."""
        resp = self.drive.files().list(
            q=f"name='{SPREADSHEET_TITLE}' and mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
            fields="files(id)",
        ).execute()

        if files := resp.get("files", []):
            self.spreadsheet_id = files[0]["id"]
        else:
            ss = self.sheets.spreadsheets().create(
                body={"properties": {"title": SPREADSHEET_TITLE}}
            ).execute()
            self.spreadsheet_id = ss["spreadsheetId"]

        # Ensure tabs
        self._ensure_sheets(["Comidas", "Peso", "Google_Fit"])

    def _ensure_sheets(self, names: list[str]):
        """Create missing sheet tabs."""
        meta = self.sheets.spreadsheets().get(
            spreadsheetId=self.spreadsheet_id, fields="sheets.properties.title"
        ).execute()
        existing = {s["properties"]["title"] for s in meta.get("sheets", [])}

        for name in names:
            if name not in existing:
                self.sheets.spreadsheets().batchUpdate(
                    spreadsheetId=self.spreadsheet_id,
                    body={"requests": [{"addSheet": {"properties": {"title": name}}}]},
                ).execute()

        # Delete default Sheet1
        if "Sheet1" in existing and len(existing) > len(names):
            for s in meta["sheets"]:
                if s["properties"]["title"] == "Sheet1":
                    self.sheets.spreadsheets().batchUpdate(
                        spreadsheetId=self.spreadsheet_id,
                        body={"requests": [{"deleteSheet": {"sheetId": s["properties"]["sheetId"]}}]},
                    ).execute()

    def export_meals(self, rows: list[list]):
        """Export meals with headers."""
        headers = [["Fecha", "Hora", "Tipo", "Alimento", "Porción_g", "Calorías", "Proteínas_g", "Carbos_g", "Grasas_g", "Confianza", "Notas"]]
        self._write_sheet("Comidas", headers + rows)

    def export_weight(self, rows: list[list]):
        headers = [["Fecha", "Peso_kg", "BF_pct"]]
        self._write_sheet("Peso", headers + rows)

    def export_fit(self, rows: list[list]):
        headers = [["Fecha", "Pasos", "Sueño_h", "Calorías_activas", "Min_activos", "Peso_kg"]]
        self._write_sheet("Google_Fit", headers + rows)

    def _write_sheet(self, sheet_name: str, values: list[list]):
        """Clear and write a sheet."""
        # Clear everything
        self.sheets.spreadsheets().values().clear(
            spreadsheetId=self.spreadsheet_id,
            range=f"{sheet_name}!A:Z",
        ).execute()

        if values:
            self.sheets.spreadsheets().values().update(
                spreadsheetId=self.spreadsheet_id,
                range=f"{sheet_name}!A1",
                body={"values": values},
                valueInputOption="USER_ENTERED",
            ).execute()

    @property
    def url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.spreadsheet_id}"
