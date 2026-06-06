"""GoogleDriveService の upload/find/upsert API の単体テスト（TD1・受け入れ基準1）。

Drive API は完全モック化する（drive_service を MagicMock に差し替え）。
ネットワーク・実認証情報を一切使わない。
"""

from unittest.mock import MagicMock

import utils


def _make_service():
  """GoogleDriveService を実初期化せず生成し、drive_service をモックに差し替える。

  __init__ は build(...) で実際の Drive クライアントを作るため、
  __new__ でインスタンスだけ作って属性を手で設定する。
  """
  svc = utils.GoogleDriveService.__new__(utils.GoogleDriveService)
  svc.drive_service = MagicMock()
  svc.data_dir = "."
  return svc


def test_find_file_in_folder_returns_id_when_present():
  svc = _make_service()
  svc.drive_service.files.return_value.list.return_value.execute.return_value = {
    "files": [{"id": "FILE123", "name": "trn_event.csv"}]
  }
  file_id = svc.find_file_in_folder("FOLDER", "trn_event.csv")
  assert file_id == "FILE123"


def test_find_file_in_folder_returns_none_when_absent():
  svc = _make_service()
  svc.drive_service.files.return_value.list.return_value.execute.return_value = {
    "files": []
  }
  assert svc.find_file_in_folder("FOLDER", "trn_event.csv") is None


def test_upsert_creates_when_no_existing_file(tmp_path):
  # 受け入れ基準1: 同名なし → create を呼ぶ（update は呼ばない）。
  local = tmp_path / "trn_event.csv"
  local.write_text("event_id\n1\n")

  svc = _make_service()
  files_api = svc.drive_service.files.return_value
  # find → None（同名なし）
  files_api.list.return_value.execute.return_value = {"files": []}
  # create → 新規 file_id
  files_api.create.return_value.execute.return_value = {"id": "NEW123"}

  file_id = svc.upsert_file("FOLDER", str(local))

  assert file_id == "NEW123"
  assert files_api.create.called
  assert not files_api.update.called


def test_upsert_updates_when_existing_file(tmp_path):
  # 受け入れ基準1: 同名あり → update を呼ぶ（create は呼ばない）。
  local = tmp_path / "trn_event.csv"
  local.write_text("event_id\n1\n")

  svc = _make_service()
  files_api = svc.drive_service.files.return_value
  # find → 既存 file_id（同名あり）
  files_api.list.return_value.execute.return_value = {
    "files": [{"id": "EXIST123", "name": "trn_event.csv"}]
  }
  files_api.update.return_value.execute.return_value = {"id": "EXIST123"}

  file_id = svc.upsert_file("FOLDER", str(local))

  assert file_id == "EXIST123"
  assert files_api.update.called
  assert not files_api.create.called


def test_download_file_to_skips_when_absent(tmp_path):
  # フォルダ内に該当なし → 何もせず None。
  svc = _make_service()
  svc.drive_service.files.return_value.list.return_value.execute.return_value = {
    "files": []
  }
  dest = tmp_path / "trn_event.csv"
  result = svc.download_file_to("FOLDER", "trn_event.csv", str(dest))
  assert result is None
  assert not dest.exists()
