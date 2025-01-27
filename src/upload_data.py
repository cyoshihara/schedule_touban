import firebase_admin
from firebase_admin import credentials, db
from dotenv import load_dotenv
import pandas as pd
import toml
import os


# Firebaseプロジェクトのサービスアカウントキー（JSONファイル）を指定

# .envファイルから環境変数を読み込む
load_dotenv()

# 環境変数からサービスアカウント情報を取得
service_account_info_str = os.getenv('GOOGLE_APPLICATION_CREDENTIALS_TOML')
service_account_info = toml.loads(service_account_info_str)

# Firebase Admin SDKの初期化
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://schedule-touban-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

# CSVファイルを読み込む
csv_file = "./data/input.csv"  # CSVファイルのパス
data = pd.read_csv(csv_file)

# Firebase Realtime Databaseにデータをアップロード
ref = db.reference("test-node")  # 保存するノード名を指定

# CSVの各行をFirebaseに挿入
for index, row in data.iterrows():
    ref.push(row.to_dict())  # 行を辞書形式で挿入

print("データをアップロードしました！")
