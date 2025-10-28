import sys
import pandas as pd
import os
import json

# clear potential cached variables
for var in ("df", "excel_data"):
    if var in globals():
        del globals()[var]

if hasattr(pd.io.excel, "_excel_readers"):
    pd.io.excel._excel_readers.clear()

path = "cross_table.xlsx"
if not os.path.exists(path):
    raise FileNotFoundError(f"Expected updated file at {path}")

df = pd.read_excel(path)
df = df.rename(columns={"Region": "region_1"})  # only needed if Excel header is 'Region'
print("✅ Reloaded fresh copy of Excel file.")

# convert to long form
long_df = (
    df.melt(id_vars=["region_1"], var_name="region_2", value_name="mapping")
      .dropna(subset=["mapping"])
)

# write outputs
csv_path = "cross_table_long.csv"
json_path = "cross_table_long.json"

long_df.to_csv(csv_path, index=False)
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(long_df.to_dict(orient="records"), f, indent=2, ensure_ascii=False)

print(f"✅ Conversion complete!\n- CSV: {csv_path}\n- JSON: {json_path}")
