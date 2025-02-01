from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import streamlit as st

import os
import json
from datetime import datetime

import const


def get_current_fiscal_year():
    today = datetime.today()
    # 4月1日より前の場合は前年を年度の開始年とする
    if today.month < 4:
        fiscal_year_start = today.year - 1
    else:
        fiscal_year_start = today.year
    return fiscal_year_start


def get_secrets():
    """Secretsを取得"""
    try:
        gcp_creds               = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
        google_genai_creds_info = st.secrets["google_genai"]
        print("Streamlit Cloud で実行しています")
    except:
        print("ローカル環境で実行しています")
        with open("./.local/credentials.json") as f:
            creds_info = json.load(f)
        gcp_creds_info = creds_info["gcp"]
        gcp_creds = service_account.Credentials.from_service_account_info(gcp_creds_info)
        google_genai_creds_info = creds_info["google_genai"]

    google_genai_api_key = google_genai_creds_info["api_key"]
    return gcp_creds, google_genai_api_key


class GoogleDriveService:
    """GoogleDriveへの各種アクセス"""

    def __init__(self, credentials, data_dir = const.DIR_TEMP):
        """コンストラクタ"""
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.data_dir = data_dir

        if os.path.isdir(self.data_dir) is False:
            os.mkdir(self.data_dir)


    def list_drive_files(self, pageSize=10):
        """Google Drive のファイル一覧を取得"""
        results = self.drive_service.files().list(
            pageSize=pageSize,
            fields="files(id, name)"
            ).execute()
        files = results.get("files", [])
        return files


    def get_file_name(self, file_id):
        """ファイル名を取得"""
        file_metadata = self.drive_service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata.get('name')
        return file_name


    def download_file(self, file_id):
        """Google Driveからファイルをダウンロード"""
        request = self.drive_service.files().get_media(fileId=file_id)
        
        if os.path.isdir(const.DIR_TEMP) is False:
            os.mkdir(self.data_dir)
        fname = self.get_file_name(file_id)
        file_path = os.path.join(self.data_dir, fname)

        print(f"Downloading file: {fname}")
        with open(file_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                progress = int(status.progress() * 100)
                print(f"Download {progress}%.")
                # yield progress, done
        return file_path
