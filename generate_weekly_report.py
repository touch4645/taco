# -*- coding: utf-8 -*>
import os
import datetime
import argparse
import io

def get_last_week_daily_reports(daily_report_dir):
    """
    指定されたディレクトリから過去7日分のデイリーレポートのパスを取得する
    """
    if not os.path.exists(daily_report_dir):
        return []

    report_paths = []
    today = datetime.date.today()
    for i in range(7):
        date = today - datetime.timedelta(days=i)
        file_name = "{}.md".format(date.strftime('%Y-%m-%d'))
        file_path = os.path.join(daily_report_dir, file_name)
        if os.path.exists(file_path):
            report_paths.append(file_path)
    return report_paths

def generate_weekly_report(daily_dir, weekly_dir):
    """
    ウィークリーレポートを生成して保存する
    """
    daily_reports = get_last_week_daily_reports(daily_dir)
    if not daily_reports:
        print("デイリーレポートが見つかりません。")
        return

    # デイリーレポートの内容を結合
    combined_report = ""
    for report_path in sorted(daily_reports):
        with io.open(report_path, 'r', encoding='utf-8') as f:
            combined_report += f.read() + "\n\n"

    # ここでGemini APIを呼び出し、レポートを要約する処理を後で追加する

    # ウィークリーレポートのファイル名を決定
    today = datetime.date.today()
    end_date = today - datetime.timedelta(days=1)
    start_date = end_date - datetime.timedelta(days=6)
    if not os.path.exists(weekly_dir):
        os.makedirs(weekly_dir)
    weekly_report_filename = "{}_{}_weekly.md".format(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    weekly_report_path = os.path.join(weekly_dir, weekly_report_filename)

    # とりあえず結合したレポートをそのまま保存
    with io.open(weekly_report_path, 'w', encoding='utf-8') as f:
        f.write(combined_report)

    print("ウィークリーレポートを {} に保存しました。".format(weekly_report_path))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ウィークリーレポートを生成します。")
    parser.add_argument("--daily_dir", default="reports/daily", help="デイリーレポートが格納されているディレクトリ")
    parser.add_argument("--weekly_dir", default="reports/weekly", help="ウィークリーレポートを保存するディレクトリ")
    args = parser.parse_args()

    generate_weekly_report(args.daily_dir, args.weekly_dir)
