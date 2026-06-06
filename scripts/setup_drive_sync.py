"""バスケ スタッツアプリの Google Drive 同期セットアップ補助スクリプト。

あなたの PC で次の 1 コマンドを実行するだけで、面倒な設定を肩代わりします。

    python scripts/setup_drive_sync.py

やること:
  1. ./.local/credentials.json に `gdrive` 設定（folder_id）を自動で書き込む。
  2. 共有先となる「サービスアカウントのメールアドレス」を画面に表示する。
  3. Drive フォルダへ実際に接続できるか／3 つの CSV を保存できるかをテストし、
     結果と「次にやること」を日本語で表示する。

フォルダ ID は既定で下記。別フォルダにしたい場合は引数で渡す:
    python scripts/setup_drive_sync.py <folder_id>
"""

import json
import os
import sys

# 既定の同期先フォルダ（ユーザー指定）。
DEFAULT_FOLDER_ID = "1RWx3b2IRH6D2SzIp6OGmwVxCPhzraxKi"

# src/ を import パスに追加（stats_sync / utils / stats_const を使う）。
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "src")
sys.path.insert(0, _SRC)

CREDS_PATH = "./.local/credentials.json"


def _fail(msg):
    print("\n[NG] " + msg)
    sys.exit(1)


def main():
    folder_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_FOLDER_ID

    print("=" * 60)
    print(" バスケ スタッツ: Google Drive 同期セットアップ")
    print("=" * 60)
    print(f"対象フォルダ ID: {folder_id}")

    # --- 1. credentials.json を読み、gdrive 設定を書き込む ---
    if not os.path.isfile(CREDS_PATH):
        _fail(
            f"{CREDS_PATH} が見つかりません。\n"
            "    当番アプリで使っている認証ファイルを ./.local/credentials.json に"
            "置いてから、もう一度実行してください。"
        )

    with open(CREDS_PATH, encoding="utf-8") as f:
        creds_info = json.load(f)

    if "gcp" not in creds_info:
        _fail(
            f"{CREDS_PATH} に \"gcp\"（サービスアカウント情報）がありません。\n"
            "    当番アプリ用の gcp セクションが入った認証ファイルが必要です。"
        )

    creds_info["gdrive"] = {"enabled": True, "stats_folder_id": folder_id}
    with open(CREDS_PATH, "w", encoding="utf-8") as f:
        json.dump(creds_info, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] {CREDS_PATH} に gdrive 設定を書き込みました。")

    sa_email = creds_info["gcp"].get("client_email", "(client_email 不明)")
    print("\n――― 共有してほしいメールアドレス（サービスアカウント）―――")
    print(f"    {sa_email}")
    print("  ↑ Google Drive で対象フォルダを開き、このメールアドレスを")
    print("    『編集者』として共有してください（まだの場合）。")

    # --- 2. 実際に接続テスト ---
    import stats_const as sc
    import stats_sync as sync
    from utils import GoogleDriveService

    print("\n[..] Drive へ接続テスト中...")
    try:
        creds = sync._load_creds_from_info(creds_info["gcp"])
        drive = GoogleDriveService(creds, data_dir=sc.DIR_TEMP)
        # フォルダ内ファイル一覧でアクセス可否を確認。
        for name in sync.SYNC_FILES:
            drive.find_file_in_folder(folder_id, name)
        print("[OK] フォルダにアクセスできました。")
    except Exception as e:
        msg = str(e)
        if "404" in msg or "notFound" in msg:
            _fail(
                "フォルダが見つからないか、まだ共有されていません。\n"
                f"    上のメールアドレス（{sa_email}）にフォルダを『編集者』で\n"
                "    共有してから、もう一度このコマンドを実行してください。"
            )
        if "403" in msg or "insufficient" in msg.lower():
            _fail(
                "アクセス権がありません（共有がまだ／権限不足）。\n"
                f"    フォルダを {sa_email} に『編集者』で共有してから再実行してください。"
            )
        _fail("接続でエラーが発生しました:\n    " + msg)

    # --- 3. 保存（アップロード）テスト ---
    print("\n[..] CSV の保存テスト中...")
    os.makedirs(sc.DIR_TEMP, exist_ok=True)
    test_name = sc.CsvFile.event
    local_path = os.path.join(sc.DIR_TEMP, test_name)
    if not os.path.isfile(local_path):
        # まだデータが無ければ、ヘッダだけの空ファイルでテストする。
        with open(local_path, "w", encoding="utf-8") as f:
            f.write("")
    try:
        drive.upsert_file(folder_id, local_path, file_name=test_name)
        print(f"[OK] {test_name} を Drive に保存できました。")
    except Exception as e:
        msg = str(e)
        if "storageQuota" in msg or "quota" in msg.lower():
            print(
                "\n[注意] サービスアカウントによる新規作成が容量制限で失敗しました。\n"
                "  （個人 Gmail でよくある制約です）\n"
                "  回避手順（1 回だけ）:\n"
                "   1. まず一度アプリを起動して試合を1つ作り、PC の tmp フォルダに\n"
                f"      {', '.join(sync.SYNC_FILES)} を作ります。\n"
                "   2. ブラウザで Drive の対象フォルダを開き、その 3 つの CSV を\n"
                "      ドラッグ＆ドロップでアップロードします（あなたが所有者になります）。\n"
                "   3. 以降はアプリが自動でこの 3 ファイルを更新します。\n"
            )
            sys.exit(0)
        _fail("保存テストでエラー:\n    " + msg)

    print("\n" + "=" * 60)
    print(" セットアップ完了！ 通常どおりアプリを起動すれば、")
    print(" データが自動で Google Drive と同期されます。")
    print("   streamlit run src/stats_app.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
