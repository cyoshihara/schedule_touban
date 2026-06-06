"""ストレージ抽象 stats_sync.py の単体テスト（TD3・受け入れ基準2〜7）。

Drive は完全モック化する。ネットワーク・実認証情報を一切使わない。
data_dir には tmp_path を使う。
"""

import os
import shutil

import polars as pl
import pytest

import stats_const as sc
import stats_logic as logic
import stats_models as sm
import stats_sync as sync


class FakeDrive:
  """GoogleDriveService の振る舞いを模した、フォルダをメモリ保持するフェイク。

  upsert_file: ローカル CSV の内容を store[file_name] に保存（push）。
  download_file_to: store にあれば dest_path へ書き出す（pull）。無ければ None。
  """

  def __init__(self):
    self.store: dict[str, str] = {}
    self.upserts: list[str] = []

  def upsert_file(self, folder_id, local_path, file_name=None, **kwargs):
    if file_name is None:
      file_name = os.path.basename(local_path)
    with open(local_path, "r", encoding="utf-8") as f:
      self.store[file_name] = f.read()
    self.upserts.append(file_name)
    return f"id_{file_name}"

  def download_file_to(self, folder_id, file_name, dest_path, **kwargs):
    if file_name not in self.store:
      return None
    dest_dir = os.path.dirname(dest_path)
    if dest_dir and not os.path.isdir(dest_dir):
      os.makedirs(dest_dir, exist_ok=True)
    with open(dest_path, "w", encoding="utf-8") as f:
      f.write(self.store[file_name])
    return dest_path


class RaisingDrive:
  """常に例外を投げる Drive（push/pull 失敗時の継続をテストする）。"""

  def upsert_file(self, *a, **k):
    raise RuntimeError("network down")

  def download_file_to(self, *a, **k):
    raise RuntimeError("network down")


# ---------------------------------------------------------------------------
# 受け入れ基準2: 後方互換（設定なしで LocalOnlyBackend・no-op）
# ---------------------------------------------------------------------------
def test_build_backend_returns_local_only_when_no_config(tmp_path):
  data_dir = str(tmp_path / "data")
  cfg = sync.DriveConfig(enabled=False)
  backend = sync.build_backend(data_dir, config=cfg)
  assert isinstance(backend, sync.LocalOnlyBackend)
  assert backend.enabled is False
  # pull/push は no-op（例外なく DISABLED を返す）。
  assert backend.pull().status == sync.SyncStatus.DISABLED
  assert backend.push([sc.CsvFile.event]).status == sync.SyncStatus.DISABLED


def test_build_backend_local_only_when_config_none_and_no_secrets(tmp_path):
  # config 未指定でも get_drive_config が disabled を返し LocalOnly になる。
  data_dir = str(tmp_path / "data")
  backend = sync.build_backend(data_dir)
  assert isinstance(backend, sync.LocalOnlyBackend)
  assert backend.enabled is False


# ---------------------------------------------------------------------------
# 受け入れ基準3: フォールバック（初期化例外で LocalOnlyBackend）
# ---------------------------------------------------------------------------
def test_build_backend_falls_back_on_init_exception(tmp_path, monkeypatch):
  data_dir = str(tmp_path / "data")
  # creds は不正なオブジェクト。GoogleDriveService 初期化で例外を起こさせる。
  cfg = sync.DriveConfig(
    enabled=True, stats_folder_id="FOLDER", creds=object()
  )

  import utils

  def _boom(*a, **k):
    raise RuntimeError("auth failed")

  monkeypatch.setattr(utils, "GoogleDriveService", _boom)
  backend = sync.build_backend(data_dir, config=cfg)
  assert isinstance(backend, sync.LocalOnlyBackend)


# ---------------------------------------------------------------------------
# 受け入れ基準4: 起動時プル（モック Drive の CSV を data_dir に配置→read 可能）
# ---------------------------------------------------------------------------
def _seed_drive_with_game(fake: FakeDrive, src_dir: str):
  """src_dir に試合データを作り、その CSV を FakeDrive の store へ載せる。"""
  sm.init_storage(src_dir)
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=src_dir)
  sm.register_players(
    gid, [{"player_name": "A", "number": 4}], data_dir=src_dir
  )
  sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_2PT,
    player_id=1, points=2, made=True, data_dir=src_dir,
  )
  sm.append_event(
    gid, 1, sc.TeamSide.AWAY, sc.EventType.AWAY_SCORE,
    points=3, data_dir=src_dir,
  )
  for fname in sync.SYNC_FILES:
    with open(os.path.join(src_dir, fname), "r", encoding="utf-8") as f:
      fake.store[fname] = f.read()
  return gid


def test_pull_places_csv_and_is_readable(tmp_path):
  src_dir = str(tmp_path / "src")
  data_dir = str(tmp_path / "data")
  os.makedirs(data_dir, exist_ok=True)

  fake = FakeDrive()
  gid = _seed_drive_with_game(fake, src_dir)

  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=fake
  )
  result = backend.pull()
  assert result.status == sync.SyncStatus.OK
  assert set(result.pulled) == set(sync.SYNC_FILES)

  # pull 後にローカルから read できる。
  games = sm.read_games(data_dir)
  events = sm.read_events_by_game(gid, data_dir)
  assert games.height == 1
  assert events.height == 2


def test_pull_continues_when_files_absent(tmp_path):
  # Drive に何も無ければ空で続行（pulled は空、status OK）。
  data_dir = str(tmp_path / "data")
  fake = FakeDrive()
  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=fake
  )
  result = backend.pull()
  assert result.status == sync.SyncStatus.OK
  assert result.pulled == []


# ---------------------------------------------------------------------------
# 受け入れ基準5: push 対象の絞り込み（event のみ変更→event だけ upsert）
# ---------------------------------------------------------------------------
def test_push_only_dirty_files(tmp_path):
  data_dir = str(tmp_path / "data")
  sm.init_storage(data_dir)
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_2PT,
    player_id=1, points=2, made=True, data_dir=data_dir,
  )

  fake = FakeDrive()
  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=fake
  )
  result = backend.push([sc.CsvFile.event])
  assert result.status == sync.SyncStatus.OK
  assert result.pushed == [sc.CsvFile.event]
  # event だけが upsert された。
  assert fake.upserts == [sc.CsvFile.event]


def test_push_skips_unknown_and_missing_files(tmp_path):
  data_dir = str(tmp_path / "data")
  sm.init_storage(data_dir)
  fake = FakeDrive()
  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=fake
  )
  # 未知ファイル名は無視され、存在する CSV だけ push される。
  result = backend.push(["bogus.csv", sc.CsvFile.game])
  assert result.pushed == [sc.CsvFile.game]


# ---------------------------------------------------------------------------
# 受け入れ基準6: push/pull 失敗時の継続（例外が伝播せず status に反映）
# ---------------------------------------------------------------------------
def test_push_failure_does_not_propagate(tmp_path):
  data_dir = str(tmp_path / "data")
  sm.init_storage(data_dir)
  sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)

  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=RaisingDrive()
  )
  result = backend.push([sc.CsvFile.game])  # 例外を投げない
  assert result.status == sync.SyncStatus.OFFLINE
  assert backend.status == sync.SyncStatus.OFFLINE
  # ローカル CSV は保存済みのまま（push 失敗でも消えない）。
  assert sm.read_games(data_dir).height == 1


def test_pull_failure_does_not_propagate(tmp_path):
  data_dir = str(tmp_path / "data")
  os.makedirs(data_dir, exist_ok=True)
  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=RaisingDrive()
  )
  result = backend.pull()  # 例外を投げない
  assert result.status == sync.SyncStatus.OFFLINE
  assert backend.status == sync.SyncStatus.OFFLINE


# ---------------------------------------------------------------------------
# 受け入れ基準7: 同期と集計の一致（pull 往復で boxscore/scores が同一）
# ---------------------------------------------------------------------------
def test_pull_roundtrip_keeps_aggregations(tmp_path):
  src_dir = str(tmp_path / "src")
  data_dir = str(tmp_path / "data")
  os.makedirs(data_dir, exist_ok=True)

  fake = FakeDrive()
  gid = _seed_drive_with_game(fake, src_dir)

  # push 前（src）の集計
  src_events = sm.read_events_by_game(gid, src_dir)
  src_players = sm.read_game_players_by_game(gid, src_dir)
  box_before = logic.build_boxscore(src_events, src_players)
  scores_before = logic.compute_scores(src_events)

  # data_dir へ pull
  backend = sync.DriveSyncBackend(
    data_dir=data_dir, folder_id="FOLDER", drive_service=fake
  )
  backend.pull()

  dst_events = sm.read_events_by_game(gid, data_dir)
  dst_players = sm.read_game_players_by_game(gid, data_dir)
  box_after = logic.build_boxscore(dst_events, dst_players)
  scores_after = logic.compute_scores(dst_events)

  assert scores_after == scores_before
  assert box_after.equals(box_before)


# ---------------------------------------------------------------------------
# get_drive_config: 設定なし/欠落時 disabled（例外を投げない）
# ---------------------------------------------------------------------------
def test_get_drive_config_disabled_when_no_secrets(monkeypatch, tmp_path):
  # ./.local/credentials.json も st.secrets も無い前提で disabled。
  missing = str(tmp_path / "nope.json")
  monkeypatch.setattr(sync, "_LOCAL_CREDS_PATH", missing)
  cfg = sync.get_drive_config()
  assert cfg.enabled is False


def test_get_drive_config_disabled_when_enabled_false(monkeypatch, tmp_path):
  import json

  creds_path = tmp_path / "credentials.json"
  creds_path.write_text(json.dumps({
    "gdrive": {"enabled": False, "stats_folder_id": "FOLDER"},
    "gcp": {"type": "service_account"},
  }))
  monkeypatch.setattr(sync, "_LOCAL_CREDS_PATH", str(creds_path))
  cfg = sync.get_drive_config()
  assert cfg.enabled is False


# ---------------------------------------------------------------------------
# _classify_error: 401/403/認証エラーは AUTH_ERROR、それ以外は OFFLINE
# ---------------------------------------------------------------------------
class _Resp:
  def __init__(self, status):
    self.status = status


def test_classify_error_generic_is_offline():
  assert sync._classify_error(RuntimeError("network down")) == sync.SyncStatus.OFFLINE


def test_classify_error_http_403_is_auth_error():
  try:
    from googleapiclient.errors import HttpError
  except Exception:
    import pytest

    pytest.skip("googleapiclient 未インストール")
  # HttpError.__init__ は httplib2 Response 依存のため __new__ で生成し resp を設定。
  err = HttpError.__new__(HttpError)
  err.resp = _Resp(403)
  assert sync._classify_error(err) == sync.SyncStatus.AUTH_ERROR


def test_classify_error_refresh_error_is_auth_error():
  try:
    from google.auth.exceptions import RefreshError
  except Exception:
    import pytest

    pytest.skip("google-auth 未インストール")
  assert sync._classify_error(RefreshError("bad creds")) == sync.SyncStatus.AUTH_ERROR
