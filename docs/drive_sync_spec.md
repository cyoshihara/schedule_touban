# バスケ スコア＆スタッツ記録アプリ：Google Drive 同期によるデータ永続化 設計仕様（v0.1）

作成日: 2026-06-06 / 作成: planner サブエージェント
ステータス: 承認済み（ローカル実行前提で実装フェーズへ）
対象: `docs/basketball_stats_spec.md` の確定事項 A4/A5（将来拡張だった Drive 同期）を実装フェーズへ昇格させる追加設計

## 確定（2026-06-06 レビュー反映）
- 実行先: **ローカル実行**（`./.local/credentials.json` を使用）。Streamlit Cloud も後方互換で対応可。
- 認証: 既存 GCP サービスアカウントを流用。
- フォルダ: 専用フォルダを1つ作成し folder_id を設定、サービスアカウントへ「編集者」共有。
- 注意: 個人 Gmail のマイドライブではサービスアカウントの新規ファイル作成が storageQuotaExceeded になりうる（§4.3）。回避のためセットアップで CSV を事前作成し、アプリは update 主体で運用する。

---

## 1. 概要と前提

### 1.1 目的
現状、バスケアプリは `./tmp` 配下のローカル CSV にのみ保存している。コンテナ再起動やデプロイでローカル CSV が消えるため、これらの CSV を Google Drive 上のフォルダと同期させ、端末・セッションをまたいでデータを永続化する。

### 1.2 同期方針（単一端末・リアルタイム入力前提）
- 同時に複数端末で同じ試合を編集しない前提（A1/A9）。**競合解決（マージ）は実装しない。**
- 基本モデルは **last-writer-wins**。**ローカル CSV を source of truth とし、Drive へプッシュ／Drive からプル**する。
- アプリのロジックは常にローカル CSV を読み書きし、Drive とのやり取りは I/O の前後に被せる薄い層に閉じ込める。

### 1.3 後方互換
Drive 設定がない／初期化失敗時は、従来どおりローカル CSV のみで完全動作。既存テスト（pytest 21 件）に影響しない。

---

## 3. アーキテクチャ

### 3.1 設計原則：既存 I/O を壊さず同期を被せる
`stats_models.py` の read/write 関数群はローカル CSV を読み書きする純粋 I/O で `data_dir` 引数を取る。**この層には手を入れない。** Drive 同期は外側に被せる新規モジュール `stats_sync.py` のストレージ抽象として実装する。

```
stats_app.py (UI)
  - 起動時: sync.pull_on_startup()
  - 書込後: sync.push_after_write(...)
        │
stats_models.py（変更なし） → ./tmp の CSV
        │
stats_sync.py（新規）= StorageBackend / LocalOnlyBackend / DriveSyncBackend
        │
utils.GoogleDriveService（upload API 追加）
```

### 3.2 新規モジュール `src/stats_sync.py`
`StorageBackend` プロトコル（`pull()` / `push(files)` / `enabled` / `status`）。
- `LocalOnlyBackend`: pull/push は no-op、`enabled=False`。Drive 未設定時の既定（後方互換の要）。
- `DriveSyncBackend`: upload 拡張版 `GoogleDriveService` を内部に持ち 3 CSV をプル／プッシュ。
- ファクトリ `build_backend(data_dir, config)`: 設定が揃い初期化成功なら `DriveSyncBackend`、未設定・例外時は `LocalOnlyBackend`（例外を握りつぶしてフォールバック）。

### 3.3 同期ポイント
- 起動時（セッション初回のみ、`st.session_state["_synced"]`）: `pull()` → `models.init_storage()`。
- 書込後: ローカル書込直後に dirty マーク、§7 の方針で push。
- 明示「クラウドに保存」ボタン: 全 CSV を push。
- 起動時プルは初回限定（毎回プルするとローカル最新を Drive 旧版で上書きするリスク）。

### 3.4 有効/無効スイッチ
設定 `gdrive.enabled`（既定 true）。読めない／false なら強制 `LocalOnlyBackend`。

---

## 4. `GoogleDriveService` への追加 API

既存メソッド（`list_drive_files`/`get_file_name`/`download_file`）のシグネチャは変更しない。以下を追加。

| メソッド | 挙動 |
|---|---|
| `find_file_in_folder(folder_id, file_name)` | フォルダ内同名ファイル検索。`files().list(q="'<folder_id>' in parents and name='<name>' and trashed=false", fields='files(id,name)')`。無ければ None |
| `upload_new_file(folder_id, local_path, file_name=None)` | `files().create(body={name,parents:[folder_id]}, media_body=MediaFileUpload(...))` |
| `update_file(file_id, local_path)` | `files().update(fileId, media_body=MediaFileUpload(...))` |
| `upsert_file(folder_id, local_path, file_name=None)` | あれば update、無ければ create。同期層が主に使う |
| `download_file_to(folder_id, file_name, dest_path)` | フォルダ内指定名ファイルを指定パスへ取得。無ければ何もしない |

`MediaFileUpload`（`googleapiclient.http`）の import 追加が必要。共有ドライブ対応の `supportsAllDrives` 等は任意引数で受ける。

### 4.2 OAuth スコープ
create/update には書き込みスコープが必要。推奨 **`https://www.googleapis.com/auth/drive.file`**（アプリが作成/開いたファイルに限定、最小権限）。フォルダ内の既存ファイルも触る必要があれば `https://www.googleapis.com/auth/drive`。`service_account.Credentials.from_service_account_info(info, scopes=[...])` で指定。既存 `get_secrets()` を壊さず同期用に別途スコープ付き creds を生成する。

### 4.3 サービスアカウントの共有要件 / クォータ
- **要件A（推奨・簡単）**: 対象フォルダをサービスアカウントのメールに「編集者」共有。
  - ただしマイドライブ上では SA 作成ファイルの所有者が SA となり、SA はクォータ 0 のため `create` が `storageQuotaExceeded` で失敗しうる。→ 回避策: **CSV をユーザーが事前作成して所有**し、アプリは `update` 主体で運用（upsert が既存を見つけて update する）。
- **要件B（確実）**: 共有ドライブ（Shared Drive、要 Workspace）に SA をメンバー追加。個人 Gmail では不可。
- 本実装はマイドライブ共有フォルダ（要件A）で開始。`create` クォータ問題は事前作成で回避。

---

## 5. 設定方法

### 5.1 Streamlit Cloud（`st.secrets`）
```toml
[gdrive]
enabled = true
stats_folder_id = "xxxxxxxxxxxxxxxxxxxxx"
```

### 5.2 ローカル（`./.local/credentials.json`）
```json
{
  "gcp": { "...": "既存" },
  "google_genai": { "api_key": "..." },
  "gdrive": { "enabled": true, "stats_folder_id": "xxxxxxxxxxxxxxxxxxxxx" }
}
```

### 5.3 設定読み出し `get_drive_config()`
Cloud/ローカル両経路から `enabled`/`stats_folder_id`/creds を取得。欠落時は disabled 相当。環境変数 `STATS_GDRIVE_FOLDER_ID` でのオーバーライドも任意許可。

---

## 6. 失敗時の挙動
**大原則: リアルタイム入力を絶対に止めない。**
- 設定なし/enabled=false → `LocalOnlyBackend`、「ローカル保存モード」表示。
- 認証失敗 → `LocalOnlyBackend` にフォールバック、`st.warning`。
- ネットワーク/権限エラー（push/pull 時）→ ローカル書込は成功済み、未同期を session_state に記録、「未同期の変更があります」＋「再同期」ボタン。
- プル失敗（起動時）→ ローカル既存 CSV で続行。
- 同期層の pull/push は内部で例外を捕捉し `status`/`SyncResult` に反映。**例外を UI まで伝播させない。**

---

## 7. パフォーマンス（プッシュ頻度）
毎イベント即時プッシュは入力遅延・API クォータ増のため避ける。推奨:
- イベント追記時はローカル CSV へ即時保存（保全の主役はローカル）。
- Drive への push は間引き: **節目イベント（試合作成・選手登録確定・「次のQへ」・試合終了・ボックススコア画面遷移）で push**、加えて**未同期が一定件数（例:10）たまったら push**。
- 常時表示の**「クラウドに保存」ボタン**で任意即 push。
- **変更があった CSV だけ**を push（dirty 追跡）。頻繁に変わるのは `trn_event.csv` のみ。

---

## 8. 実装タスク分解（TD系）

**TD1. `GoogleDriveService` への upload/find API 追加**（依存: なし）
- `src/utils.py` に find/upload/update/upsert を追加、`MediaFileUpload` import。既存メソッド不変。
- 完了条件: Drive API をモックした単体テストで upsert が「無→create／有→update」を分岐。

**TD2. Drive 設定ローダ `get_drive_config()`**（依存: なし）
- secrets/credentials.json/環境変数から enabled・stats_folder_id・creds を取得。欠落時 disabled。スコープ付き creds 生成。
- 完了条件: 設定あり/なし/一部欠落で期待どおりの config を返す単体テスト。

**TD3. ストレージ抽象 `stats_sync.py`**（依存: TD1, TD2）
- `StorageBackend`/`LocalOnlyBackend`/`DriveSyncBackend`/`build_backend()`。
- pull は 3 CSV を folder→data_dir、push は dirty な CSV を upsert。例外捕捉し status 反映。
- 完了条件: `GoogleDriveService` をモック化して pull/push、例外時フォールバック、未設定時 LocalOnly をテスト。

**TD4. `stats_app.py` への同期フック組み込み**（依存: TD3）
- `main()` で build_backend → 初回 pull → init_storage。書込後 dirty マーク＋間引き push。「クラウドに保存」ボタン、同期ステータス表示。
- 完了条件: Drive 無効環境で従来どおり動作、有効環境（モック）でプル→記録→push が正しく遷移。

**TD5. ドキュメント更新**（依存: TD1〜TD4）
- `docs/basketball_stats_spec.md` の A4/A5 を更新、セットアップ手順追記。

推奨シーケンス: TD1 → TD2 → TD3 → TD4 → TD5。

---

## 9. 受け入れ基準
1. **upsert 分岐（モック）**: 同名なし→create、有→update を呼ぶ。
2. **後方互換（同期無効）**: 設定なしで build_backend が LocalOnlyBackend、pull/push が no-op。既存 21 件 green 維持。
3. **フォールバック**: creds 不正・初期化例外時に例外を投げず LocalOnlyBackend。
4. **起動時プル（モック）**: pull がモック Drive の 3 CSV を data_dir に配置、その後 read できる。無ければ空で続行。
5. **push 対象の絞り込み**: event のみ変更時、event CSV だけ upsert。
6. **push 失敗時の継続**: push 内例外が伝播せず、ローカル保存済み、status が OFFLINE/AUTH_ERROR。
7. **同期と集計の一致**: pull 取得 CSV から build_boxscore/compute_scores が push 前と同一結果。
8. **既存 I/O 非干渉**: stats_models.py 無変更で従来テスト通過。

---

## 10. 既存テスト（21件）を壊さない方針
- `stats_models.py`/`stats_const.py`/`stats_logic.py` 変更なし。Drive 同期は `stats_sync.py`（新規）と `utils.py` への追加メソッドのみ。
- `utils.py` は追加のみ・既存メソッド不変。
- テスト環境では gdrive 設定が無く build_backend は LocalOnlyBackend（no-op）。
- 新規テストは Drive を完全モック化（`drive_service` を MagicMock に差し替え）。ネットワーク・認証情報不要。
- 新規テストファイル: `tests/test_stats_sync.py` / `tests/test_utils_drive.py`。
