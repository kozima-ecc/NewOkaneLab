import pandas as pd
import os

# =========================================================
# 設定エリア
# =========================================================
# データベース名
DB_NAME = 'sisukai_db'

# 読み込むCSVファイルのリスト（依存関係順：親テーブルを先に！）
# 1. 用語集 (独立)
# 2. 企業 (親)
# 3. 日次株価, 財務データ, イベント (子)
FILES = [
    'sisukai.xlsx - 用語集.csv',
    'sisukai.xlsx - 企業.csv',
    'sisukai.xlsx - 日次株価.csv',
    'sisukai.xlsx - 財務データ.csv',
    'sisukai.xlsx - イベント.csv'
]

# 出力するSQLファイル名
OUTPUT_SQL_FILE = 'create_sisukai_db.sql'
# =========================================================

def get_col_index(row, search_terms):
    for i, val in enumerate(row):
        if pd.notna(val) and any(s in str(val) for s in search_terms):
            return i
    return -1

def get_table_name_map(files):
    mapping = {}
    for f in files:
        try:
            df = pd.read_csv(f, header=None)
            phys_name = ""
            log_name = ""
            
            for r_idx, row in df.iterrows():
                # 物理名取得
                c_idx = get_col_index(row, ["テーブル名(物理)"])
                if c_idx != -1 and r_idx + 1 < len(df):
                    val = df.iloc[r_idx+1, c_idx]
                    if pd.notna(val): phys_name = str(val).strip()
                
                # 論理名取得
                c_idx_log = get_col_index(row, ["テーブル名(論理)"])
                if c_idx_log != -1 and r_idx + 1 < len(df):
                    val = df.iloc[r_idx+1, c_idx_log]
                    if pd.notna(val): log_name = str(val).strip()
            
            # 用語集の特例対応
            if "用語集" in f and not phys_name:
                phys_name = "Glossary"
                log_name = "用語集"

            if log_name and phys_name:
                mapping[log_name] = phys_name
                # "企業表" -> "companies" のように "表" なし/あり 両対応
                mapping[log_name.replace("表", "")] = phys_name
                mapping[log_name + "表"] = phys_name
        except:
            pass
    return mapping

def generate_create_table_sql(file_path, table_map):
    try:
        df = pd.read_csv(file_path, header=None)
        
        # 1. テーブル名の特定
        phys_table_name = ""
        log_table_name = ""
        
        for r_idx, row in df.iterrows():
            c_idx = get_col_index(row, ["テーブル名(物理)"])
            if c_idx != -1 and r_idx + 1 < len(df):
                val = df.iloc[r_idx+1, c_idx]
                if pd.notna(val): phys_table_name = str(val).strip()
            
            c_idx_log = get_col_index(row, ["テーブル名(論理)"])
            if c_idx_log != -1 and r_idx + 1 < len(df):
                val = df.iloc[r_idx+1, c_idx_log]
                if pd.notna(val): log_table_name = str(val).strip()
        
        if "用語集" in file_path and not phys_table_name:
            phys_table_name = "Glossary"
            log_table_name = "用語集"

        if not phys_table_name:
            return f"-- [Error] Table name not found in {file_path}"

        # 2. ヘッダー行の探索
        header_row_idx = -1
        for r_idx, row in df.iterrows():
            if get_col_index(row, ["項番"]) != -1 and get_col_index(row, ["列名(物理)"]) != -1:
                header_row_idx = r_idx
                break
        
        if header_row_idx == -1: return f"-- [Error] Header not found in {file_path}"
        
        header_row = df.iloc[header_row_idx]
        sub_header_row = df.iloc[header_row_idx+1] if header_row_idx+1 < len(df) else None
        
        # 3. 列インデックスの特定
        idx_phys = get_col_index(header_row, ["列名(物理)"])
        idx_type = get_col_index(header_row, ["データ型"])
        idx_len = get_col_index(header_row, ["桁数"])
        
        # PK, NNの位置特定 (P, PK, N, NN)
        idx_pk = get_col_index(header_row, ["P", "PK"])
        if idx_pk == -1: idx_pk = 24 # フォールバック
        
        idx_nn = get_col_index(header_row, ["N", "NN"])
        if idx_nn == -1: idx_nn = 25 # フォールバック
        
        idx_comment = get_col_index(header_row, ["備考"])
        
        # 参照テーブル/列の特定 (サブヘッダーにあることが多い)
        idx_ref_table = -1
        idx_ref_col = -1
        if sub_header_row is not None:
            # 誤検知を防ぐため、列番号20以降で探す
            for i in range(20, len(sub_header_row)):
                val = str(sub_header_row[i])
                if "テーブル名" in val: idx_ref_table = i
                if "列名" in val: idx_ref_col = i
        
        col_defs = []
        pks = []
        fks = []
        
        # 4. データ行の解析
        for r_idx in range(header_row_idx + 2, len(df)):
            row = df.iloc[r_idx]
            
            # 物理名がない行はスキップ
            phys_name = str(row[idx_phys]).strip() if pd.notna(row[idx_phys]) else ""
            if not phys_name or phys_name == "nan" or phys_name == "列名(物理)": continue
            
            # データ型
            dtype = str(row[idx_type]).strip() if pd.notna(row[idx_type]) else ""
            length = str(row[idx_len]).strip() if idx_len != -1 and pd.notna(row[idx_len]) else ""
            if length and length != 'nan':
                 length = length.replace('"', '')
                 # 文字列やDECIMAL型なら桁数をつける
                 if dtype.upper() in ['VARCHAR', 'CHAR', 'DECIMAL', 'INT', 'BIGINT', 'TINYINT']:
                     dtype = f"{dtype}({length})"
            
            # 制約 (PK, NN)
            is_nn = False
            if idx_nn != -1 and pd.notna(row[idx_nn]) and str(row[idx_nn]).strip() in ['◯', 'O', 'Y', '1']:
                is_nn = True
                
            if idx_pk != -1 and pd.notna(row[idx_pk]) and str(row[idx_pk]).strip() in ['◯', 'O', 'Y', '1']:
                pks.append(phys_name)
            
            comment = ""
            if idx_comment != -1 and pd.notna(row[idx_comment]):
                comment = str(row[idx_comment]).strip().replace("'", "''")
                
            # 外部キー (FK)
            if idx_ref_table != -1 and pd.notna(row[idx_ref_table]):
                ref_tab_raw = str(row[idx_ref_table]).strip()
                ref_col = str(row[idx_ref_col]).strip() if idx_ref_col != -1 and pd.notna(row[idx_ref_col]) else ""
                
                if ref_tab_raw and ref_col:
                    # 論理名→物理名へ変換
                    ref_tab_phys = table_map.get(ref_tab_raw, ref_tab_raw)
                    fks.append((phys_name, ref_tab_phys, ref_col))

            # SQL行の構築
            line = f"  `{phys_name}` {dtype}"
            line += " NOT NULL" if is_nn else " NULL"
            if "AUTO_INCREMENT" in comment.upper():
                line += " AUTO_INCREMENT"
            line += f" COMMENT '{comment}'"
            col_defs.append(line)
            
        # CREATE TABLE文の組み立て
        sql = f"-- Table: {log_table_name} ({phys_table_name})\n"
        sql += f"CREATE TABLE `{phys_table_name}` (\n"
        sql += ",\n".join(col_defs)
        
        if pks:
            sql += f",\n  PRIMARY KEY ({', '.join(['`'+p+'`' for p in pks])})"
            
        for col, rt, rc in fks:
            # 制約名は一意にする
            constraint_name = f"fk_{phys_table_name}_{col}"
            sql += f",\n  CONSTRAINT `{constraint_name}` FOREIGN KEY (`{col}`) REFERENCES `{rt}` (`{rc}`) ON DELETE CASCADE ON UPDATE CASCADE"
            
        sql += f"\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='{log_table_name}';\n"
        
        return sql

    except Exception as e:
        return f"-- [Error] {file_path}: {e}\n"

def main():
    print("🚀 MySQL DDL生成を開始します...")
    
    # マッピングの作成
    table_map = get_table_name_map(FILES)
    # 補正
    table_map["企業"] = "companies"
    
    with open(OUTPUT_SQL_FILE, 'w', encoding='utf-8') as f:
        # 1. DB作成
        f.write(f"-- Generated by Python Script\n")
        f.write(f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\n")
        f.write(f"USE `{DB_NAME}`;\n\n")
        
        # 2. 各テーブルのCREATE文
        for csv_file in FILES:
            if os.path.exists(csv_file):
                print(f"  Processing: {csv_file}")
                sql = generate_create_table_sql(csv_file, table_map)
                f.write(sql + "\n")
            else:
                print(f"  ⚠️ File not found: {csv_file}")
                f.write(f"-- File not found: {csv_file}\n")
    
    print(f"\n✅ 完了！ SQLファイルを作成しました: {OUTPUT_SQL_FILE}")
    print("このファイルをMySQL Workbenchなどで開いて実行してください。")

if __name__ == "__main__":
    main()