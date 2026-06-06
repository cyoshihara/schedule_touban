"""集計・派生指標層（stats_logic, T3）の単体テスト。

仕様 10章「受け入れ基準」3〜12 のうち、ロジックで検証可能なものを
イベント DataFrame を直接構築して検証する。
"""

import math

import polars as pl
import pytest

import stats_const as sc
import stats_logic as sl


# ---------------------------------------------------------------------------
# ヘルパー: イベント / 選手 DataFrame を組み立てる
# ---------------------------------------------------------------------------
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

_PLAYER_SCHEMA = {
  sc.GamePlayerColumns.game_id: pl.Int64,
  sc.GamePlayerColumns.player_id: pl.Int64,
  sc.GamePlayerColumns.player_name: pl.Utf8,
  sc.GamePlayerColumns.number: pl.Int64,
}


def make_events(rows):
  """rows: list[dict]（部分指定可）から event DataFrame を作る。"""
  records = []
  for i, r in enumerate(rows, start=1):
    rec = {
      sc.EventColumns.event_id: r.get(sc.EventColumns.event_id, i),
      sc.EventColumns.game_id: r.get(sc.EventColumns.game_id, 1),
      sc.EventColumns.quarter: r.get(sc.EventColumns.quarter, 1),
      sc.EventColumns.team_side: r.get(sc.EventColumns.team_side, sc.TeamSide.HOME),
      sc.EventColumns.player_id: r.get(sc.EventColumns.player_id),
      sc.EventColumns.event_type: r[sc.EventColumns.event_type],
      sc.EventColumns.points: r.get(sc.EventColumns.points, 0),
      sc.EventColumns.made: r.get(sc.EventColumns.made),
      sc.EventColumns.assist_player_id: r.get(sc.EventColumns.assist_player_id),
      sc.EventColumns.created_at: r.get(sc.EventColumns.created_at, "2026-06-06T00:00:00"),
    }
    records.append(rec)
  if not records:
    return pl.DataFrame(schema=_EVENT_SCHEMA)
  return pl.DataFrame(records, schema=_EVENT_SCHEMA)


def make_players(rows):
  """rows: list[(player_id, number, name)]。"""
  return pl.DataFrame(
    {
      sc.GamePlayerColumns.game_id: [1] * len(rows),
      sc.GamePlayerColumns.player_id: [r[0] for r in rows],
      sc.GamePlayerColumns.player_name: [r[2] for r in rows],
      sc.GamePlayerColumns.number: [r[1] for r in rows],
    },
    schema=_PLAYER_SCHEMA,
  )


def _shot(et, made, pid=1, side=sc.TeamSide.HOME, quarter=1, points=0):
  return {
    sc.EventColumns.event_type: et,
    sc.EventColumns.made: made,
    sc.EventColumns.player_id: pid,
    sc.EventColumns.team_side: side,
    sc.EventColumns.quarter: quarter,
    sc.EventColumns.points: points,
  }


def stat_of(box, pid, col):
  """選手 pid の col 値を取り出す。"""
  return box.filter(pl.col(sc.BoxScoreColumns.player_id) == pid).select(col).item()


# ---------------------------------------------------------------------------
# 受け入れ基準 3: 得点集計
# ---------------------------------------------------------------------------
def test_score_aggregation_2p_and_3p():
  events = make_events([
    _shot(sc.EventType.SHOT_2PT, True),
    _shot(sc.EventType.SHOT_3PT, True),
  ])
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  assert stat_of(box, 1, bc.pts) == 5
  assert stat_of(box, 1, bc.fgm) == 2
  assert stat_of(box, 1, bc.fga) == 2
  assert stat_of(box, 1, bc.three_pm) == 1
  assert stat_of(box, 1, bc.three_pa) == 1
  assert stat_of(box, 1, bc.two_pm) == 1
  assert stat_of(box, 1, bc.two_pa) == 1

  scores = sl.compute_scores(events)
  assert scores[sc.TeamSide.HOME] == 5
  assert scores[sc.TeamSide.AWAY] == 0


# 受け入れ基準 4: 失敗の反映
def test_missed_shot_increments_attempts_only():
  events = make_events([
    _shot(sc.EventType.SHOT_2PT, True),
    _shot(sc.EventType.SHOT_2PT, False),
  ])
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  assert stat_of(box, 1, bc.fgm) == 1
  assert stat_of(box, 1, bc.fga) == 2
  assert stat_of(box, 1, bc.pts) == 2


# 受け入れ基準 5: FT 集計
def test_free_throw_aggregation():
  events = make_events([
    _shot(sc.EventType.FREE_THROW, True),
    _shot(sc.EventType.FREE_THROW, True),
    _shot(sc.EventType.FREE_THROW, False),
  ])
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  assert stat_of(box, 1, bc.ftm) == 2
  assert stat_of(box, 1, bc.fta) == 3
  assert stat_of(box, 1, bc.pts) == 2
  # FT は FG に含めない
  assert stat_of(box, 1, bc.fga) == 0
  assert stat_of(box, 1, bc.fgm) == 0


# 受け入れ基準 6: リバウンド O/D 区別
def test_rebound_off_def_distinct():
  events = make_events([
    {sc.EventColumns.event_type: sc.EventType.REB_OFF, sc.EventColumns.player_id: 1},
    {sc.EventColumns.event_type: sc.EventType.REB_OFF, sc.EventColumns.player_id: 1},
    {sc.EventColumns.event_type: sc.EventType.REB_DEF, sc.EventColumns.player_id: 1},
  ])
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  assert stat_of(box, 1, bc.oreb) == 2
  assert stat_of(box, 1, bc.dreb) == 1
  assert stat_of(box, 1, bc.reb) == 3


# 受け入れ基準 7: 派生指標 + ゼロ除算は None（-）
def test_derived_percentages():
  # 2P 1/2, 3P 1/1, FT 1/2
  events = make_events([
    _shot(sc.EventType.SHOT_2PT, True),
    _shot(sc.EventType.SHOT_2PT, False),
    _shot(sc.EventType.SHOT_3PT, True),
    _shot(sc.EventType.FREE_THROW, True),
    _shot(sc.EventType.FREE_THROW, False),
  ])
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  # FGM=2, FGA=3, 3PM=1, FTM=1, FTA=2, PTS=2+3+1=... 2P 1*2 + 3P 1*3 + FT 1 = 6
  assert stat_of(box, 1, bc.pts) == 6
  assert math.isclose(stat_of(box, 1, bc.fg_pct), 2 / 3)
  assert math.isclose(stat_of(box, 1, bc.two_p_pct), 1 / 2)
  assert math.isclose(stat_of(box, 1, bc.three_p_pct), 1 / 1)
  assert math.isclose(stat_of(box, 1, bc.ft_pct), 1 / 2)
  # eFG% = (FGM + 0.5*3PM) / FGA = (2 + 0.5) / 3
  assert math.isclose(stat_of(box, 1, bc.efg_pct), (2 + 0.5) / 3)
  # TS% = PTS / (2*(FGA + 0.44*FTA)) = 6 / (2*(3 + 0.88))
  assert math.isclose(stat_of(box, 1, bc.ts_pct), 6 / (2 * (3 + 0.44 * 2)))


def test_zero_denominator_percentages_are_none():
  # シュートを一切打たない選手
  events = make_events([
    {sc.EventColumns.event_type: sc.EventType.STEAL, sc.EventColumns.player_id: 1},
  ])
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  assert stat_of(box, 1, bc.fg_pct) is None
  assert stat_of(box, 1, bc.two_p_pct) is None
  assert stat_of(box, 1, bc.three_p_pct) is None
  assert stat_of(box, 1, bc.ft_pct) is None
  assert stat_of(box, 1, bc.efg_pct) is None
  assert stat_of(box, 1, bc.ts_pct) is None
  assert stat_of(box, 1, bc.stl) == 1


# 受け入れ基準 8: undo 後の再集計（ロジック側: イベントが減れば集計も戻る）
def test_undo_reflected_in_aggregation():
  full = make_events([
    _shot(sc.EventType.SHOT_2PT, True),
    _shot(sc.EventType.SHOT_3PT, True),
  ])
  players = make_players([(1, 4, "A")])
  assert sl.compute_scores(full)[sc.TeamSide.HOME] == 5

  # 最終イベント(3P)を取り消した状態
  undone = full.filter(pl.col(sc.EventColumns.event_id) != 2)
  box = sl.build_player_stats(undone, players)
  assert stat_of(box, 1, sc.BoxScoreColumns.pts) == 2
  assert sl.compute_scores(undone)[sc.TeamSide.HOME] == 2


# 受け入れ基準 9: チームファウル（クォーター別集計）
def test_team_fouls_by_quarter():
  events = make_events([
    {sc.EventColumns.event_type: sc.EventType.FOUL, sc.EventColumns.player_id: 1, sc.EventColumns.quarter: 1},
    {sc.EventColumns.event_type: sc.EventType.FOUL, sc.EventColumns.player_id: 2, sc.EventColumns.quarter: 1},
    {sc.EventColumns.event_type: sc.EventType.FOUL, sc.EventColumns.player_id: 1, sc.EventColumns.quarter: 2},
  ])
  tf = sl.compute_team_fouls_by_quarter(events)

  q1 = tf.filter(
    (pl.col(sc.EventColumns.quarter) == 1)
    & (pl.col(sc.EventColumns.team_side) == sc.TeamSide.HOME)
  ).select("team_fouls").item()
  q2 = tf.filter(
    (pl.col(sc.EventColumns.quarter) == 2)
    & (pl.col(sc.EventColumns.team_side) == sc.TeamSide.HOME)
  ).select("team_fouls").item()
  assert q1 == 2
  assert q2 == 1


def test_is_bonus_threshold():
  assert sl.is_bonus(5) is True
  assert sl.is_bonus(4) is False
  assert sl.is_bonus(6) is True


# 受け入れ基準 10: 相手得点
def test_away_score():
  events = make_events([
    _shot(sc.EventType.SHOT_2PT, True),  # home 2
    {
      sc.EventColumns.event_type: sc.EventType.AWAY_SCORE,
      sc.EventColumns.team_side: sc.TeamSide.AWAY,
      sc.EventColumns.points: 2,
    },
    {
      sc.EventColumns.event_type: sc.EventType.AWAY_SCORE,
      sc.EventColumns.team_side: sc.TeamSide.AWAY,
      sc.EventColumns.points: 3,
    },
  ])
  scores = sl.compute_scores(events)
  assert scores[sc.TeamSide.HOME] == 2
  assert scores[sc.TeamSide.AWAY] == 5

  # 自チームスタッツは away 得点の影響を受けない
  players = make_players([(1, 4, "A")])
  box = sl.build_player_stats(events, players)
  assert stat_of(box, 1, sc.BoxScoreColumns.pts) == 2
  assert box.height == 1  # away 行は選手別ボックスに出ない


# 受け入れ基準 12: チーム合計 = 各選手合計
def test_team_total_matches_player_sum():
  events = make_events([
    _shot(sc.EventType.SHOT_2PT, True, pid=1),
    _shot(sc.EventType.SHOT_3PT, True, pid=2),
    _shot(sc.EventType.FREE_THROW, True, pid=1),
    {sc.EventColumns.event_type: sc.EventType.REB_DEF, sc.EventColumns.player_id: 2},
  ])
  players = make_players([(1, 4, "A"), (2, 5, "B")])
  box = sl.build_boxscore(events, players)
  bc = sc.BoxScoreColumns

  total = box.filter(pl.col(bc.player_name) == "合計")
  assert total.height == 1
  assert total.select(bc.pts).item() == 6  # 2 + 3 + 1
  assert total.select(bc.fgm).item() == 2
  assert total.select(bc.reb).item() == 1

  # 各カウント列の合計 = 選手別合計
  player_rows = box.filter(pl.col(bc.player_name) != "合計")
  for col in sc.BOXSCORE_COUNT_COLUMNS:
    assert total.select(col).item() == player_rows.select(pl.col(col).sum()).item()


def test_player_without_events_appears_with_zeros():
  events = make_events([
    _shot(sc.EventType.SHOT_2PT, True, pid=1),
  ])
  players = make_players([(1, 4, "A"), (2, 5, "B")])
  box = sl.build_player_stats(events, players)
  bc = sc.BoxScoreColumns

  assert box.height == 2
  assert stat_of(box, 2, bc.pts) == 0
  assert stat_of(box, 2, bc.fga) == 0
  assert stat_of(box, 2, bc.fg_pct) is None
