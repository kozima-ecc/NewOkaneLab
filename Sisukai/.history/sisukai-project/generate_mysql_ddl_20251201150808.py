import os

# =========================================================
# 設定エリア
# =========================================================
DB_NAME = 'trade_sim'
OUTPUT_SQL_FILE = 'create_trade_sim.sql'
# =========================================================

def main():
    print("🚀 MySQL DDL生成を開始します (CSV不要モード)...")

    # SQLの中身を定義
    sql_content = f"""
-- ========================================================
-- Database Creation
-- ========================================================
CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE `{DB_NAME}`;

-- ========================================================
-- 1. 用語集 (Glossary)
-- ========================================================
CREATE TABLE `Glossary` (
  `TermID` INT NOT NULL AUTO_INCREMENT COMMENT '項目ID',
  `TermName` VARCHAR(256) NOT NULL COMMENT '項目名',
  `Category` VARCHAR(256) NOT NULL COMMENT '分類',
  `Definition` TEXT NOT NULL COMMENT '定義',
  `Reading` VARCHAR(256) NOT NULL COMMENT '読み方',
  `example` TEXT NOT NULL COMMENT '事例',
  `Details` TEXT NOT NULL COMMENT '詳細解説',
  PRIMARY KEY (`TermID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用語集';

-- ========================================================
-- 2. 企業マスタ (companies) - 親テーブル
-- ========================================================
CREATE TABLE `companies` (
  `ticker_code` VARCHAR(10) NOT NULL COMMENT '銘柄コード (例: 7203.T)',
  `company_name` VARCHAR(256) NOT NULL COMMENT '企業名',
  `industry_name` VARCHAR(100) NULL COMMENT '業種名',
  `market` VARCHAR(50) NULL COMMENT '市場区分',
  PRIMARY KEY (`ticker_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='企業表';

-- ========================================================
-- 3. 日次株価 (factstock_daily)
-- ========================================================
CREATE TABLE `factstock_daily` (
  `date` DATE NOT NULL COMMENT '日付',
  `ticker_code` VARCHAR(10) NOT NULL COMMENT '銘柄コード (FK)',
  `open` DECIMAL(10,2) NULL COMMENT '始値',
  `high` DECIMAL(10,2) NULL COMMENT '高値',
  `low` DECIMAL(10,2) NULL COMMENT '安値',
  `close` DECIMAL(10,2) NULL COMMENT '終値',
  `adj_close` DECIMAL(10,2) NULL COMMENT '調整後終値',
  `volume` BIGINT NULL COMMENT '出来高',
  PRIMARY KEY (`date`, `ticker_code`),
  CONSTRAINT `fk_factstock_daily_ticker` FOREIGN KEY (`ticker_code`) 
    REFERENCES `companies` (`ticker_code`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='日次株価';

-- ========================================================
-- 4. 財務データ (fact_financials)
-- ========================================================
CREATE TABLE `fact_financials` (
  `ticker_code` VARCHAR(10) NOT NULL COMMENT '銘柄コード (FK)',
  `fiscal_year` INT NOT NULL COMMENT '会計年度 (例: 2025)',
  `quarter` TINYINT NOT NULL COMMENT '四半期 (1-4)',
  `net_sales` BIGINT NULL COMMENT '売上高',
  `operating_income` BIGINT NULL COMMENT '営業利益',
  `net_income` BIGINT NULL COMMENT '純利益',
  `eps` DECIMAL(10,2) NULL COMMENT 'EPS',
  `roe` FLOAT NULL COMMENT 'ROE',
  PRIMARY KEY (`ticker_code`, `fiscal_year`, `quarter`),
  CONSTRAINT `fk_fact_financials_ticker` FOREIGN KEY (`ticker_code`) 
    REFERENCES `companies` (`ticker_code`) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='財務データ';

-- ========================================================
-- 5. イベントデータ (fact_events)
-- ========================================================
CREATE TABLE `fact_events` (
  `event_id` INT NOT NULL AUTO_INCREMENT COMMENT 'イベントID',
  `event_date` DATE NOT NULL COMMENT '発生日',
  `ticker_code` VARCHAR(10) NULL COMMENT '関連銘柄 (NULL可)',
  `category` VARCHAR(50) NULL COMMENT 'カテゴリ',
  `title` VARCHAR(256) NULL COMMENT 'タイトル',
  `description` TEXT NULL COMMENT '詳細',
  `sentiment_score` FLOAT NULL COMMENT 'センチメント',
  `importance` TINYINT NULL COMMENT '重要度',
  PRIMARY KEY (`event_id`),
  CONSTRAINT `fk_fact_events_ticker` FOREIGN KEY (`ticker_code`) 
    REFERENCES `companies` (`ticker_code`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='イベント';
"""

    # ファイル書き出し
    try:
        with open(OUTPUT_SQL_FILE, 'w', encoding='utf-8') as f:
            f.write(sql_content)
        
        print(f"\n✅ 完了！ SQLファイルを作成しました: {OUTPUT_SQL_FILE}")
        print(f"以下のコマンドでMySQLにデータベースを作成できます:")
        print(f"mysql -u root -p < {OUTPUT_SQL_FILE}")
        
    except Exception as e:
        print(f"❌ ファイル作成エラー: {e}")

if __name__ == "__main__":
    main()