"""バスケ スコア＆スタッツ記録アプリの Google Drive 同期層（TD2/TD3）。

設計 docs/drive_sync_spec.md の 3〜7章に対応する。

設計原則:
  - ローカル CSV を source of truth とし、Drive とのやり取りは I/O の前後に
    被せる薄い層（StorageBackend）に閉じ込める。
  - 既存 I/O（stats_models.py）には手を入れない。
  - pull/push は内部で例外を捕捉し status / SyncResult に反映し、
    例外を呼び出し元（UI）へ伝播させない。
  - 設定なし／初期化失敗時は LocalOnlyBackend にフォールバックし、
    従来どおりローカル CSV のみで完全動作させる（後方互換）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

import stats_const as sc


# Drive 同期対象の 3 CSV（ファイル名は stats_const から取得）。
SYNC_FILES = (
  sc.CsvFile.game,
  sc.CsvFile.game_player,
  sc.CsvFile.event,
)

# 書き込みスコープ（アプリが作成/開いたファイルに限定、最小権限）。
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# 設定キー
_GDRIVE_KEY = "gdrive"
_ENABLED_KEY = "enabled"
_FOLDER_ID_KEY = "stats_folder_id"
_ENV_FOLDER_ID = "STATS_GDRIVE_FOLDER_ID"

# ローカル credentials.json の既定パス（既存 utils.get_secrets と同じ場所）。
_LOCAL_CREDS_PATH = "./.local/credentials.json"


# ---------------------------------------------------------------------------
# 同期ステータス（OK/OFFLINE/AUTH_ERROR/DISABLED）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SyncStatus:
  """同期ステータスの文字列定数。"""

  OK = "OK"
  OFFLINE = "OFFLINE"
  AUTH_ERROR = "AUTH_ERROR"
  DISABLED = "DISABLED"


@dataclass
class SyncResult:
  """pull/push の結果。例外は捕捉して status/error に反映する。"""

  status: str = SyncStatus.OK
  pushed: list = field(default_factory=list)
  pulled: list = field(default_factory=list)
  error: str | None = None

  @property
  def ok(self) -> bool:
    return self.status == SyncStatus.OK


def _classify_error(exc: Exception) -> str:
  """例外を同期ステータスに分類する。

  認証情報のリフレッシュ失敗や Drive API の 401/403（権限不足・共有未設定・
  storageQuotaExceeded 等）は AUTH_ERROR とし、UI で「再認証/共有設定が必要」を
  案内できるようにする。それ以外（ネットワーク断など）は OFFLINE。
  """
  try:
    from google.auth.exceptions import GoogleAuthError

    if isinstance(exc, GoogleAuthError):
      return SyncStatus.AUTH_ERROR
  except Exception:
    pass
  try:
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError):
      status_code = getattr(getattr(exc, "resp", None), "status", None)
      try:
        status_code = int(status_code)
      except (TypeError, ValueError):
        status_code = None
      if status_code in (401, 403):
        return SyncStatus.AUTH_ERROR
  except Exception:
    pass
  return SyncStatus.OFFLINE


# ---------------------------------------------------------------------------
# TD2: Drive 設定ローダ
# ---------------------------------------------------------------------------
@dataclass
class DriveConfig:
  """get_drive_config() の返り値。欠落・例外時は enabled=False を返す。"""

  enabled: bool = False
  stats_folder_id: str | None = None
  creds: object | None = None


def _load_creds_from_info(info) -> object:
  """service account info から書き込みスコープ付き creds を生成する。

  既存 utils.get_secrets を壊さないよう、ここで別途生成する。
  """
  from google.oauth2 import service_account

  return service_account.Credentials.from_service_account_info(
    info, scopes=DRIVE_SCOPES
  )


def get_drive_config() -> DriveConfig:
  """Drive 同期の設定を取得する（設計5章）。

  経路:
    1. Streamlit Cloud: st.secrets["gdrive"] と st.secrets["gcp_service_account"]
    2. ローカル: ./.local/credentials.json の "gdrive" と "gcp"
  環境変数 STATS_GDRIVE_FOLDER_ID で folder_id をオーバーライド可能。

  いずれか欠落・例外時は disabled 相当（enabled=False）を返し、例外は投げない。
  """
  try:
    cfg = _get_drive_config_cloud()
    if cfg is None:
      cfg = _get_drive_config_local()
    if cfg is None:
      return DriveConfig(enabled=False)

    enabled, folder_id, gcp_info = cfg

    # 環境変数による folder_id オーバーライド（任意）。
    env_folder = os.environ.get(_ENV_FOLDER_ID)
    if env_folder:
      folder_id = env_folder

    if not enabled:
      return DriveConfig(enabled=False, stats_folder_id=folder_id)
    if not folder_id or gcp_info is None:
      return DriveConfig(enabled=False, stats_folder_id=folder_id)

    creds = _load_creds_from_info(gcp_info)
    return DriveConfig(
      enabled=True, stats_folder_id=folder_id, creds=creds
    )
  except Exception:
    # 大原則: 設定取得で例外が出ても入力を止めない。無効扱いにする。
    return DriveConfig(enabled=False)


def _get_drive_config_cloud():
  """st.secrets 経由で (enabled, folder_id, gcp_info) を取得。無ければ None。"""
  try:
    import streamlit as st

    if _GDRIVE_KEY not in st.secrets:
      return None
    gdrive = st.secrets[_GDRIVE_KEY]
    enabled = bool(gdrive.get(_ENABLED_KEY, True))
    folder_id = gdrive.get(_FOLDER_ID_KEY)
    gcp_info = None
    if "gcp_service_account" in st.secrets:
      gcp_info = dict(st.secrets["gcp_service_account"])
    return enabled, folder_id, gcp_info
  except Exception:
    return None


def _get_drive_config_local():
  """credentials.json 経由で (enabled, folder_id, gcp_info) を取得。無ければ None。"""
  if not os.path.isfile(_LOCAL_CREDS_PATH):
    return None
  with open(_LOCAL_CREDS_PATH) as f:
    creds_info = json.load(f)
  if _GDRIVE_KEY not in creds_info:
    return None
  gdrive = creds_info[_GDRIVE_KEY]
  enabled = bool(gdrive.get(_ENABLED_KEY, True))
  folder_id = gdrive.get(_FOLDER_ID_KEY)
  gcp_info = creds_info.get("gcp")
  return enabled, folder_id, gcp_info


# ---------------------------------------------------------------------------
# TD3: ストレージ抽象
# ---------------------------------------------------------------------------
class StorageBackend:
  """ストレージ抽象（プロトコル相当）。

  - pull(): Drive→data_dir に 3 CSV を取得。SyncResult を返す。
  - push(files): dirty な CSV を Drive へ upsert。SyncResult を返す。
  - enabled: 同期が有効か。
  - status: 直近の同期ステータス。
  """

  enabled: bool = False
  status: str = SyncStatus.DISABLED

  def pull(self) -> SyncResult:  # pragma: no cover - 抽象
    raise NotImplementedError

  def push(self, files=None) -> SyncResult:  # pragma: no cover - 抽象
    raise NotImplementedError


class LocalOnlyBackend(StorageBackend):
  """Drive 未設定/無効時の既定。pull/push は no-op、enabled=False。"""

  def __init__(self, data_dir: str = sc.DIR_TEMP):
    self.data_dir = data_dir
    self.enabled = False
    self.status = SyncStatus.DISABLED

  def pull(self) -> SyncResult:
    return SyncResult(status=SyncStatus.DISABLED)

  def push(self, files=None) -> SyncResult:
    return SyncResult(status=SyncStatus.DISABLED)


class DriveSyncBackend(StorageBackend):
  """Google Drive 同期バックエンド。

  upload 拡張版 GoogleDriveService を内部に持ち、3 CSV を
  pull（folder→data_dir）/ push（dirty な CSV を upsert）する。
  pull/push 内で例外を捕捉し status/SyncResult に反映、例外を伝播させない。
  """

  def __init__(self, data_dir: str, folder_id: str, drive_service):
    self.data_dir = data_dir
    self.folder_id = folder_id
    # GoogleDriveService インスタンス（テストでは MagicMock を差し替え）。
    self.drive = drive_service
    self.enabled = True
    self.status = SyncStatus.OK

  def pull(self) -> SyncResult:
    """3 CSV を Drive から data_dir へ取得する（無ければスキップ）。"""
    result = SyncResult(status=SyncStatus.OK)
    try:
      if self.data_dir and not os.path.isdir(self.data_dir):
        os.makedirs(self.data_dir, exist_ok=True)
      for file_name in SYNC_FILES:
        dest = os.path.join(self.data_dir, file_name)
        got = self.drive.download_file_to(self.folder_id, file_name, dest)
        if got is not None:
          result.pulled.append(file_name)
      self.status = SyncStatus.OK
      return result
    except Exception as e:
      self.status = _classify_error(e)
      return SyncResult(status=self.status, error=str(e))

  def push(self, files=None) -> SyncResult:
    """dirty な CSV を Drive へ upsert する（変更があった CSV だけ）。

    files=None の場合は同期対象 3 CSV すべてを push する。
    存在しないローカル CSV はスキップする。
    """
    targets = list(files) if files else list(SYNC_FILES)
    result = SyncResult(status=SyncStatus.OK)
    try:
      for file_name in targets:
        if file_name not in SYNC_FILES:
          continue
        local_path = os.path.join(self.data_dir, file_name)
        if not os.path.isfile(local_path):
          continue
        self.drive.upsert_file(
          self.folder_id, local_path, file_name=file_name
        )
        result.pushed.append(file_name)
      self.status = SyncStatus.OK
      return result
    except Exception as e:
      self.status = _classify_error(e)
      return SyncResult(status=self.status, error=str(e))


# ---------------------------------------------------------------------------
# ファクトリ
# ---------------------------------------------------------------------------
def build_backend(data_dir: str, config: DriveConfig | None = None) -> StorageBackend:
  """ストレージバックエンドを構築する。

  設定が揃い初期化成功なら DriveSyncBackend、未設定・例外時は
  LocalOnlyBackend を返す（例外を握りつぶしてフォールバック）。
  """
  try:
    if config is None:
      config = get_drive_config()

    if not config.enabled or not config.stats_folder_id or config.creds is None:
      return LocalOnlyBackend(data_dir)

    # 遅延 import（utils 依存を build 時のみに限定）。
    import utils

    drive_service = utils.GoogleDriveService(config.creds, data_dir=data_dir)
    return DriveSyncBackend(
      data_dir=data_dir,
      folder_id=config.stats_folder_id,
      drive_service=drive_service,
    )
  except Exception:
    # 認証失敗・初期化例外時は LocalOnlyBackend にフォールバック。
    return LocalOnlyBackend(data_dir)
