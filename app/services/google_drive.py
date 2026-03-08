from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import io
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_ACCOUNT_FILE = os.path.join(BASE_DIR, "service_account.json")
SCOPES = ["https://www.googleapis.com/auth/drive"]

# Lazy-loaded so the app can start without credentials (e.g. on Railway without the file).
_credentials = None
_drive_service = None


def _get_drive_service():
    """Load credentials from file or GOOGLE_SERVICE_ACCOUNT_JSON env, then build Drive service."""
    global _credentials, _drive_service
    if _drive_service is not None:
        return _drive_service
    # Prefer env var (safe for Railway: set GOOGLE_SERVICE_ACCOUNT_JSON to the JSON string).
    json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if json_str:
        info = json.loads(json_str)
        _credentials = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    elif os.path.isfile(SERVICE_ACCOUNT_FILE):
        _credentials = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
    else:
        raise FileNotFoundError(
            "Google Drive credentials not found. Set GOOGLE_SERVICE_ACCOUNT_JSON env var "
            "or place service_account.json in app/services/"
        )
    _drive_service = build("drive", "v3", credentials=_credentials)
    return _drive_service


def upload_file_to_drive(file, filename, folder_id):
    """
    file      = file ที่ได้จาก FastAPI
    filename  = ชื่อไฟล์
    folder_id = Google Drive Folder ID
    """

    file_metadata = {
        "name": filename,
        "parents": [folder_id]
    }

    media = MediaIoBaseUpload(
        io.BytesIO(file),
        mimetype="application/octet-stream",
        resumable=True
    )

    drive_service = _get_drive_service()
    uploaded_file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()

    file_id = uploaded_file.get("id")

    return f"https://drive.google.com/file/d/{file_id}/view"
