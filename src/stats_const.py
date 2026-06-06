"""バスケットボール スコア＆スタッツ記録アプリの定数定義（T1）。

仕様書 docs/basketball_stats_spec.md の 5章・6章・9章(T1) に対応。
既存 src/const.py の dataclass(frozen=True) パターンに倣う。
"""

from dataclasses import dataclass


# 永続化先ディレクトリ（既存 const.DIR_TEMP と同じ ./tmp 配下）
DIR_TEMP = "./tmp"


@dataclass(frozen=True)
class EventType:
  """event_type の列挙（仕様 6.2 のとおり固定値）。"""

  SHOT_2PT = "SHOT_2PT"
  SHOT_3PT = "SHOT_3PT"
  FREE_THROW = "FREE_THROW"
  REB_OFF = "REB_OFF"
  REB_DEF = "REB_DEF"
  ASSIST = "ASSIST"
  STEAL = "STEAL"
  BLOCK = "BLOCK"
  TURNOVER = "TURNOVER"
  FOUL = "FOUL"
  AWAY_SCORE = "AWAY_SCORE"


# event_type の全列挙値（バリデーション用）
EVENT_TYPES = (
  EventType.SHOT_2PT,
  EventType.SHOT_3PT,
  EventType.FREE_THROW,
  EventType.REB_OFF,
  EventType.REB_DEF,
  EventType.ASSIST,
  EventType.STEAL,
  EventType.BLOCK,
  EventType.TURNOVER,
  EventType.FOUL,
  EventType.AWAY_SCORE,
)


@dataclass(frozen=True)
class TeamSide:
  """team_side の列挙。"""

  HOME = "home"
  AWAY = "away"


@dataclass(frozen=True)
class GameStatus:
  """試合ステータスの列挙。"""

  IN_PROGRESS = "in_progress"
  FINISHED = "finished"


@dataclass(frozen=True)
class GameDefault:
  """試合作成時のデフォルト値（U12 ミニバス確定値・仕様 A2）。"""

  num_quarters = 4
  quarter_minutes = 6
  # 各ピリオド5回でボーナス（チームファウルのボーナス閾値）
  team_foul_bonus_threshold = 5


@dataclass(frozen=True)
class CsvFile:
  """永続化する CSV ファイル名。"""

  game = "trn_game.csv"
  game_player = "trn_game_player.csv"
  event = "trn_event.csv"


@dataclass(frozen=True)
class GameColumns:
  """trn_game.csv のカラム定義（仕様 6.2）。"""

  game_id = "game_id"
  date = "date"
  home_team_name = "home_team_name"
  away_team_name = "away_team_name"
  num_quarters = "num_quarters"
  quarter_minutes = "quarter_minutes"
  status = "status"
  created_at = "created_at"


GAME_COLUMNS = (
  GameColumns.game_id,
  GameColumns.date,
  GameColumns.home_team_name,
  GameColumns.away_team_name,
  GameColumns.num_quarters,
  GameColumns.quarter_minutes,
  GameColumns.status,
  GameColumns.created_at,
)


@dataclass(frozen=True)
class GamePlayerColumns:
  """trn_game_player.csv のカラム定義（仕様 6.2）。"""

  game_id = "game_id"
  player_id = "player_id"
  player_name = "player_name"
  number = "number"


GAME_PLAYER_COLUMNS = (
  GamePlayerColumns.game_id,
  GamePlayerColumns.player_id,
  GamePlayerColumns.player_name,
  GamePlayerColumns.number,
)


@dataclass(frozen=True)
class EventColumns:
  """trn_event.csv のカラム定義（仕様 6.2）。"""

  event_id = "event_id"
  game_id = "game_id"
  quarter = "quarter"
  team_side = "team_side"
  player_id = "player_id"
  event_type = "event_type"
  points = "points"
  made = "made"
  assist_player_id = "assist_player_id"
  created_at = "created_at"


EVENT_COLUMNS = (
  EventColumns.event_id,
  EventColumns.game_id,
  EventColumns.quarter,
  EventColumns.team_side,
  EventColumns.player_id,
  EventColumns.event_type,
  EventColumns.points,
  EventColumns.made,
  EventColumns.assist_player_id,
  EventColumns.created_at,
)


@dataclass(frozen=True)
class BoxScoreColumns:
  """ボックススコアの集計カラム定義（仕様 5章）。

  生スタッツ（カウント項目）と派生指標（%系）を分けて定義する。
  """

  # 識別
  player_id = "player_id"
  player_name = "player_name"
  number = "number"
  # 得点
  pts = "PTS"
  # フィールドゴール（FT を含めない）
  fgm = "FGM"
  fga = "FGA"
  # 2P
  two_pm = "2PM"
  two_pa = "2PA"
  # 3P
  three_pm = "3PM"
  three_pa = "3PA"
  # フリースロー
  ftm = "FTM"
  fta = "FTA"
  # リバウンド
  oreb = "OREB"
  dreb = "DREB"
  reb = "REB"
  # その他カウント
  ast = "AST"
  stl = "STL"
  blk = "BLK"
  to = "TO"
  pf = "PF"
  # 派生指標（%系）
  fg_pct = "FG%"
  two_p_pct = "2P%"
  three_p_pct = "3P%"
  ft_pct = "FT%"
  efg_pct = "eFG%"
  ts_pct = "TS%"


# 生スタッツ（カウント）列。チーム合計はこれらを単純合算する。
BOXSCORE_COUNT_COLUMNS = (
  BoxScoreColumns.pts,
  BoxScoreColumns.fgm,
  BoxScoreColumns.fga,
  BoxScoreColumns.two_pm,
  BoxScoreColumns.two_pa,
  BoxScoreColumns.three_pm,
  BoxScoreColumns.three_pa,
  BoxScoreColumns.ftm,
  BoxScoreColumns.fta,
  BoxScoreColumns.oreb,
  BoxScoreColumns.dreb,
  BoxScoreColumns.reb,
  BoxScoreColumns.ast,
  BoxScoreColumns.stl,
  BoxScoreColumns.blk,
  BoxScoreColumns.to,
  BoxScoreColumns.pf,
)


# 派生指標（%系）列。分母0は None（表示は「-」）。
BOXSCORE_PCT_COLUMNS = (
  BoxScoreColumns.fg_pct,
  BoxScoreColumns.two_p_pct,
  BoxScoreColumns.three_p_pct,
  BoxScoreColumns.ft_pct,
  BoxScoreColumns.efg_pct,
  BoxScoreColumns.ts_pct,
)


# ボックススコア表の表示列順（識別 → カウント → 派生指標）
BOXSCORE_COLUMNS = (
  (
    BoxScoreColumns.player_id,
    BoxScoreColumns.number,
    BoxScoreColumns.player_name,
  )
  + BOXSCORE_COUNT_COLUMNS
  + BOXSCORE_PCT_COLUMNS
)
