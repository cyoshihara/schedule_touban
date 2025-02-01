import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
import polars as pl

import const
import utils


def main():
    gcp_creds, google_genai_api_key = utils.get_secrets()

    # Google Drive API クライアントを作成
    drive_service = build("drive", "v3", credentials=gcp_creds)

    if st.button("ファイル一覧を取得"):
        files = utils.list_drive_files(drive_service)
        if files:
            for file in files:
                st.write(f"📄 {file['name']} (ID: {file['id']})")
        else:
            st.write("ファイルが見つかりませんでした")

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

    with st.spinner('処理中...'):
        fpath = utils.download_csv_file(
            drive_service,
            "1PyryHjH5Qi6fwkDrIejDUtW68Oc3V28R",
            "input.csv",
            const.DIR_TEMP)
        df = pl.read_csv(fpath)
    st.write(df)

if __name__ == "__main__":
    main()