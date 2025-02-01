from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload
import streamlit as st

import os
import json


def get_secrets():
    """Secretsを取得"""
    try:
        print("Streamlit Cloud で実行しています")
        gcp_creds               = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
        google_genai_creds_info = service_account.Credentials.from_service_account_info(st.secrets["google_genai"])
    except:
        print("ローカル環境で実行しています")
        with open("./.local/credentials.json") as f:
            creds_info = json.load(f)
        gcp_creds_info = creds_info["gcp"]
        gcp_creds = service_account.Credentials.from_service_account_info(gcp_creds_info)

        google_genai_creds_info = creds_info["google_genai"]
    # google_genai_api_key = google_genai_creds_info["api_key"]
    google_genai_api_key = ""
    return gcp_creds, google_genai_api_key


def list_drive_files(drive_service):
    """Google Drive のファイル一覧を取得"""
    results = drive_service.files().list(pageSize=10, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files


def download_csv_file(drive_service, file_id, file_name, dir_path):
    """Google Driveからファイルをダウンロード"""
    request = drive_service.files().get_media(fileId=file_id)
    
    if os.path.isdir(dir_path) is False:
        os.mkdir(dir_path)
    file_path = os.path.join(dir_path, file_name)
    with open(file_path, "wb") as f:
        downloader = MediaIoBaseDownload(f, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            print(f"Download {int(status.progress() * 100)}%.")
    return file_path

