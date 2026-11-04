import os
import pandas as pd
from sklearn.model_selection import train_test_split

# 1. 경로 설정
# 원본 파일: data/original/kwater_4class_questions_2000.csv
SOURCE_DIR = os.path.join("data", "original")
SOURCE_FILE = os.path.join(SOURCE_DIR, "kwater_4class_questions_2000.csv")

# 분할된 파일 저장 위치: data/
OUTPUT_DIR = "data"

# 폴더 생성 (data 및 data/original이 없더라도 안전하게 처리)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 원본 데이터 로드
df = pd.read_csv(SOURCE_FILE)

# 2. Train(80%) vs test(20%) - 층화 추출(stratify) 적용
train_df, test_df = train_test_split(
    df,
    test_size=0.2,
    random_state=42,
    stratify=df["label"]
)



# 4. 저장 (UTF-8-SIG 인코딩)
train_df.to_csv(os.path.join(OUTPUT_DIR, "train.csv"), index=False, encoding="utf-8-sig")
test_df.to_csv(os.path.join(OUTPUT_DIR, "test.csv"), index=False, encoding="utf-8-sig")

print(f"분할 완료:")
print(f"- 원본: {SOURCE_FILE} ({len(df)}건)")
print(f"- Train: {len(train_df)}건 ({len(train_df)/len(df)*100:.1f}%) -> {os.path.join(OUTPUT_DIR, 'train.csv')}")
print(f"- Test : {len(test_df)}건 ({len(test_df)/len(df)*100:.1f}%) -> {os.path.join(OUTPUT_DIR, 'test.csv')}")