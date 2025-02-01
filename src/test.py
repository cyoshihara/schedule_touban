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
    with open("schedule-touban-449606-d7f8e2568452.json") as f:
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

# if st.button("ファイル一覧を取得"):
files = list_drive_files()
if files:
    for file in files:
        print(f"📄 {file['name']} (ID: {file['id']})")
else:
    print("ファイルが見つかりませんでした")


# # import streamlit as st
# import polars as pl
# import os
# from dotenv import load_dotenv
# import toml
# from dotenv import load_dotenv
# from supabase import create_client, Client


# # # ローカル環境かStreamlit Cloudかを判定
# # if os.getenv('STREAMLIT_ENV') == 'cloud':
# #     # Streamlit Cloudの場合、secretsから読み込む
# #     supabase_url = st.secrets["SUPABASE_URL"]
# #     supabase_key = st.secrets["SUPABASE_KEY"]
# # else:
# #     # ローカル環境の場合、.envファイルから読み込む
# load_dotenv()
# supabase_url = os.getenv("SUPABASE_URL")
# supabase_key = os.getenv("SUPABASE_KEY")
# if not supabase_url or not supabase_key:
#     raise ValueError("SUPABASE_URL or SUPABASE_KEY environment variable not set")

# # Supabaseの接続
# def get_supabase_client() -> Client:
#     return create_client(supabase_url, supabase_key)

# try:
#     supabase: Client = create_client(supabase_url, supabase_key)
# except Exception as e:
#     print("クライアントの作成に失敗しました:", e)
#     exit(1)

# def insert_data():
#     response = None  # スコープ全体で使えるように初期化
#     try:
#         data = {"column1": "value1", "column2": "value2"}  # 挿入するデータ
#         print("データ挿入リクエスト送信中...")
#         response = supabase.table("your_table_name").insert(data).execute()

#         if response.status_code >= 400 or response.error:
#             raise Exception(f"APIエラー: {response.error or response.raw_response}")
        
#         # レスポンスのデバッグ
#         print("レスポンスのステータスコード:", response.status_code)
#         print("レスポンスのデータ:", response.data)
#         print("レスポンスのエラー:", response.error)
#         print("データの挿入成功:", response.data)

#     except Exception as e:
#         print("エラーが発生しました:", str(e))
#         if response:  # response が None でない場合のみデバッグ出力
#             print("デバッグ用レスポンス:", response.raw_response)
#         else:
#             print("レスポンスがありません（クエリが失敗しました）")

# insert_data()
# # # テーブルの存在を確認する関数
# # def check_table_exists(table_name: str) -> bool:
# #     try:
# #         # テーブルから1件取得するクエリ
# #         response = supabase.table(table_name).select("*").execute()
        
# #         # レスポンスの内容を直接参照
# #         if response.data:
# #             return True  # データが取得できた場合、テーブルは存在する
# #         return False  # データが空の場合、テーブルは存在しない
# #     except Exception as e:
# #         raise Exception(f"Error checking table existence: {str(e)}")

# # # テーブルの存在を確認
# # table_name = 'sample'
# # try:
# #     if check_table_exists(table_name):
# #         print(f"Table '{table_name}' exists in Supabase")
# #     else:
# #         print(f"Table '{table_name}' does not exist in Supabase")
# # except Exception as e:
# #     print(f"Error: {e}")