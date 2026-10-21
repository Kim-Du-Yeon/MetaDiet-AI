"""Bounded atomic JSON persistence; retries file replacement, never API calls."""
import json,time

def save_json(path,value):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    for attempt in range(6):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==5:raise
            time.sleep(.02*(attempt+1))
