from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
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


    # -----------------------------------------------------------------------
    # アップロード/検索 API（バスケ スタッツ Drive 同期用に追加・既存メソッド不変）
    # -----------------------------------------------------------------------
    def find_file_in_folder(self, folder_id, file_name, supportsAllDrives=False):
        """指定フォルダ内の同名ファイルを検索し file_id を返す（無ければ None）。"""
        # name にシングルクォートが含まれてもクエリが壊れないようエスケープ。
        safe_name = file_name.replace("'", "\\'")
        query = (
            f"'{folder_id}' in parents and name='{safe_name}' and trashed=false"
        )
        kwargs = {
            "q": query,
            "fields": "files(id, name)",
            "pageSize": 10,
        }
        if supportsAllDrives:
            kwargs["supportsAllDrives"] = True
            kwargs["includeItemsFromAllDrives"] = True
        results = self.drive_service.files().list(**kwargs).execute()
        files = results.get("files", [])
        if not files:
            return None
        return files[0].get("id")


    def upload_new_file(
        self, folder_id, local_path, file_name=None, supportsAllDrives=False
    ):
        """ローカルファイルを新規作成（create）し、生成された file_id を返す。"""
        if file_name is None:
            file_name = os.path.basename(local_path)
        body = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(local_path, resumable=False)
        kwargs = {"body": body, "media_body": media, "fields": "id"}
        if supportsAllDrives:
            kwargs["supportsAllDrives"] = True
        created = self.drive_service.files().create(**kwargs).execute()
        return created.get("id")


    def update_file(self, file_id, local_path, supportsAllDrives=False):
        """既存ファイルの内容を更新（update）し、file_id を返す。"""
        media = MediaFileUpload(local_path, resumable=False)
        kwargs = {"fileId": file_id, "media_body": media, "fields": "id"}
        if supportsAllDrives:
            kwargs["supportsAllDrives"] = True
        updated = self.drive_service.files().update(**kwargs).execute()
        return updated.get("id")


    def upsert_file(
        self, folder_id, local_path, file_name=None, supportsAllDrives=False
    ):
        """同名ファイルがあれば update、無ければ create する。file_id を返す。"""
        if file_name is None:
            file_name = os.path.basename(local_path)
        file_id = self.find_file_in_folder(
            folder_id, file_name, supportsAllDrives=supportsAllDrives
        )
        if file_id is None:
            return self.upload_new_file(
                folder_id, local_path, file_name=file_name,
                supportsAllDrives=supportsAllDrives,
            )
        return self.update_file(
            file_id, local_path, supportsAllDrives=supportsAllDrives
        )


    def download_file_to(
        self, folder_id, file_name, dest_path, supportsAllDrives=False
    ):
        """フォルダ内の指定名ファイルを dest_path へ取得する。

        フォルダ内に該当ファイルが無ければ何もせず None を返す。
        取得した場合は dest_path を返す。
        """
        file_id = self.find_file_in_folder(
            folder_id, file_name, supportsAllDrives=supportsAllDrives
        )
        if file_id is None:
            return None

        request = self.drive_service.files().get_media(fileId=file_id)
        dest_dir = os.path.dirname(dest_path)
        if dest_dir and not os.path.isdir(dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
        with open(dest_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while done is False:
                _status, done = downloader.next_chunk()
        return dest_path
