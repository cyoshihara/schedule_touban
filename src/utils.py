from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import streamlit as st

import os
import json
import shutil

import const


def get_secrets():
    """Secretsを取得"""
    try:
        print("Streamlit Cloud で実行しています")
        gcp_creds               = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
        google_genai_creds_info = st.secrets["google_genai"]
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

    def __init__(self, credentials, data_dir = const.DIR_TEMP, is_clear_data_dir_when_app_close=True):
        """コンストラクタ"""
        self.drive_service = build("drive", "v3", credentials=credentials)
        self.data_dir = data_dir

        if os.path.isdir(self.data_dir) is False:
            os.mkdir(self.data_dir)


    def __del__(self):
        """デストラクタ"""
        try:
            if self.is_clear_data_dir_when_app_close and os.path.exists(self.data_dir):
                shutil.rmtree(self.data_dir)
                print(f"Cleaned up temporary directory: {self.data_dir}")
            # ファイルの更新もしたい！！！
        except Exception as e:
            print(f"Error during cleanup: {e}")


    @property
    def is_clear_data_dir_when_app_close(self) -> bool:
        """アプリ終了時に一時ファイルを削除するかどうかのフラグ"""
        return self._is_clear_data_dir_when_app_close


    @is_clear_data_dir_when_app_close.setter
    def is_clear_data_dir_when_app_close(self, value: bool) -> None:
        if not isinstance(value, bool):
            raise ValueError("is_clear_data_dir_when_app_close must be a boolean")
        self._is_clear_data_dir_when_app_close = value


    def list_drive_files(self):
        """Google Drive のファイル一覧を取得"""
        results = self.drive_service.files().list(
            pageSize=10,
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
