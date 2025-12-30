import sqlite3

db_path = "dados/projeto.sqlite"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get table names
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# Get columns for each table
for table in tables:
    t_name = table[0]
    cursor.execute(f"PRAGMA table_info({t_name})")
    columns = cursor.fetchall()
    print(f"\nTable: {t_name}")
    for col in columns:
        print(f"  {col[1]} ({col[2]})")

conn.close()
