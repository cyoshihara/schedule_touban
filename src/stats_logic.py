"""バスケットボール スコア＆スタッツ記録アプリの集計・派生指標層（T3）。

イベント表（polars DataFrame）からボックススコアを生成する。
仕様書 docs/basketball_stats_spec.md の 5章・9章(T3) に対応。

集計項目（カウント）:
  PTS, FGM, FGA, 2PM, 2PA, 3PM, 3PA, FTM, FTA,
  OREB, DREB, REB, AST, STL, BLK, TO, PF
派生指標（%系・分母0は None=表示「-」）:
  FG%, 2P%, 3P%, FT%, eFG%, TS%

計算式（仕様 5章どおり厳守）:
  PTS  = FTM*1 + 2PM*2 + 3PM*3
  FGM  = 2PM + 3PM
  FGA  = 2PA + 3PA            （FT は含めない）
  eFG% = (FGM + 0.5*3PM) / FGA
  TS%  = PTS / (2 * (FGA + 0.44*FTA))
"""

import polars as pl

import stats_const as sc


# ---------------------------------------------------------------------------
# 内部: イベント DataFrame からカウント系の式を組み立てる
# ---------------------------------------------------------------------------
def _et(event_type: str) -> pl.Expr:
  """指定 event_type にマッチする行を示す bool 式。"""
  return pl.col(sc.EventColumns.event_type) == event_type


def _made() -> pl.Expr:
  """made == True を示す式（null は False 扱い）。"""
  return pl.col(sc.EventColumns.made).fill_null(False)


def _count_expr(condition: pl.Expr, alias: str) -> pl.Expr:
  """condition を満たす行数の合計を集計する式。"""
  return condition.cast(pl.Int64).sum().alias(alias)


# カウント系の集計式（home の選手別イベントを group_by 後に適用する）
def _count_aggregations() -> list[pl.Expr]:
  bc = sc.BoxScoreColumns
  et = sc.EventType

  two_pm = _et(et.SHOT_2PT) & _made()
  two_pa = _et(et.SHOT_2PT)
  three_pm = _et(et.SHOT_3PT) & _made()
  three_pa = _et(et.SHOT_3PT)
  ftm = _et(et.FREE_THROW) & _made()
  fta = _et(et.FREE_THROW)

  return [
    _count_expr(two_pm, bc.two_pm),
    _count_expr(two_pa, bc.two_pa),
    _count_expr(three_pm, bc.three_pm),
    _count_expr(three_pa, bc.three_pa),
    _count_expr(ftm, bc.ftm),
    _count_expr(fta, bc.fta),
    _count_expr(_et(et.REB_OFF), bc.oreb),
    _count_expr(_et(et.REB_DEF), bc.dreb),
    _count_expr(_et(et.ASSIST), bc.ast),
    _count_expr(_et(et.STEAL), bc.stl),
    _count_expr(_et(et.BLOCK), bc.blk),
    _count_expr(_et(et.TURNOVER), bc.to),
    _count_expr(_et(et.FOUL), bc.pf),
  ]


def _derived_count_columns() -> list[pl.Expr]:
  """カウント集計後に算出する派生カウント列（PTS/FGM/FGA/REB）。"""
  bc = sc.BoxScoreColumns
  return [
    (
      pl.col(bc.ftm) * 1
      + pl.col(bc.two_pm) * 2
      + pl.col(bc.three_pm) * 3
    ).alias(bc.pts),
    (pl.col(bc.two_pm) + pl.col(bc.three_pm)).alias(bc.fgm),
    (pl.col(bc.two_pa) + pl.col(bc.three_pa)).alias(bc.fga),
    (pl.col(bc.oreb) + pl.col(bc.dreb)).alias(bc.reb),
  ]


def _pct(numer: pl.Expr, denom: pl.Expr) -> pl.Expr:
  """分母0のとき None を返す割合式。"""
  return (
    pl.when(denom == 0)
    .then(None)
    .otherwise(numer / denom)
  )


def _pct_columns() -> list[pl.Expr]:
  """派生指標（%系）列。分母0は None（表示は「-」）。"""
  bc = sc.BoxScoreColumns
  fgm = pl.col(bc.fgm)
  fga = pl.col(bc.fga)
  three_pm = pl.col(bc.three_pm)
  three_pa = pl.col(bc.three_pa)
  two_pm = pl.col(bc.two_pm)
  two_pa = pl.col(bc.two_pa)
  ftm = pl.col(bc.ftm)
  fta = pl.col(bc.fta)
  pts = pl.col(bc.pts)

  return [
    _pct(fgm, fga).alias(bc.fg_pct),
    _pct(two_pm, two_pa).alias(bc.two_p_pct),
    _pct(three_pm, three_pa).alias(bc.three_p_pct),
    _pct(ftm, fta).alias(bc.ft_pct),
    _pct(fgm + 0.5 * three_pm, fga).alias(bc.efg_pct),
    _pct(pts, 2 * (fga + 0.44 * fta)).alias(bc.ts_pct),
  ]


# ---------------------------------------------------------------------------
# 公開関数
# ---------------------------------------------------------------------------
def build_player_stats(
  events: pl.DataFrame,
  players: pl.DataFrame,
) -> pl.DataFrame:
  """home チームの選手別ボックススコア（生スタッツ＋派生指標）を生成する。

  Args:
    events: trn_event 相当の DataFrame（複数試合を含んでいてもよいが、
      呼び出し側で対象試合に絞っておくこと）。
    players: trn_game_player 相当の DataFrame（player_id / player_name /
      number を含む）。登録された全選手が、イベントが無くても 0 行で
      ボックススコアに表れるよう left join のベースに使う。

  Returns:
    BOXSCORE_COLUMNS 順の DataFrame。number 昇順に並べる。
  """
  bc = sc.BoxScoreColumns
  pc = sc.GamePlayerColumns

  # home かつ player_id を持つイベントのみ選手別集計の対象
  home_events = events.filter(
    (pl.col(sc.EventColumns.team_side) == sc.TeamSide.HOME)
    & pl.col(sc.EventColumns.player_id).is_not_null()
  )

  base = players.select(
    pl.col(pc.player_id).alias(bc.player_id),
    pl.col(pc.number).alias(bc.number),
    pl.col(pc.player_name).alias(bc.player_name),
  ).unique(subset=[bc.player_id], keep="first")

  if home_events.height > 0:
    agg = home_events.group_by(
      pl.col(sc.EventColumns.player_id).alias(bc.player_id)
    ).agg(_count_aggregations())
  else:
    # イベントが無い場合は空集計（後続 join で 0 埋め）
    agg = pl.DataFrame(
      schema={bc.player_id: pl.Int64}
      | {
        name: pl.Int64
        for name in (
          bc.two_pm,
          bc.two_pa,
          bc.three_pm,
          bc.three_pa,
          bc.ftm,
          bc.fta,
          bc.oreb,
          bc.dreb,
          bc.ast,
          bc.stl,
          bc.blk,
          bc.to,
          bc.pf,
        )
      }
    )

  df = base.join(agg, on=bc.player_id, how="left")

  # イベントが無い選手のカウントは 0 埋め
  count_source_cols = [
    bc.two_pm,
    bc.two_pa,
    bc.three_pm,
    bc.three_pa,
    bc.ftm,
    bc.fta,
    bc.oreb,
    bc.dreb,
    bc.ast,
    bc.stl,
    bc.blk,
    bc.to,
    bc.pf,
  ]
  df = df.with_columns(
    [pl.col(c).fill_null(0).cast(pl.Int64) for c in count_source_cols]
  )

  # 派生カウント（PTS/FGM/FGA/REB）→ 派生指標（%系）
  df = df.with_columns(_derived_count_columns())
  df = df.with_columns(_pct_columns())

  df = df.select(list(sc.BOXSCORE_COLUMNS)).sort(bc.number)
  return df


def build_team_total(player_stats: pl.DataFrame) -> pl.DataFrame:
  """選手別ボックススコアからチーム合計行（1行）を生成する。

  カウント列は単純合算、%系は合算後のカウントから再計算する（分母0は None）。
  """
  bc = sc.BoxScoreColumns

  if player_stats.height == 0:
    totals = {c: 0 for c in sc.BOXSCORE_COUNT_COLUMNS}
  else:
    totals = {
      c: int(player_stats.select(pl.col(c).sum()).item())
      for c in sc.BOXSCORE_COUNT_COLUMNS
    }

  fgm = totals[bc.fgm]
  fga = totals[bc.fga]
  two_pm = totals[bc.two_pm]
  two_pa = totals[bc.two_pa]
  three_pm = totals[bc.three_pm]
  three_pa = totals[bc.three_pa]
  ftm = totals[bc.ftm]
  fta = totals[bc.fta]
  pts = totals[bc.pts]

  def pct(numer: float, denom: float):
    return None if denom == 0 else numer / denom

  row = {
    bc.player_id: None,
    bc.number: None,
    bc.player_name: "合計",
  }
  row.update({c: totals[c] for c in sc.BOXSCORE_COUNT_COLUMNS})
  row[bc.fg_pct] = pct(fgm, fga)
  row[bc.two_p_pct] = pct(two_pm, two_pa)
  row[bc.three_p_pct] = pct(three_pm, three_pa)
  row[bc.ft_pct] = pct(ftm, fta)
  row[bc.efg_pct] = pct(fgm + 0.5 * three_pm, fga)
  row[bc.ts_pct] = pct(pts, 2 * (fga + 0.44 * fta))

  schema = {
    bc.player_id: pl.Int64,
    bc.number: pl.Int64,
    bc.player_name: pl.Utf8,
  }
  schema |= {c: pl.Int64 for c in sc.BOXSCORE_COUNT_COLUMNS}
  schema |= {c: pl.Float64 for c in sc.BOXSCORE_PCT_COLUMNS}

  return pl.DataFrame({k: [v] for k, v in row.items()}, schema=schema).select(
    list(sc.BOXSCORE_COLUMNS)
  )


def build_boxscore(
  events: pl.DataFrame,
  players: pl.DataFrame,
) -> pl.DataFrame:
  """選手別ボックススコア＋最下行のチーム合計を結合した DataFrame を返す。"""
  player_stats = build_player_stats(events, players)
  total = build_team_total(player_stats)
  return pl.concat([player_stats, total], how="vertical")


def compute_scores(events: pl.DataFrame) -> dict:
  """両チームの合計得点を集計する。

  home: 選手別の得点イベント（SHOT_2PT/SHOT_3PT/FREE_THROW の made）から PTS を算出。
  away: AWAY_SCORE イベントの points 合計。

  Returns:
    {"home": int, "away": int}
  """
  et = sc.EventType

  home = events.filter(pl.col(sc.EventColumns.team_side) == sc.TeamSide.HOME)
  two_pm = home.filter(_et(et.SHOT_2PT) & _made()).height
  three_pm = home.filter(_et(et.SHOT_3PT) & _made()).height
  ftm = home.filter(_et(et.FREE_THROW) & _made()).height
  home_pts = ftm * 1 + two_pm * 2 + three_pm * 3

  away = events.filter(_et(et.AWAY_SCORE))
  if away.height == 0:
    away_pts = 0
  else:
    away_pts = int(away.select(pl.col(sc.EventColumns.points).sum()).item())

  return {sc.TeamSide.HOME: int(home_pts), sc.TeamSide.AWAY: int(away_pts)}


def compute_team_fouls_by_quarter(events: pl.DataFrame) -> pl.DataFrame:
  """クォーター別・チーム別のチームファウル数を集計する。

  FOUL イベント（home の選手ファウル）をチームファウルとして算入する。
  AWAY 側の FOUL も記録があれば team_side ごとに集計する。

  Returns:
    columns: quarter, team_side, team_fouls（quarter, team_side 昇順）
  """
  fouls = events.filter(_et(sc.EventType.FOUL))
  if fouls.height == 0:
    return pl.DataFrame(
      schema={
        sc.EventColumns.quarter: pl.Int64,
        sc.EventColumns.team_side: pl.Utf8,
        "team_fouls": pl.Int64,
      }
    )

  return (
    fouls.group_by(
      [sc.EventColumns.quarter, sc.EventColumns.team_side]
    )
    .agg(pl.len().cast(pl.Int64).alias("team_fouls"))
    .sort([sc.EventColumns.quarter, sc.EventColumns.team_side])
  )


def is_bonus(
  team_fouls: int,
  threshold: int = sc.GameDefault.team_foul_bonus_threshold,
) -> bool:
  """チームファウル数がボーナス閾値に達しているか判定する。"""
  return team_fouls >= threshold
