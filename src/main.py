import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

# ローカル or Streamlit Cloud の判定
try:
    print("Streamlit Cloud で実行しています")
    creds = service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
except:
    print("ローカル環境で実行しています")
    with open("credentials.json") as f:
        creds_info = json.load(f)
    creds = service_account.Credentials.from_service_account_info(creds_info)

# Google Drive API クライアントを作成
drive_service = build("drive", "v3", credentials=creds)

# Google Drive のファイル一覧を取得
def list_drive_files():
    results = drive_service.files().list(pageSize=10, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files

print("📂 Google Drive API テスト")

if st.button("ファイル一覧を取得"):
    files = list_drive_files()
    if files:
        for file in files:
            st.write(f"📄 {file['name']} (ID: {file['id']})")
    else:
        st.write("ファイルが見つかりませんでした")