"""バスケットボール スコア＆スタッツ記録アプリの Streamlit UI（T4〜T8）。

仕様書 docs/basketball_stats_spec.md の 7章（画面/UX設計）に対応。

画面構成（st.session_state.page で切替）:
  - home     : 試合一覧・新規作成入口・既存試合の再開/閲覧（T8）
  - create   : 新規試合作成＋出場選手登録（T4）
  - record   : 記録画面（得点/スタッツ/相手得点/Undo/Q進行）（T5, T6）
  - boxscore : ボックススコア表示・CSVエクスポート（T7）

ロジック/I/O は既存 3 モジュール（stats_const / stats_models / stats_logic）
の関数を呼ぶだけにし、集計ロジックを UI 側に再実装しない。
"""

from datetime import date

import polars as pl
import streamlit as st

import stats_const as sc
import stats_logic as logic
import stats_models as models


# 永続化先（既存 const.DIR_TEMP と同じ ./tmp 配下）
DATA_DIR = sc.DIR_TEMP


# ---------------------------------------------------------------------------
# session_state 初期化
# ---------------------------------------------------------------------------
def _init_state() -> None:
  """画面遷移・現在試合・選択選手・現在Qを session_state に保持する。"""
  defaults = {
    "page": "home",
    "game_id": None,
    "current_quarter": 1,
    "selected_player_id": None,
  }
  for key, value in defaults.items():
    if key not in st.session_state:
      st.session_state[key] = value


def _goto(page: str, game_id: int | None = None) -> None:
  """画面遷移ヘルパ。game_id 指定時は対象試合に切替え、選択選手をリセット。"""
  st.session_state.page = page
  if game_id is not None:
    st.session_state.game_id = game_id
    st.session_state.selected_player_id = None
    st.session_state.current_quarter = _resume_quarter(game_id)


def _resume_quarter(game_id: int) -> int:
  """再開時の現在クォーターを、記録済みイベントの最大 quarter から復元する。

  current_quarter は session_state のみ保持で永続化されないため、途中再開や
  リロードで巻き戻らないよう、保存済みイベントの最大Qを採用する（無ければ1）。
  """
  events = models.read_events_by_game(game_id, DATA_DIR)
  if events.height == 0:
    return 1
  return int(events[sc.EventColumns.quarter].max())


# ---------------------------------------------------------------------------
# 共通ユーティリティ
# ---------------------------------------------------------------------------
def _get_game(game_id: int) -> dict | None:
  """game_id の試合レコードを dict で返す（無ければ None）。"""
  games = models.read_games(DATA_DIR)
  row = games.filter(pl.col(sc.GameColumns.game_id) == game_id)
  if row.height == 0:
    return None
  return row.row(0, named=True)


def _player_label(players: pl.DataFrame, player_id: int | None) -> str:
  """player_id から「#背番号 氏名」の表示ラベルを作る。"""
  if player_id is None:
    return "（選手なし）"
  row = players.filter(pl.col(sc.GamePlayerColumns.player_id) == player_id)
  if row.height == 0:
    return f"player_id={player_id}"
  r = row.row(0, named=True)
  return f"#{r[sc.GamePlayerColumns.number]} {r[sc.GamePlayerColumns.player_name]}"


# 直近イベントログ用: event_type → 日本語ラベル
_EVENT_LABELS = {
  (sc.EventType.SHOT_2PT, True): "2P成功",
  (sc.EventType.SHOT_2PT, False): "2P失敗",
  (sc.EventType.SHOT_3PT, True): "3P成功",
  (sc.EventType.SHOT_3PT, False): "3P失敗",
  (sc.EventType.FREE_THROW, True): "FT成功",
  (sc.EventType.FREE_THROW, False): "FT失敗",
  sc.EventType.REB_OFF: "OREB",
  sc.EventType.REB_DEF: "DREB",
  sc.EventType.ASSIST: "AST",
  sc.EventType.STEAL: "STL",
  sc.EventType.BLOCK: "BLK",
  sc.EventType.TURNOVER: "TO",
  sc.EventType.FOUL: "FOUL",
  sc.EventType.AWAY_SCORE: "相手得点",
}


def _event_label(event_type: str, made) -> str:
  """イベント1件の表示ラベル（Undo ボタン・ログ表示で使う）。"""
  key = (event_type, bool(made)) if made is not None else None
  if key in _EVENT_LABELS:
    return _EVENT_LABELS[key]
  return _EVENT_LABELS.get(event_type, event_type)


# ---------------------------------------------------------------------------
# ホーム / 試合一覧（T8）
# ---------------------------------------------------------------------------
def page_home() -> None:
  st.write("## ホーム / 試合一覧")

  if st.button("＋ 新規試合を作成", type="primary", use_container_width=True):
    _goto("create")
    st.rerun()

  st.divider()
  st.write("### 過去の試合")

  games = models.read_games(DATA_DIR)
  if games.height == 0:
    st.info("まだ試合がありません。「新規試合を作成」から始めてください。")
    return

  events_all = models.read_events(DATA_DIR)
  # 新しい試合を上に表示
  games = games.sort(sc.GameColumns.game_id, descending=True)
  for g in games.iter_rows(named=True):
    gid = g[sc.GameColumns.game_id]
    g_events = events_all.filter(pl.col(sc.EventColumns.game_id) == gid)
    scores = logic.compute_scores(g_events)
    home = g[sc.GameColumns.home_team_name]
    away = g[sc.GameColumns.away_team_name]

    with st.container(border=True):
      st.write(
        f"**#{gid}** {g[sc.GameColumns.date]}　"
        f"{home} {scores[sc.TeamSide.HOME]} - "
        f"{scores[sc.TeamSide.AWAY]} {away}　"
        f"({g[sc.GameColumns.status]})"
      )
      col_rec, col_box = st.columns(2)
      with col_rec:
        if st.button("記録を続ける", key=f"rec_{gid}", use_container_width=True):
          _goto("record", game_id=gid)
          st.rerun()
      with col_box:
        if st.button("ボックススコア", key=f"box_{gid}", use_container_width=True):
          _goto("boxscore", game_id=gid)
          st.rerun()


# ---------------------------------------------------------------------------
# 新規試合作成・選手登録（T4）
# ---------------------------------------------------------------------------
def page_create() -> None:
  st.write("## 新規試合作成")
  if st.button("← ホームへ戻る"):
    _goto("home")
    st.rerun()

  with st.form("create_game_form"):
    st.write("### 試合情報")
    home_team = st.text_input("自チーム名", value="自チーム")
    away_team = st.text_input("相手チーム名", value="相手チーム")
    game_date = st.date_input("試合日", value=date.today())
    col_q, col_m = st.columns(2)
    with col_q:
      num_quarters = st.number_input(
        "クォーター数",
        min_value=1,
        max_value=12,
        value=sc.GameDefault.num_quarters,
        step=1,
      )
    with col_m:
      quarter_minutes = st.number_input(
        "1クォーターの分数",
        min_value=1,
        max_value=60,
        value=sc.GameDefault.quarter_minutes,
        step=1,
      )

    st.write("### 出場選手（背番号・氏名）")
    st.caption("行を追加して登録してください（最終行で Enter / + で追加）。")
    empty_players = pl.DataFrame(
      schema={
        sc.GamePlayerColumns.number: pl.Int64,
        sc.GamePlayerColumns.player_name: pl.Utf8,
      }
    )
    edited = st.data_editor(
      empty_players,
      num_rows="dynamic",
      use_container_width=True,
      column_config={
        sc.GamePlayerColumns.number: st.column_config.NumberColumn(
          "背番号", min_value=0, step=1
        ),
        sc.GamePlayerColumns.player_name: st.column_config.TextColumn("氏名"),
      },
      key="player_editor",
    )

    submitted = st.form_submit_button("試合を作成", type="primary")

  if submitted:
    if not home_team.strip() or not away_team.strip():
      st.error("自チーム名・相手チーム名を入力してください。")
      return

    players = []
    for r in edited.iter_rows(named=True):
      number = r[sc.GamePlayerColumns.number]
      name = r[sc.GamePlayerColumns.player_name]
      if name is None or str(name).strip() == "":
        continue
      players.append(
        {
          sc.GamePlayerColumns.player_name: str(name).strip(),
          sc.GamePlayerColumns.number: int(number) if number is not None else 0,
        }
      )

    if len(players) == 0:
      st.error("出場選手を1人以上登録してください。")
      return

    game_id = models.create_game(
      date=str(game_date),
      home_team_name=home_team.strip(),
      away_team_name=away_team.strip(),
      num_quarters=int(num_quarters),
      quarter_minutes=int(quarter_minutes),
      data_dir=DATA_DIR,
    )
    models.register_players(game_id, players, data_dir=DATA_DIR)
    st.success(f"試合 #{game_id} を作成しました。記録画面へ移動します。")
    _goto("record", game_id=game_id)
    st.rerun()


# ---------------------------------------------------------------------------
# 記録画面（T5, T6）
# ---------------------------------------------------------------------------
def _record_event(event_type: str, **kwargs) -> None:
  """イベントを1件追記して即時 rerun する（オートセーブ）。"""
  game_id = st.session_state.game_id
  quarter = st.session_state.current_quarter
  models.append_event(
    game_id=game_id,
    quarter=quarter,
    event_type=event_type,
    data_dir=DATA_DIR,
    **kwargs,
  )
  st.rerun()


def _scoreboard(game: dict, events: pl.DataFrame) -> None:
  """上部スコアボード: スコア・現在Q・両チームのチームファウル（ボーナス）。"""
  scores = logic.compute_scores(events)
  home = game[sc.GameColumns.home_team_name]
  away = game[sc.GameColumns.away_team_name]
  quarter = st.session_state.current_quarter

  col_h, col_mid, col_a = st.columns([2, 1, 2])
  with col_h:
    st.metric(home, scores[sc.TeamSide.HOME])
  with col_mid:
    st.metric("Q", f"{quarter} / {game[sc.GameColumns.num_quarters]}")
  with col_a:
    st.metric(away, scores[sc.TeamSide.AWAY])

  # 現在Qのチームファウル（home/away）
  fouls = logic.compute_team_fouls_by_quarter(events)
  q_fouls = fouls.filter(pl.col(sc.EventColumns.quarter) == quarter)

  def _foul_count(side: str) -> int:
    row = q_fouls.filter(pl.col(sc.EventColumns.team_side) == side)
    if row.height == 0:
      return 0
    return int(row.select(pl.col("team_fouls").sum()).item())

  home_fouls = _foul_count(sc.TeamSide.HOME)
  away_fouls = _foul_count(sc.TeamSide.AWAY)

  col_hf, col_af = st.columns(2)
  with col_hf:
    bonus = " 🔴ボーナス" if logic.is_bonus(home_fouls) else ""
    st.write(f"{home} チームファウル(Q{quarter}): **{home_fouls}**{bonus}")
  with col_af:
    bonus = " 🔴ボーナス" if logic.is_bonus(away_fouls) else ""
    st.write(f"{away} チームファウル(Q{quarter}): **{away_fouls}**{bonus}")


def _player_grid(players: pl.DataFrame) -> None:
  """背番号ボタンのグリッド。選択中選手をハイライト（primary 表示）。"""
  st.write("#### 選手を選択")
  selected = st.session_state.selected_player_id
  players = players.sort(sc.GamePlayerColumns.number)
  rows = list(players.iter_rows(named=True))

  cols_per_row = 4
  for i in range(0, len(rows), cols_per_row):
    chunk = rows[i : i + cols_per_row]
    cols = st.columns(cols_per_row)
    for col, r in zip(cols, chunk):
      pid = r[sc.GamePlayerColumns.player_id]
      label = f"#{r[sc.GamePlayerColumns.number]} {r[sc.GamePlayerColumns.player_name]}"
      is_sel = pid == selected
      with col:
        if st.button(
          label,
          key=f"psel_{pid}",
          type="primary" if is_sel else "secondary",
          use_container_width=True,
        ):
          st.session_state.selected_player_id = pid
          st.rerun()


def _action_buttons(players: pl.DataFrame) -> None:
  """選択中選手に対する得点系・スタッツ系アクションボタン群。"""
  pid = st.session_state.selected_player_id
  if pid is None:
    st.info("先に選手を選択してください。")
    return

  st.write(f"#### アクション（{_player_label(players, pid)}）")

  # 得点系
  st.caption("得点")
  shot_defs = [
    ("2P◯", sc.EventType.SHOT_2PT, True, 2),
    ("2P✕", sc.EventType.SHOT_2PT, False, 0),
    ("3P◯", sc.EventType.SHOT_3PT, True, 3),
    ("3P✕", sc.EventType.SHOT_3PT, False, 0),
    ("FT◯", sc.EventType.FREE_THROW, True, 1),
    ("FT✕", sc.EventType.FREE_THROW, False, 0),
  ]
  cols = st.columns(len(shot_defs))
  for col, (label, etype, made, pts) in zip(cols, shot_defs):
    with col:
      if st.button(label, key=f"act_{label}", use_container_width=True):
        _record_event(
          etype,
          player_id=pid,
          team_side=sc.TeamSide.HOME,
          made=made,
          points=pts,
        )

  # スタッツ系
  st.caption("スタッツ")
  stat_defs = [
    ("OREB", sc.EventType.REB_OFF),
    ("DREB", sc.EventType.REB_DEF),
    ("AST", sc.EventType.ASSIST),
    ("STL", sc.EventType.STEAL),
    ("BLK", sc.EventType.BLOCK),
    ("TO", sc.EventType.TURNOVER),
    ("FOUL", sc.EventType.FOUL),
  ]
  cols = st.columns(len(stat_defs))
  for col, (label, etype) in zip(cols, stat_defs):
    with col:
      if st.button(label, key=f"act_{label}", use_container_width=True):
        _record_event(
          etype,
          player_id=pid,
          team_side=sc.TeamSide.HOME,
        )


def _away_score_buttons() -> None:
  """相手チームの得点ボタン（AWAY_SCORE イベント）。"""
  st.write("#### 相手得点")
  cols = st.columns(3)
  for col, pts in zip(cols, (1, 2, 3)):
    with col:
      if st.button(f"相手 +{pts}", key=f"away_{pts}", use_container_width=True):
        _record_event(
          sc.EventType.AWAY_SCORE,
          player_id=None,
          team_side=sc.TeamSide.AWAY,
          points=pts,
        )


def _undo_and_quarter(game: dict, events: pl.DataFrame, players: pl.DataFrame) -> None:
  """常時表示の Undo ボタンとクォーター進行ボタン。"""
  col_undo, col_q = st.columns(2)

  # Undo: 直前イベント種別を表示
  with col_undo:
    if events.height > 0:
      last = events.sort(sc.EventColumns.event_id).row(-1, named=True)
      last_label = _event_label(
        last[sc.EventColumns.event_type], last[sc.EventColumns.made]
      )
      last_pid = last[sc.EventColumns.player_id]
      who = (
        _player_label(players, last_pid)
        if last_pid is not None
        else game[sc.GameColumns.away_team_name]
      )
      if st.button(
        f"↩ 取り消す（直前: {last_label} / {who}）", use_container_width=True
      ):
        models.delete_last_event(st.session_state.game_id, data_dir=DATA_DIR)
        st.rerun()
    else:
      st.button("↩ 取り消す（履歴なし）", disabled=True, use_container_width=True)

  # クォーター進行
  with col_q:
    cur = st.session_state.current_quarter
    max_q = int(game[sc.GameColumns.num_quarters])
    if st.button(
      "次のQへ ▶",
      disabled=cur >= max_q,
      use_container_width=True,
    ):
      st.session_state.current_quarter = min(cur + 1, max_q)
      st.rerun()


def _recent_events_log(events: pl.DataFrame, players: pl.DataFrame, game: dict) -> None:
  """直近イベントログ（最新5件）を表示する。"""
  st.write("#### 直近イベント（最新5件）")
  if events.height == 0:
    st.caption("まだイベントがありません。")
    return

  recent = events.sort(sc.EventColumns.event_id, descending=True).head(5)
  lines = []
  for r in recent.iter_rows(named=True):
    label = _event_label(r[sc.EventColumns.event_type], r[sc.EventColumns.made])
    pid = r[sc.EventColumns.player_id]
    who = (
      _player_label(players, pid)
      if pid is not None
      else game[sc.GameColumns.away_team_name]
    )
    lines.append(
      f"- Q{r[sc.EventColumns.quarter]} | {label} | {who}"
    )
  st.markdown("\n".join(lines))


def page_record() -> None:
  game_id = st.session_state.game_id
  game = _get_game(game_id)
  if game is None:
    st.error("試合が見つかりません。")
    if st.button("← ホームへ"):
      _goto("home")
      st.rerun()
    return

  col_back, col_box = st.columns(2)
  with col_back:
    if st.button("← ホーム", use_container_width=True):
      _goto("home")
      st.rerun()
  with col_box:
    if st.button("ボックススコアを見る", use_container_width=True):
      _goto("boxscore", game_id=game_id)
      st.rerun()

  events = models.read_events_by_game(game_id, DATA_DIR)
  players = models.read_game_players_by_game(game_id, DATA_DIR)

  _scoreboard(game, events)
  st.divider()
  _undo_and_quarter(game, events, players)
  st.divider()
  _player_grid(players)
  st.divider()
  _action_buttons(players)
  st.divider()
  _away_score_buttons()
  st.divider()
  _recent_events_log(events, players, game)


# ---------------------------------------------------------------------------
# ボックススコア画面（T7）
# ---------------------------------------------------------------------------
def _format_boxscore_for_display(box: pl.DataFrame) -> pl.DataFrame:
  """表示用に整形: player_id 列を除外し、%系の None を「-」表示にする。

  %は 0〜1 の小数で保持しているため、パーセント文字列に整形する。
  """
  bc = sc.BoxScoreColumns
  # player_id は非表示
  display_cols = [c for c in sc.BOXSCORE_COLUMNS if c != bc.player_id]

  exprs = []
  for c in display_cols:
    if c in sc.BOXSCORE_PCT_COLUMNS:
      exprs.append(
        pl.when(pl.col(c).is_null())
        .then(pl.lit("-"))
        .otherwise((pl.col(c) * 100).round(1).cast(pl.Utf8) + "%")
        .alias(c)
      )
    elif c == bc.number:
      exprs.append(
        pl.when(pl.col(c).is_null())
        .then(pl.lit(""))
        .otherwise(pl.col(c).cast(pl.Utf8))
        .alias(c)
      )
    else:
      exprs.append(pl.col(c))

  return box.select(display_cols).with_columns(exprs)


def page_boxscore() -> None:
  game_id = st.session_state.game_id
  game = _get_game(game_id)
  if game is None:
    st.error("試合が見つかりません。")
    if st.button("← ホームへ"):
      _goto("home")
      st.rerun()
    return

  st.write("## ボックススコア")
  col_back, col_rec = st.columns(2)
  with col_back:
    if st.button("← ホーム", use_container_width=True):
      _goto("home")
      st.rerun()
  with col_rec:
    if st.button("記録画面へ", use_container_width=True):
      _goto("record", game_id=game_id)
      st.rerun()

  events = models.read_events_by_game(game_id, DATA_DIR)
  players = models.read_game_players_by_game(game_id, DATA_DIR)

  scores = logic.compute_scores(events)
  st.write(
    f"### {game[sc.GameColumns.home_team_name]} "
    f"{scores[sc.TeamSide.HOME]} - {scores[sc.TeamSide.AWAY]} "
    f"{game[sc.GameColumns.away_team_name]}"
  )

  box = logic.build_boxscore(events, players)
  display = _format_boxscore_for_display(box)
  st.dataframe(display, use_container_width=True, hide_index=True)

  # CSV ダウンロード（F12）: 集計値そのまま（player_id 除外）。
  csv_cols = [c for c in sc.BOXSCORE_COLUMNS if c != sc.BoxScoreColumns.player_id]
  csv_bytes = box.select(csv_cols).write_csv().encode("utf-8-sig")
  st.download_button(
    "CSV をダウンロード",
    data=csv_bytes,
    file_name=f"boxscore_game{game_id}.csv",
    mime="text/csv",
  )


# ---------------------------------------------------------------------------
# エントリ
# ---------------------------------------------------------------------------
def main() -> None:
  st.set_page_config(page_title="バスケ スコア＆スタッツ", layout="wide")
  models.init_storage(DATA_DIR)
  _init_state()

  st.write("# 🏀 バスケ スコア＆スタッツ記録")

  page = st.session_state.page
  if page == "home":
    page_home()
  elif page == "create":
    page_create()
  elif page == "record":
    page_record()
  elif page == "boxscore":
    page_boxscore()
  else:
    st.session_state.page = "home"
    page_home()


if __name__ == "__main__":
  main()
