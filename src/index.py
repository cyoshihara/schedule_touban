import streamlit as st
import firebase_admin
from firebase_admin import credentials, db
import polars as pl
import os
from dotenv import load_dotenv
import toml

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数からサービスアカウント情報を取得
service_account_info_str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_TOML')
if service_account_info_str is None:
    raise ValueError("GOOGLE_APPLICATION_CREDENTIALS_TOML environment variable not set")

# デバッグ用に環境変数の内容を表示
# st.write(f"Environment variable content: {service_account_info_str}")

# TOML形式の文字列を辞書に変換
service_account_info = toml.loads(service_account_info_str)

# Firebase Admin SDKの初期化
cred = credentials.Certificate(service_account_info['google_application_credentials'])
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://schedule-touban-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# Realtime Databaseからデータを取得
try:
    ref = db.reference('test-node')
    data = ref.get()
    if data:
        st.write("Data retrieved successfully")
    else:
        st.write("No data found")
except Exception as e:
    st.write(f"Error retrieving data: {e}")

# データをリストに変換
if data:
    data_list = [value for key, value in data.items()]
    # Polars DataFrameに変換
    df = pl.DataFrame(data_list)
    # データを表示
    st.write(df)

st.write("Hello, world!")