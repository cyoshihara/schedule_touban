# Streamlit Community Cloud デプロイ手順（スマホ/iPad から見る）

バスケ スタッツアプリを無料の Streamlit Community Cloud に公開し、スマホ/iPad の
ブラウザから専用 URL でアクセスできるようにする手順。データは Google Drive 同期で
保持される（クラウドはファイルが消えるため）。

---

## 前提
- GitHub にこのリポジトリがある（`cyoshihara/schedule_touban`）。
- 公開ブランチ: `claude/basketball-stats-app-k0S6u`（このブランチを直接デプロイ可能）。
- Google Drive の同期フォルダ ID: `1RWx3b2IRH6D2SzIp6OGmwVxCPhzraxKi`

---

## 手順

### 1. Drive フォルダにサービスアカウントを共有
1. ブラウザで対象フォルダを開く: https://drive.google.com/drive/folders/1RWx3b2IRH6D2SzIp6OGmwVxCPhzraxKi
2. 右クリック →「共有」→ **サービスアカウントのメール**（`〜@〜.iam.gserviceaccount.com`、当番アプリの認証ファイルの `client_email`）を **「編集者」** で追加。

### 2. 初期 CSV を Drive にアップロード（個人 Gmail の容量制限回避）
チャットで受け取った **3 つの CSV**（`trn_game.csv` / `trn_game_player.csv` / `trn_event.csv`）を、
上記フォルダにブラウザでドラッグ＆ドロップしてアップロードする。
（あなたが所有者になるので、サービスアカウントは「更新」だけで済み、容量制限に当たらない）

### 3. Streamlit Community Cloud でアプリを作成
1. https://share.streamlit.io を開き、**GitHub アカウントでサインイン**。
2. 「**Create app**」→「Deploy a public app from GitHub」。
3. 設定:
   - **Repository**: `cyoshihara/schedule_touban`
   - **Branch**: `claude/basketball-stats-app-k0S6u`
   - **Main file path**: `src/stats_app.py`
4. 「**Advanced settings**」→ **Secrets** に下記（§4）を貼り付け。
5. 「Deploy」。数分でビルドが終わり、`https://〜.streamlit.app` の URL が発行される。
   → この URL をスマホ/iPad のホーム画面に追加すればアプリのように使える。

### 4. Secrets（Advanced settings → Secrets に貼る）
`.streamlit/secrets.toml.example` を参照。要点:

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "xxxx@xxxx.iam.gserviceaccount.com"
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

[gdrive]
enabled = true
stats_folder_id = "1RWx3b2IRH6D2SzIp6OGmwVxCPhzraxKi"
```

- このスタッツアプリに必要な secrets は **`[gcp_service_account]` と `[gdrive]` の 2 つだけ**
  （`google_genai` は当番アプリ用で、本アプリでは不要）。
- `[gcp_service_account]` の各値は、当番アプリで使っているサービスアカウントの
  JSON（`credentials.json` の `gcp` セクション）の中身をそのまま移す。
- `private_key` は改行を `\n` のままにして 1 行で貼る（TOML の `"..."` 内）。

---

## 動作確認
- 発行された `https://〜.streamlit.app` をスマホ/iPad で開く。
- 試合を作成 → 記録 → 画面下の「ストレージ: 同期OK」を確認。
- 一度アプリを再起動（Cloud の「Reboot」）してもデータが残っていれば、Drive 同期成功。
- 画面に「同期エラー（共有/認証を確認）」が出る場合は、§1 の共有または §2 のアップロードが
  未完。手順を見直す。

---

## 補足
- 公開 URL はリンクを知っていれば誰でも開ける。限定したい場合は Streamlit Cloud の
  「Settings → Sharing」でビューワーをメール制限できる（要設定）。
- ブランチを `main` に統合したい場合は別途 PR 作成 → マージ後、Cloud の Branch を `main` に変更。
