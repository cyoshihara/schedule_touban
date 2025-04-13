import polars as pl
import pulp
import numpy as np
import os

from utils import get_current_fiscal_year
import utils
import const

def optimize(dir, df_input, df_trn_touban, cutoff_threshold, gds:utils.GoogleDriveService):
  fpath_mst_day = os.path.join(dir, "mst_day.csv")
  fpath_mst_member = os.path.join(dir, "mst_member.csv")
  fpath_mst_parent = os.path.join(dir, "mst_parent.csv")
  fpath_mst_grade_category = os.path.join(dir, "mst_grade_category.csv")

  if os.path.isfile(fpath_mst_day) is False:
      fpath_mst_day = gds.download_file(const.FileID.mst_day)
  if os.path.isfile(fpath_mst_member) is False:
      fpath_mst_member = gds.download_file(const.FileID.mst_member)
  if os.path.isfile(fpath_mst_parent) is False:
      df_mst_parent = gds.download_file(const.FileID.mst_parent)
  if os.path.isfile(fpath_mst_grade_category) is False:
      df_mst_grade_category = gds.download_file(const.FileID.mst_grade_category)

  df_mst_day = pl.read_csv(fpath_mst_day)
  df_mst_member = pl.read_csv(fpath_mst_member)
  df_mst_parent = pl.read_csv(fpath_mst_parent, try_parse_dates=True)
  df_mst_grade_category = pl.read_csv(fpath_mst_grade_category)

  # --------------------------------------------------
  # 入力の整形
  # --------------------------------------------------
  def add_start_end_duration(df_input):
    df_input = df_input.with_columns( pl.col("time").str.split("~") )
    df_input = df_input.with_columns( [
      pl.col("time").list.get(0).alias("start_time"),
      pl.col("time").list.get(1).alias("end_time")
      ]).drop("time")
    df_input = df_input.with_columns(
      pl.col("start_time").str.strptime(pl.Time, format="%H:%M"),
      pl.col("end_time").str.strptime(pl.Time, format="%H:%M")
    )
    df_input = df_input.with_columns([
        (pl.datetime(1970, 1, 1) + pl.col("start_time").cast(pl.Duration)).alias("start_datetime"),
        (pl.datetime(1970, 1, 1) + pl.col("end_time").cast(pl.Duration)).alias("end_datetime"),
    ])
    df_input = df_input.with_columns(
        (pl.col("end_datetime") - pl.col("start_datetime")).alias("duration")
    )
    print(df_input)
    df_input = df_input.select([
      "event_id",
      "year",
      "month",
      "day",
      "youbi",
      "start_time",
      "end_time",
      "duration",
      "place",
      "need_touban",
      "m_cat",
      "f_cat",
      "m_und",
      "m_mid",
      "m_top",
      "m_1",
      "m_2",
      "m_3",
      "m_4",
      "m_5",
      "m_6",
      "f_und",
      "f_mid",
      "f_top",
      "f_1",
      "f_2",
      "f_3",
      "f_4",
      "f_5",
      "f_6"
    ])
    return df_input

  df_input = add_start_end_duration(df_input)

  # STAFFを除く
  df_mst_parent = df_mst_parent.filter( pl.col("staff") == 0 )
  # 当番が必要な日に限定
  df_input_org = df_input.clone()
  df_input = df_input.filter(pl.col("need_touban") == 1 )
  # 曜日をIDに変更
  day_map = dict(zip(df_mst_day["day_name"], df_mst_day["day_id"]))
  df_input = df_input.join(df_mst_day, left_on="youbi", right_on="day_name", how="inner")
  df_input = df_input.drop("youbi")
  df_input = df_input.with_columns( pl.col("day_id").alias("youbi") )

  # 入会間もない人は除く (TODO: 3か月以内→後でパラメータ外だし)
  ninety_days_duration = pl.duration(days=90)
  first_row = df_input[0]
  next_month = pl.date(first_row["year"], first_row["month"], first_row["day"])
  print("以下の人たちを除外")
  print(
      df_mst_parent.filter(
          (next_month - pl.col("joined_date")) <= ninety_days_duration
      )
  )
  df_mst_parent = df_mst_parent.filter( (next_month - pl.col("joined_date")) > ninety_days_duration )

  # --------------------------------------------------
  # バリデーション
  # --------------------------------------------------
  # df_input
  # event_idの重複チェック
  if len(df_input["event_id"].unique()) != len(df_input):
    raise Exception("■■■■■■■event_id が重複してるよ■■■■■■■")
  else :
    print("OK｜event_idの重複なし")
  # ロングの日があったらエラー
  df_input_longer_than_3hours = df_input.filter(pl.col("duration") > pl.duration(hours=3))
  if len(df_input_longer_than_3hours) > 0:
    print(df_input_longer_than_3hours)
    raise ValueError(f"■■■■■■■ ロングなのに分割できてない日があるよ ■■■■■■■: {df_input_longer_than_3hours}")
  else :
    print("OK｜3時間以上の日なし")


  # --------------------------------------------------
  # 中間テーブル作成
  # --------------------------------------------------
  df_parent_attr = df_mst_parent.clone()

  # --------------------------------------------------
  # カテゴリごとのフラグを付与
  df_parent_attr = df_parent_attr.join(df_mst_member, on="parent_id", how="inner")

  dict_gender = {0: "m", 1: "f"}
  dict_cat = {0: "top", 1: "mid", 2: "und"}

  for gender_k in dict_gender:
    for cat_k in dict_cat:  
      df_parent_attr = df_parent_attr.with_columns(
        pl.when( (pl.col("gender") == gender_k) & (pl.col("category") == cat_k)) 
        .then(1)
        .otherwise(0)
        .alias(f"{dict_gender[gender_k]}_{dict_cat[cat_k]}") 
      )
    for grade in range(1, 7):
      df_parent_attr = df_parent_attr.with_columns(
        pl.when( (pl.col("gender") == gender_k) & (pl.col("grade") == grade)) 
        .then(1)
        .otherwise(0)
        .alias(f"{dict_gender[gender_k]}_{grade}") 
      )
  df_parent_attr = df_parent_attr.select([
    "parent_id", "parent_name", "staff", "joined_date",
    "m_top","m_mid","m_und","m_1","m_2","m_3","m_4","m_5","m_6","f_top","f_mid","f_und","f_1","f_2","f_3","f_4","f_5","f_6",
    "all_cat_only"])
  df_parent_attr = df_parent_attr.group_by(["parent_id", "parent_name", "staff", "joined_date"], maintain_order=True).sum()

  # --------------------------------------------------
  # 当番のカウントを付与 (↑と入れ替え不可. こどもで親が集約前にcountを横積みすると, countがgroup_byで倍になってしまう)
  # df_touban_count = df_trn_touban.select(["parent_id"]).group_by(["parent_id"], maintain_order=True).count().sort(by=pl.col("parent_id"))
  def get_touban_count(df_trn_touban, df_mst_parent):
    df_melt = df_trn_touban.melt(
      id_vars=["year", "month",	"day",	"youbi",	"time",	"m_cat",	"f_cat",	"place",	"note"],
      value_vars=["touban1", "touban2"],
      variable_name="touban_index",
      value_name="touban"
    )
    df_melt = df_melt.drop(pl.col("touban_index"))
    df_melt = df_melt.filter( pl.col("touban") != "-" )

    df_melt = df_melt.sort(by=["year", "month", "day"])
    df_melt = df_melt.join(df_mst_parent, left_on="touban", right_on="parent_name", how="inner")

    df_melt = df_melt.select(["parent_id"]).group_by(["parent_id"], maintain_order=True).count().sort(by=pl.col("count"))
    df_melt = df_mst_parent.join(df_melt, on="parent_id", how="outer")
    df_melt = df_melt.drop(pl.col("parent_id_right"))
    df_melt = df_melt.fill_null(0)
    return df_melt

  df_touban_count = get_touban_count(df_trn_touban, df_mst_parent)
  df_parent_attr = df_parent_attr.join(df_touban_count, on="parent_id", how="left")
  df_parent_attr = df_parent_attr.with_columns([pl.col("count").fill_null(0)])

  # --------------------------------------------------
  # 入会からの年数を付与
  df_parent_attr = df_parent_attr.with_columns([
      (
        get_current_fiscal_year() - pl.col("joined_date").dt.year()
      ).alias("years passed from joined")
  ])
  print(df_parent_attr)


  # --------------------------------------------------
  # モデリング
  # --------------------------------------------------
  # prob = pulp.LpProblem("opt", sense=pulp.const.LpMaximize)
  prob = pulp.LpProblem("opt", sense=pulp.const.LpMinimize)

  # ------------------------------------------------------
  # 定数準備
  # 回数の少ない保護者だけで求解してみる
  # parents = df_mst_parent["parent_id"].to_list()
  COUNT_FILTER = cutoff_threshold
  parents = df_parent_attr.filter(pl.col("count") <= COUNT_FILTER)["parent_id"].unique().to_list()
  event_ids = df_input["event_id"].to_list()
  cats = df_mst_grade_category["cat_name"].to_list()

  # 累計の過去当番回数
  touban_count_per_parent = {}
  for parent in parents:
    touban_count = df_parent_attr.filter(pl.col("parent_id") == parent).select("count").to_series().to_list()[0]
    touban_count_per_parent[parent] = touban_count

  # 累計当番回数の低いひとたちで最適化を回す

  # 親 - 各カテゴリ (学年含む) のフラグ
  dict_parent_cat_vs_flag = {}
  for parent in parents:
    dict_parent_cat_vs_flag[parent] = {}
    for cat in cats:
      flag_for_parent_in_cat = df_parent_attr.filter(pl.col("parent_id") == parent).select(cat).sum().to_series().to_list()[0]
      dict_parent_cat_vs_flag[parent][cat] = flag_for_parent_in_cat

  # 練習 - 各カテゴリ (学年含む) のフラグ
  dict_event_cat_vs_flag = {}
  for event_id in event_ids:
      dict_event_cat_vs_flag[event_id] = {}
      for cat in cats:
        # 今日のカテゴリのフラグ
        flag_for_day_in_cat = df_input.filter( pl.col("event_id") == event_id ).select(cat).sum().to_series().to_list()[0]
        dict_event_cat_vs_flag[event_id][cat] = flag_for_day_in_cat

  # 親 - 入会からの年数のdict
  dict_parent_id_vs_years_passed_from_joined = dict(zip(
      df_parent_attr["parent_id"].to_list(),
      df_parent_attr["years passed from joined"].to_list()
  ))
  dict_event_cat_vs_flag

  # 親 - 全カテフラグ
  dict_parent_vs_all_cat_flag = {}
  for parent in parents:
    df_parent_attr


  # ------------------------------------------------------
  # 決定変数
  event_parent_pairs = [(event_id, parent) for event_id in event_ids for parent in parents ]
  x = pulp.LpVariable.dicts("x", event_parent_pairs, cat=pulp.LpBinary)

  # 補助変数 (当番の回数)
  x_count_by_parents_total = pulp.LpVariable.dict("x_count_by_parents_total", parents, cat=pulp.LpInteger, lowBound=0)
  x_count_by_parents_this_month = pulp.LpVariable.dict("x_count_by_parents_this_month", parents, cat=pulp.LpInteger, lowBound=0)
  # 補助変数 (最大値と最小値)
  max_count = pulp.LpVariable("max_count", lowBound=0, cat=pulp.const.LpInteger)
  min_count = pulp.LpVariable("min_count", lowBound=0, cat=pulp.const.LpInteger)
  max_count.setInitialValue(0)
  min_count.setInitialValue(10000)

  # ------------------------------------------------------
  # 目的関数
  # 最大値最小化問題
  # 最小値最大化問題にしてみる?
  # 和の最小化もあり
  # prob.setObjective(
  #   # max_count - min_count
  #   min_count
  # )
  prob.setObjective(
    pulp.lpSum(max_count)
  )
  # ------------------------------------------------------
  # 制約条件
  # 0. 補助変数 (parentごとの今月担当回数)
  for parent in parents:
    prob.addConstraint(
      x_count_by_parents_total[parent] 
      == pulp.lpSum( x[event_id, parent] for event_id in event_ids ) + touban_count_per_parent[parent]
    )
  for parent in parents:
    prob.addConstraint(
      x_count_by_parents_this_month[parent] 
      == pulp.lpSum( x[event_id, parent] for event_id in event_ids )
    )

  # 0. 補助変数 (最大値, 最小値)
  for parent in parents:
    prob.addConstraint(
      x_count_by_parents_total[parent] <= max_count
    )
    prob.addConstraint(
      min_count <= x_count_by_parents_total[parent]
    )

  # 9. 今月に入る回数は1回まで
  for parent in parents:
    prob.addConstraint(
      x_count_by_parents_this_month[parent] <= 2
    )

  # 1. 各日の当番の人数は2名 (あとで人数を指定できるようにする)
  for event_id in event_ids:
    prob.addConstraint(
      pulp.lpSum(
        [ x[event_id, parent] for parent in parents ]
      ) == 2
    )

  # 2. 各dayの該当カテゴリにのみアサイン
  for event_id in event_ids:
    for parent in parents:
      prob.addConstraint(
        x[event_id, parent] <= ( 
          dict_parent_cat_vs_flag[parent][cat] * dict_event_cat_vs_flag[event_id][cat]
          for cat in cats
        )
      )
  # 10. 全カテのみフラグが入っている人は全カテの日だけを対象とする
  # ※本来はこどもが全員いる日なので、修正が必要. アンダートップの日とかも入れられる可能性あり
  # 親 - 全カテフラグ
  # dict_parent_vs_all_cat_flag = dict(zip(
  #     df_parent_attr["parent_id"].to_list(),
  #     df_parent_attr["all_cat_only"].to_list()
  # ))
  # dict_event_allcat_vs_flag = {}
  # for event_id in event_ids:
  #   # この日は全カテか？
  #   is_all_cat_event = 1
  #   for cat in cats:
  #     if (not "und" in cat) and (not "mid" in cat) and (not "top" in cat):
  #       continue
  #     is_all_cat_event *= dict_event_cat_vs_flag[event_id][cat]
  #   dict_event_allcat_vs_flag[event_id] = is_all_cat_event
  # for event_id in event_ids:
  #   for parent in parents:
  #     # 全カテ
  #     prob.addConstraint(
  #       x[event_id, parent] <= ( 
  #         dict_parent_vs_all_cat_flag[parent] * dict_event_allcat_vs_flag[event_id]
  #       )
  #     )

  # 3. 曜日希望をかなえる
  day_ids = list(range(8))
  dict_id_vs_day = dict(zip(df_mst_day["day_id"].to_list(), df_mst_day["day_name"].to_list()))
  dict_parent_vs_abledaybit = {}
  for parent in parents:
    ableday_list = [int(item) for item in df_mst_parent.filter( pl.col("parent_id") == parent )["youbi_kibo"].to_list()[0].split(",")]
    ableday_bit = np.zeros(len(day_ids), dtype=int)
    ableday_bit[ableday_list] = 1
    dict_parent_vs_abledaybit[parent] = ableday_bit

  for event_id in event_ids:
    day_id = df_input.filter( pl.col("event_id") == event_id )["youbi"].to_list()[0]
    for parent in parents:
      # 親をキーに曜日指定日をとってきて
      prob.addConstraint(
        x[event_id, parent] <= dict_parent_vs_abledaybit[parent][day_id]
      )
  # 4. 初心者は一人にしない
  # ×今年度入会 + 当番回数が0の人 同士はペアにしない
  # ●今年度入会の人はペアにしない
  # 経過年数の合計が1以上
  for event_id in event_ids:
    prob.addConstraint(
      pulp.lpSum(
        x[event_id, parent] * dict_parent_id_vs_years_passed_from_joined[parent]
        for parent in parents
      ) >= 1
    )

  # 5. 同じ日に当番にしない
  # "9. 今月に入る回数は1回まで" で対応済

  # 6. Staffは対象外
  # 前処理で対応済

  # ----------------------------------------
  # solve
  result = prob.solve()
  print(pulp.LpStatus[result])
  if pulp.LpStatus[result] != "Optimal":
    print("最適解が見つかりませんでした")
    return pulp.LpStatus[result], None, None
  # ----------------------------------------
  # 結果出力
  df_touban = pl.DataFrame()
  dict_parent = dict(zip(df_mst_parent['parent_id'].to_list(), df_mst_parent['parent_name'].to_list()))
  for event_id in event_ids:
    touban = []
    for parent in parents:
      if x[event_id, parent].value() == 1:
        # print(f"{day} {parent}")  
        touban.append(dict_parent[parent])
    print(event_id,touban)
    df_touban = pl.concat( [df_touban, pl.DataFrame( {"event_id": [event_id], "touban1": [touban[0]], "touban2": [touban[1]]} )] )

  print(f"{df_touban}")

  print(f"max: {max_count.value()}")
  print(f"min: {min_count.value()}")

  maxvavava = 0
  for parent in parents:
    print(dict_parent[parent], x_count_by_parents_total[parent].value())
    if maxvavava < x_count_by_parents_total[parent].value():
      maxvavava = x_count_by_parents_total[parent].value()
  print(f"max: {maxvavava}")

  print("ここよ")
  print(df_input_org.columns)
  df_output = (
    df_input_org
    .join( df_touban, on="event_id", how="left" )
    .select(["month", "day", "youbi", "start_time", "end_time", "duration", "place", "m_cat", "f_cat", "touban1", "touban2"])
    .with_columns( [pl.col("touban1").fill_null("-"), pl.col("touban2").fill_null("-")] )
  )
  df_output = df_output.with_columns(
      df_output["start_time"].dt.strftime("%H:%M").alias("start_time")
  )
  df_output = df_output.with_columns(
      df_output["end_time"].dt.strftime("%H:%M").alias("end_time")
  )  
  # df_output.write_csv(f"{dir}/output.csv")

  # 親ごとの当番回数
  # 親、前回登板回数、今回当番回数、差分 (増分)
  # df_touban_count = pl.DataFrame()
  dict_parent_this_month_count = {}
  sorted_count = sorted(x_count_by_parents_total.items(), key=lambda x:x[1].value(), reverse=True)
  for kv in sorted_count:
    dict_parent_this_month_count[kv[0]] = kv[1].value()

  temp_touban_count_prev_month_list = []
  temp_touban_count_this_month_list = []
  temp_zobun_list = []
  parents_org = df_parent_attr["parent_id"].unique().to_list()
  touban_count_per_parent_org = {}
  for parent in parents_org:
    touban_count = df_parent_attr.filter(pl.col("parent_id") == parent).select("count").to_series().to_list()[0]
    touban_count_per_parent_org[parent] = touban_count
  for parent in parents_org:
    # 前月までの当番回数
    prev_month_count = touban_count_per_parent_org[parent]
    temp_touban_count_prev_month_list.append(prev_month_count)
    # 今月までの当番回数
    if dict_parent_this_month_count.get(parent) is not None:
      temp_touban_count_this_month_list.append(dict_parent_this_month_count[parent])
    else:
      temp_touban_count_this_month_list.append(prev_month_count) # 先月の値を入れる
    this_month_count = temp_touban_count_this_month_list[-1]
    # 増分
    temp_zobun_list.append(this_month_count - prev_month_count)
  df_touban_count_zobun = pl.DataFrame(
    {
      "parent": [dict_parent[parent] for parent in parents_org],
      "prev_month_count": temp_touban_count_prev_month_list,
      "this_month_count": temp_touban_count_this_month_list,
      "zobun": temp_zobun_list
    }
  ).sort("this_month_count", descending=True)

  return pulp.LpStatus[result], df_output, df_touban_count_zobun

