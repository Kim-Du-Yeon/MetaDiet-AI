"""Pure helpers; no credentials, tracing, or provider I/O on import."""
def pair_payload(case,rows,labels):
    return {'question':case['question'],'gold_answer':case['gold_answer'],'retrieved_context':case['context'],
            **{slot:rows[label].get('answer','') if rows[label]['status']=='completed' else '' for slot,label in zip(['a','b'],labels)}}

def needs_grade(row):
    return row['status']!='completed' and row.get('error',{}).get('reason')in {'generation_failed_or_truncated','timeout'}
