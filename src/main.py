import streamlit as st
import atexit
from googleapiclient.discovery import build
import google.generativeai as genai
import polars as pl
import os
from io import StringIO
import shutil

import const
import utils


IS_DEBUG = True

# TODO
# [] ウィザードもできる
# https://blog.streamlit.io/streamlit-wizard-form-with-custom-animated-spinner/
# [] tmpのファイルを消す

# 📄 schedule-touban-data (ID: 1eIyBtoj9xbwyWU4Ej477ZBxpccv55eY-)
# 📄 trn_touban.csv (ID: 1LnQKVcN7-o_WMtLUn_0c6OqKCunstbAa)
# 📄 for_test_trn_touban.csv (ID: 13LK7YU7mmvURWxf4cvv3Et9XaaZU6lpu)
# 📄 trn_touban_新しいフォーマットで作成中.csv (ID: 1my7qe1HYiSBPXahuxxFTCagVKyDaQ2_k)
# 📄 output.csv (ID: 1Q9x6sywZdXwH4_3xHf_Jv9_sdkaemwKz)
# 📄 input.csv (ID: 1PyryHjH5Qi6fwkDrIejDUtW68Oc3V28R)
# 📄 mst_parent.csv (ID: 1UzI8WWfLes5PIP9999bQUpQfsQjojZSx)
# 📄 _intermediate_parent_attr.csv (ID: 1dz4vyutekOoj1JNUHTL60M3ESrmhssCJ)
# 📄 trn_touban_org_till_12.csv (ID: 16zOGSkGW7hOWLS7t8Arw8eJIoXLaSFuR)
# 📄 mst_day.csv (ID: 1PvoHPZVwVyZknBybzINyZOqacMTkb0LJ)

def cleanup():
    try:
        shutil.rmtree(const.DIR_TEMP)
        print(f"Cleaned up temporary directory: {const.DIR_TEMP}")
        # GoogleDrive上のファイルの更新もしたい？？ → やりなおしたい場合もあるかもだから、やめた方がよさそう。
    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    st.write("# お当番スケジューリングアプリ")
    if 'linetext_touban' not in st.session_state:
        st.session_state.linetext_touban = const.DEBUG_SAMPLE_LINETEXT_TOUBAN if IS_DEBUG else "ここに今月の役員さんのLINEメッセージをペースト"
    if 'line_text_plan' not in st.session_state:
        st.session_state.line_text_plan = const.DEBUG_SAMPLE_LINETEXT_PLAN if IS_DEBUG else "ここに翌月の練習日程のLINEメッセージをペースト"


    gcp_creds, google_genai_api_key = utils.get_secrets()

    gds = utils.GoogleDriveService(gcp_creds, is_clear_data_dir_when_app_close=(not IS_DEBUG))

    # ここから本処理
    fpath_trn_touban = os.path.join(const.DIR_TEMP, "trn_touban.csv")
    fpath_mst_parent = os.path.join(const.DIR_TEMP, "mst_parent.csv")

    # ---------------------------------------------
    st.header('参考) 今年度の当番履歴')
    # ---------------------------------------------
    with st.spinner('データダウンロード中...'):
        if os.path.isfile(fpath_trn_touban) is False:
            fpath_trn_touban = gds.download_file("1LnQKVcN7-o_WMtLUn_0c6OqKCunstbAa")
        if os.path.isfile(fpath_mst_parent) is False:
            fpath_mst_parent = gds.download_file("1UzI8WWfLes5PIP9999bQUpQfsQjojZSx")

    with st.spinner('当番履歴読み込み中...'):
        df_trn_touban = pl.read_csv(fpath_trn_touban)
        df_mst_parent = pl.read_csv(fpath_mst_parent)
        def add_parent_id(df_trn_touban, df_mst_parent):
            df_mst_parent = df_mst_parent.select([pl.col("parent_id"), pl.col("parent_name")])
            df_trn_touban = df_trn_touban.join(df_mst_parent, left_on="touban1", right_on="parent_name", how="left")
            df_trn_touban = df_trn_touban.join(df_mst_parent, left_on="touban2", right_on="parent_name", how="left")
            return df_trn_touban
        df_trn_touban = add_parent_id(df_trn_touban, df_mst_parent) 
        st.write(df_trn_touban)


    # ---------------------------------------------
    st.write('### 作業1: 役員さんから来たLINEから表を作成します')
    # ---------------------------------------------

    col_touban_1_width = st.slider("", min_value=0, max_value=100, value=30)
    col_touban_2_width = 100 - col_touban_1_width
    col_touban_1, col_touban_2 = st.columns([col_touban_1_width, col_touban_2_width])
    with col_touban_1:
        linetext_touban = st.text_area(
            "↓↓↓LINEのお当番表を貼り付けてください↓↓↓", 
            value=st.session_state.linetext_touban,
            height=const.HEIGHT_CHECK+60
        )
        st.session_state.linetext_touban = linetext_touban
    with col_touban_2:
        if st.button('LINEテキストから当番表を作成する (10秒くらいかかります)'):
            st.write('LINEと見比べて以下の表を編集してください')
            # Geminiを呼出し
            genai.configure(api_key=google_genai_api_key)
            model = genai.GenerativeModel(const.GOOGLE_GENAI_MODEL_ID)
            response = model.generate_content(f"{const.CHATGPT_PROMPT_TOUBAN + linetext_touban}")
            if response.text != "":
            # 結果をcsvに変換
               csv_data = StringIO(response.text.replace("```csv", "").replace("```", ""))
            # DataFrameに起こして表示
            df_touban_this_month = pl.read_csv(csv_data, separator="\t")
            df_touban_this_month = df_touban_this_month.filter(
                (pl.col("year").is_not_null()) & (pl.col("month").is_not_null())
            )
            # スライダを動かしたときに消えないようにグローバルな場所に登録
            st.session_state.df_touban_this_month = df_touban_this_month
        if "df_touban_this_month" in st.session_state:
            df_touban_this_month = st.session_state.df_touban_this_month
            df_touban_this_month = st.data_editor(df_touban_this_month, num_rows="dynamic", height=const.HEIGHT_CHECK)


    # ---------------------------------------------
    st.write('### 作業2: 一真コーチのLINEから練習日程表を作成します')
    # ---------------------------------------------
    col_plan_1_width = st.slider("Column Rensyu 1 Width (%)", min_value=10, max_value=90, value=30)
    col_plan_2_width = 100 - col_plan_1_width
    col_plan_1, col_plan_2 = st.columns([col_plan_1_width, col_plan_2_width])
    with col_plan_1:
        line_text_plan = st.text_area(
            "来月の練習LINEノート",
            value=st.session_state.line_text_plan,
            height=const.HEIGHT_CHECK+60
        )
        st.session_state.line_text_plan = line_text_plan
    with col_plan_2:
        if st.button('LINEテキストから練習予定の表を作成する (10秒くらいかかります)'):
            st.write('LINEと見比べて以下の表を編集してください')
            # Geminiを呼出し
            genai.configure(api_key=google_genai_api_key)
            model = genai.GenerativeModel(const.GOOGLE_GENAI_MODEL_ID)
            response = model.generate_content(f"{const.CHATGPT_PROMPT_PLAN + line_text_plan}")
            if response.text != "":
            # 結果をcsvに変換
               csv_data = StringIO(response.text.replace("```csv", "").replace("```", ""))
            
            # DataFrameに起こして表示
            df_input = pl.read_csv(csv_data, separator="\t", truncate_ragged_lines=True)
            df_input = df_input.filter(
                (pl.col("year").is_not_null()) & (pl.col("month").is_not_null())
            )
            # スライダを動かしたときに消えないようにグローバルな場所に登録
            st.session_state.df_input = df_input
        if "df_input" in st.session_state:
            df_input = st.session_state.df_input
            df_input = st.data_editor(df_input, num_rows="dynamic", height=const.HEIGHT_CHECK)

    # ---------------------------------------------
    st.write('### 作業3: お当番の日程を自動作成')
    # ---------------------------------------------
    cutoff_threshold = st.number_input('累積当番回数がこの値以下の家庭のみ対象', 8)
    if st.button('最適化実行'):
        st.write('最適化実行中...')

        import optimize
        lp_status,df_output, dict_parent_count = optimize.optimize(
            const.DIR_TEMP,
            df_input,
            df_trn_touban,
            cutoff_threshold,
            gds
        )
        if lp_status != "Optimal":
            st.error('最適化に失敗しました')
        else:
            st.success('成功')
            st.data_editor(df_output, num_rows="dynamic")
            st.write("↑↑↑↑↑↑↑ねんのため、カテゴリを確認↑↑↑↑↑↑↑")

            # ---------------------------------------------
            st.write("累積当番回数の確認")
            st.write(dict_parent_count)
        
            st.write("TODO: 初心者でも対象外の人も出力したい")
            st.write("TODO: 各家庭の希望曜日などを外だしして表示したい")
            st.write("TODO: LINEやめてほしい")
            st.write("TODO: inputとoutputに場所とイベント列を追加したい")
            st.write("TODO: 全カテのみ希望への対応")
            st.write("TODO: 役員必須日の対応 (ふれはすの日は、一方を役員にする)")
            st.write("TODO: 最適化プログレスバーを表示したい")

def test_gemini():
    gcp_creds, google_genai_api_key = utils.get_secrets()

    genai.configure(api_key=google_genai_api_key)
    model = genai.GenerativeModel(const.GOOGLE_GENAI_MODEL_ID)
    response = model.generate_content(f"{const.CHATGPT_PROMPT_PLAN + const.DEBUG_SAMPLE_LINETEXT_PLAN}")
    print(response.text)
    if response.text != "":
    # 結果をcsvに変換
        csv_data = StringIO(response.text.replace("```csv", "").replace("```", ""))
    
    # DataFrameに起こして表示
        df_input = pl.read_csv(csv_data, separator="\t", truncate_ragged_lines=True)
        print(df_input)

if __name__ == "__main__":
    atexit.register(cleanup)
    main()

    # test_gemini()
    # gcp_creds, google_genai_api_key = utils.get_secrets()

    # gds = utils.GoogleDriveService(gcp_creds, is_clear_data_dir_when_app_close=(not IS_DEBUG))
    # print(gds.list_drive_files(100))
