"""バスケットボール スコア＆スタッツ記録アプリのデータI/O層（T2）。

game / game_player / event の CSV 読み書き（polars 1.21.0）を担当する。
仕様書 docs/basketball_stats_spec.md の 6章・9章(T2) に対応。

テスト容易性のため、すべての I/O 関数は保存先ディレクトリ data_dir を
引数で受け取れるようにしている（既定は stats_const.DIR_TEMP）。
"""

import os
from datetime import datetime

import polars as pl

import stats_const as sc


# ---------------------------------------------------------------------------
# スキーマ定義（polars の dtype）。空 CSV 初期化・read 時の型保証に使う。
# ---------------------------------------------------------------------------
_GAME_SCHEMA = {
  sc.GameColumns.game_id: pl.Int64,
  sc.GameColumns.date: pl.Utf8,
  sc.GameColumns.home_team_name: pl.Utf8,
  sc.GameColumns.away_team_name: pl.Utf8,
  sc.GameColumns.num_quarters: pl.Int64,
  sc.GameColumns.quarter_minutes: pl.Int64,
  sc.GameColumns.status: pl.Utf8,
  sc.GameColumns.created_at: pl.Utf8,
}

_GAME_PLAYER_SCHEMA = {
  sc.GamePlayerColumns.game_id: pl.Int64,
  sc.GamePlayerColumns.player_id: pl.Int64,
  sc.GamePlayerColumns.player_name: pl.Utf8,
  sc.GamePlayerColumns.number: pl.Int64,
}

_EVENT_SCHEMA = {
  sc.EventColumns.event_id: pl.Int64,
  sc.EventColumns.game_id: pl.Int64,
  sc.EventColumns.quarter: pl.Int64,
  sc.EventColumns.team_side: pl.Utf8,
  sc.EventColumns.player_id: pl.Int64,
  sc.EventColumns.event_type: pl.Utf8,
  sc.EventColumns.points: pl.Int64,
  sc.EventColumns.made: pl.Boolean,
  sc.EventColumns.assist_player_id: pl.Int64,
  sc.EventColumns.created_at: pl.Utf8,
}


# ---------------------------------------------------------------------------
# 内部ユーティリティ
# ---------------------------------------------------------------------------
def _ensure_dir(data_dir: str) -> None:
  """保存先ディレクトリが無ければ作成する。"""
  if not os.path.isdir(data_dir):
    os.makedirs(data_dir, exist_ok=True)


def _path(data_dir: str, file_name: str) -> str:
  return os.path.join(data_dir, file_name)


def _now_str() -> str:
  return datetime.now().isoformat(timespec="seconds")


def _read_or_empty(path: str, schema: dict) -> pl.DataFrame:
  """CSV が存在すればスキーマ指定で読み、無ければ空 DataFrame を返す。"""
  if os.path.isfile(path):
    return pl.read_csv(path, schema_overrides=schema)
  return pl.DataFrame(schema=schema)


# ---------------------------------------------------------------------------
# 初期化
# ---------------------------------------------------------------------------
def init_storage(data_dir: str = sc.DIR_TEMP) -> None:
  """CSV が無い場合に空ファイルを初期化する。"""
  _ensure_dir(data_dir)
  for file_name, schema in (
    (sc.CsvFile.game, _GAME_SCHEMA),
    (sc.CsvFile.game_player, _GAME_PLAYER_SCHEMA),
    (sc.CsvFile.event, _EVENT_SCHEMA),
  ):
    path = _path(data_dir, file_name)
    if not os.path.isfile(path):
      pl.DataFrame(schema=schema).write_csv(path)


# ---------------------------------------------------------------------------
# 読み込み
# ---------------------------------------------------------------------------
def read_games(data_dir: str = sc.DIR_TEMP) -> pl.DataFrame:
  """trn_game.csv を読み込む。"""
  return _read_or_empty(_path(data_dir, sc.CsvFile.game), _GAME_SCHEMA)


def read_game_players(data_dir: str = sc.DIR_TEMP) -> pl.DataFrame:
  """trn_game_player.csv を読み込む。"""
  return _read_or_empty(_path(data_dir, sc.CsvFile.game_player), _GAME_PLAYER_SCHEMA)


def read_events(data_dir: str = sc.DIR_TEMP) -> pl.DataFrame:
  """trn_event.csv を読み込む。"""
  return _read_or_empty(_path(data_dir, sc.CsvFile.event), _EVENT_SCHEMA)


def read_game_players_by_game(
  game_id: int, data_dir: str = sc.DIR_TEMP
) -> pl.DataFrame:
  """特定試合の出場選手を読み込む。"""
  df = read_game_players(data_dir)
  return df.filter(pl.col(sc.GamePlayerColumns.game_id) == game_id)


def read_events_by_game(game_id: int, data_dir: str = sc.DIR_TEMP) -> pl.DataFrame:
  """特定試合のイベントを event_id 昇順で読み込む。"""
  df = read_events(data_dir)
  return df.filter(pl.col(sc.EventColumns.game_id) == game_id).sort(
    sc.EventColumns.event_id
  )


# ---------------------------------------------------------------------------
# 採番
# ---------------------------------------------------------------------------
def _next_id(df: pl.DataFrame, col: str) -> int:
  """採番: 既存最大値 + 1（空なら 1）。"""
  if df.height == 0:
    return 1
  max_id = df.select(pl.col(col).max()).item()
  if max_id is None:
    return 1
  return int(max_id) + 1


# ---------------------------------------------------------------------------
# 書き込み（試合作成・選手登録・イベント追記・undo）
# ---------------------------------------------------------------------------
def create_game(
  date: str,
  home_team_name: str,
  away_team_name: str,
  num_quarters: int = sc.GameDefault.num_quarters,
  quarter_minutes: int = sc.GameDefault.quarter_minutes,
  data_dir: str = sc.DIR_TEMP,
) -> int:
  """試合を新規作成し、採番した game_id を返す（status=in_progress）。"""
  _ensure_dir(data_dir)
  games = read_games(data_dir)
  game_id = _next_id(games, sc.GameColumns.game_id)

  row = pl.DataFrame(
    {
      sc.GameColumns.game_id: [game_id],
      sc.GameColumns.date: [str(date)],
      sc.GameColumns.home_team_name: [home_team_name],
      sc.GameColumns.away_team_name: [away_team_name],
      sc.GameColumns.num_quarters: [int(num_quarters)],
      sc.GameColumns.quarter_minutes: [int(quarter_minutes)],
      sc.GameColumns.status: [sc.GameStatus.IN_PROGRESS],
      sc.GameColumns.created_at: [_now_str()],
    },
    schema=_GAME_SCHEMA,
  )
  games = pl.concat([games, row], how="vertical")
  games.write_csv(_path(data_dir, sc.CsvFile.game))
  return game_id


def update_game_status(
  game_id: int, status: str, data_dir: str = sc.DIR_TEMP
) -> None:
  """試合ステータスを更新する。"""
  games = read_games(data_dir)
  games = games.with_columns(
    pl.when(pl.col(sc.GameColumns.game_id) == game_id)
    .then(pl.lit(status))
    .otherwise(pl.col(sc.GameColumns.status))
    .alias(sc.GameColumns.status)
  )
  games.write_csv(_path(data_dir, sc.CsvFile.game))


def register_player(
  game_id: int,
  player_name: str,
  number: int,
  player_id: int | None = None,
  data_dir: str = sc.DIR_TEMP,
) -> int:
  """出場選手を1人登録し、player_id を返す。

  player_id 未指定時は当試合内ローカルIDを採番する。
  """
  _ensure_dir(data_dir)
  players = read_game_players(data_dir)
  if player_id is None:
    in_game = players.filter(pl.col(sc.GamePlayerColumns.game_id) == game_id)
    player_id = _next_id(in_game, sc.GamePlayerColumns.player_id)

  row = pl.DataFrame(
    {
      sc.GamePlayerColumns.game_id: [int(game_id)],
      sc.GamePlayerColumns.player_id: [int(player_id)],
      sc.GamePlayerColumns.player_name: [player_name],
      sc.GamePlayerColumns.number: [int(number)],
    },
    schema=_GAME_PLAYER_SCHEMA,
  )
  players = pl.concat([players, row], how="vertical")
  players.write_csv(_path(data_dir, sc.CsvFile.game_player))
  return int(player_id)


def register_players(
  game_id: int,
  players: list[dict],
  data_dir: str = sc.DIR_TEMP,
) -> list[int]:
  """複数の出場選手をまとめて登録する。

  players の各要素は {"player_name": str, "number": int} を想定。
  player_id を含めれば固定IDで登録する。
  """
  ids: list[int] = []
  for p in players:
    pid = register_player(
      game_id=game_id,
      player_name=p[sc.GamePlayerColumns.player_name],
      number=p[sc.GamePlayerColumns.number],
      player_id=p.get(sc.GamePlayerColumns.player_id),
      data_dir=data_dir,
    )
    ids.append(pid)
  return ids


def append_event(
  game_id: int,
  quarter: int,
  team_side: str,
  event_type: str,
  player_id: int | None = None,
  points: int = 0,
  made: bool | None = None,
  assist_player_id: int | None = None,
  data_dir: str = sc.DIR_TEMP,
) -> int:
  """イベントを1件追記し、採番した event_id を返す。"""
  _ensure_dir(data_dir)
  if event_type not in sc.EVENT_TYPES:
    raise ValueError(f"unknown event_type: {event_type}")

  events = read_events(data_dir)
  event_id = _next_id(events, sc.EventColumns.event_id)

  row = pl.DataFrame(
    {
      sc.EventColumns.event_id: [event_id],
      sc.EventColumns.game_id: [int(game_id)],
      sc.EventColumns.quarter: [int(quarter)],
      sc.EventColumns.team_side: [team_side],
      sc.EventColumns.player_id: [player_id],
      sc.EventColumns.event_type: [event_type],
      sc.EventColumns.points: [int(points)],
      sc.EventColumns.made: [made],
      sc.EventColumns.assist_player_id: [assist_player_id],
      sc.EventColumns.created_at: [_now_str()],
    },
    schema=_EVENT_SCHEMA,
  )
  events = pl.concat([events, row], how="vertical")
  events.write_csv(_path(data_dir, sc.CsvFile.event))
  return event_id


def delete_last_event(
  game_id: int, data_dir: str = sc.DIR_TEMP
) -> int | None:
  """指定試合の最終イベント（最大 event_id）を削除する（undo 用）。

  削除した event_id を返す。対象が無ければ None。
  """
  events = read_events(data_dir)
  in_game = events.filter(pl.col(sc.EventColumns.game_id) == game_id)
  if in_game.height == 0:
    return None

  last_event_id = int(
    in_game.select(pl.col(sc.EventColumns.event_id).max()).item()
  )
  events = events.filter(pl.col(sc.EventColumns.event_id) != last_event_id)
  events.write_csv(_path(data_dir, sc.CsvFile.event))
  return last_event_id
