"""Read-only plan by default; apply normalized stored provider durations explicitly."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.database.deployment import connect
from src.database.course_duration import backfill

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db-env',default='SUPABASE_DB_URL')
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    with connect(args.db_env) as conn:
        if not args.apply:conn.execute('SET TRANSACTION READ ONLY')
        print(json.dumps(backfill(conn,apply=args.apply),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
