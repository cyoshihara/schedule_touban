# Description

- This app is made by Chihiro YOSHIHARA.
- This app can schedule team 'otouban's.

# How to use

1. 先月までのデータのバックアップ
    1. ./tmp 以下のデータを ./tmp/bk/yyyymm 以下にコピー
    ※下記データはtmp配下に残す
        - mst_day.csv
        - mst_grade_category.csv
1. 当月データの作成
    1. 🦀マークのアカウントで下記ファイルにアクセス
    https://docs.google.com/spreadsheets/d/1DN_sdRDNpUL54V8veTGMkumA4b99onzfIIq96XkEZ94/edit?gid=1226783448#gid=1226783448
        1. input.csv: 当月の練習日程を元に作成
        1. mst_member.csv: 新入会があったりカテゴリ変更があった場合に更新
        1. mst_parent.csv: 新入会があった場合に更新
        1. trn_touban.csv：前月までの当番をappend
    1. 更新があったデータについて、tmp以下のファイルを更新
1. 実行


# How to Develop

- This app use the python's official virtual environment.
- So, you can run a command below.
  - python -m venv .venv
  - .\.venv\Scripts\activate
  - pip install -r requirements.txt