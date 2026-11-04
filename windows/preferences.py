import json
from pathlib import Path

def proxy_enabled(data: Path) -> bool:
    file = data / 'onegram-preferences.json'
    if not file.exists():
        return True
    payload = json.loads(file.read_text(encoding='utf-8-sig'))
    value = payload.get('proxy_enabled', True)
    if type(value) is not bool:
        raise ValueError('Invalid OneGram proxy preference')
    return value
