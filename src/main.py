import streamlit as st
import atexit
from googleapiclient.discovery import build
import google.generativeai as genai
import polars as pl
import os
from io import StringIO
import shutil

import const
from const import FileID
import utils


IS_DEBUG = True


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

    gds = utils.GoogleDriveService(gcp_creds)

    # ここから本処理
    fpath_trn_touban = os.path.join(const.DIR_TEMP, "trn_touban.csv")
    fpath_mst_parent = os.path.join(const.DIR_TEMP, "mst_parent.csv")

    # ---------------------------------------------
    st.header('参考) 今年度の当番履歴')
    # ---------------------------------------------
    with st.spinner('データダウンロード中...'):
        if os.path.isfile(fpath_trn_touban) is False:
            fpath_trn_touban = gds.download_file(FileID.trn_touban)
        if os.path.isfile(fpath_mst_parent) is False:
            fpath_mst_parent = gds.download_file(FileID.mst_parent)

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

    fpath_input = os.path.join(const.DIR_TEMP, "input.csv")
    df_input = pl.read_csv(fpath_input, separator=",")

    # ---------------------------------------------
    st.write('### 作業2: お当番の日程を自動作成')
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
            st.write("↑↑↑↑↑↑↑念のため、カテゴリを確認してください↑↑↑↑↑↑↑")
            # ---------------------------------------------
            st.write("今年度のお当番回数 ※偏りがないか確認してください")
            st.write(dict_parent_count)


if __name__ == "__main__":
    atexit.register(cleanup)
    main()