"""データI/O層（stats_models, T2）の単体テスト。

すべて一時ディレクトリ(tmp_path)を data_dir に渡し、tmp/ を汚さない。
"""

import polars as pl
import pytest

import stats_const as sc
import stats_models as sm


@pytest.fixture
def data_dir(tmp_path):
  d = str(tmp_path / "data")
  sm.init_storage(d)
  return d


def test_init_storage_creates_empty_csv(data_dir):
  # 受け入れ基準: CSV が無い場合の初期化
  games = sm.read_games(data_dir)
  players = sm.read_game_players(data_dir)
  events = sm.read_events(data_dir)
  assert games.height == 0
  assert players.height == 0
  assert events.height == 0
  assert list(games.columns) == list(sc.GAME_COLUMNS)
  assert list(players.columns) == list(sc.GAME_PLAYER_COLUMNS)
  assert list(events.columns) == list(sc.EVENT_COLUMNS)


def test_create_game_assigns_unique_id_and_in_progress(data_dir):
  # 受け入れ基準 1: 試合作成 → 一意 game_id, status=in_progress
  gid1 = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  gid2 = sm.create_game("2026-06-07", "Home2", "Away2", data_dir=data_dir)
  assert gid1 == 1
  assert gid2 == 2

  games = sm.read_games(data_dir)
  assert games.height == 2
  row = games.filter(pl.col(sc.GameColumns.game_id) == gid1).row(0, named=True)
  assert row[sc.GameColumns.status] == sc.GameStatus.IN_PROGRESS
  assert row[sc.GameColumns.num_quarters] == sc.GameDefault.num_quarters
  assert row[sc.GameColumns.quarter_minutes] == sc.GameDefault.quarter_minutes


def test_register_players_local_ids(data_dir):
  # 受け入れ基準 2: 選手登録 → 当該 game_id の行が追加
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  ids = sm.register_players(
    gid,
    [
      {"player_name": "A", "number": 4},
      {"player_name": "B", "number": 5},
    ],
    data_dir=data_dir,
  )
  assert ids == [1, 2]
  players = sm.read_game_players_by_game(gid, data_dir)
  assert players.height == 2
  assert set(players[sc.GamePlayerColumns.player_name].to_list()) == {"A", "B"}


def test_append_event_assigns_sequential_id(data_dir):
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  e1 = sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_2PT,
    player_id=1, points=2, made=True, data_dir=data_dir,
  )
  e2 = sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_3PT,
    player_id=1, points=3, made=False, data_dir=data_dir,
  )
  assert e1 == 1
  assert e2 == 2
  events = sm.read_events_by_game(gid, data_dir)
  assert events.height == 2


def test_append_event_rejects_unknown_type(data_dir):
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  with pytest.raises(ValueError):
    sm.append_event(gid, 1, sc.TeamSide.HOME, "BOGUS", data_dir=data_dir)


def test_delete_last_event_undo(data_dir):
  # 受け入れ基準 8: undo = 最終イベント削除
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_2PT,
    player_id=1, points=2, made=True, data_dir=data_dir,
  )
  last = sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_3PT,
    player_id=1, points=3, made=True, data_dir=data_dir,
  )
  deleted = sm.delete_last_event(gid, data_dir)
  assert deleted == last
  events = sm.read_events_by_game(gid, data_dir)
  assert events.height == 1
  assert events[sc.EventColumns.event_type].to_list() == [sc.EventType.SHOT_2PT]


def test_delete_last_event_empty_returns_none(data_dir):
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  assert sm.delete_last_event(gid, data_dir) is None


def test_csv_roundtrip_consistency(data_dir):
  # 受け入れ基準 11: 永続化往復で一致
  gid = sm.create_game("2026-06-06", "Home", "Away", data_dir=data_dir)
  sm.register_players(
    gid, [{"player_name": "A", "number": 4}], data_dir=data_dir
  )
  sm.append_event(
    gid, 1, sc.TeamSide.HOME, sc.EventType.SHOT_2PT,
    player_id=1, points=2, made=True, data_dir=data_dir,
  )
  sm.append_event(
    gid, 2, sc.TeamSide.AWAY, sc.EventType.AWAY_SCORE,
    points=3, data_dir=data_dir,
  )

  # 読み直し（再読込相当）
  events = sm.read_events_by_game(gid, data_dir)
  assert events.height == 2
  assert events[sc.EventColumns.points].to_list() == [2, 3]
  assert events[sc.EventColumns.made].to_list()[0] is True
  # away 得点イベントの player_id は null
  assert events[sc.EventColumns.player_id].to_list()[1] is None


def test_next_id_independent_per_game_player(data_dir):
  # 選手の player_id は試合内ローカル採番
  gid1 = sm.create_game("2026-06-06", "H", "A", data_dir=data_dir)
  gid2 = sm.create_game("2026-06-07", "H", "A", data_dir=data_dir)
  ids1 = sm.register_players(gid1, [{"player_name": "A", "number": 4}], data_dir=data_dir)
  ids2 = sm.register_players(gid2, [{"player_name": "B", "number": 7}], data_dir=data_dir)
  assert ids1 == [1]
  assert ids2 == [1]
