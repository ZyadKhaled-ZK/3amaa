import sys
sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

import os
DATA_PATH = os.path.join(os.path.dirname(__file__), 'data.parquet')

print('Loading data...', flush=True)
df = pd.read_parquet(DATA_PATH)
df.columns = df.columns.str.strip()
print(f'Loaded {len(df)} records', flush=True)

df['seating_no'] = df['seating_no'].astype(str)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search():
    data = request.get_json()
    query = data.get('query', '').strip()
    search_by = data.get('searchBy', 'seating_no')

    if not query:
        return jsonify({'error': 'يرجى إدخال رقم الجلوس أو الاسم'})

    if search_by == 'seating_no':
        result = df[df['seating_no'] == query]
    else:
        result = df[df['arabic_name'].str.contains(query, case=False, na=False)]

    if result.empty:
        return jsonify({'error': 'لا توجد نتائج للبحث المطلوب'})

    row = result.iloc[0]
    return jsonify({
        'seating_no': row['seating_no'],
        'arabic_name': row['arabic_name'],
        'total_degree': row['total_degree'],
        'student_case_desc': row['student_case_desc']
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
