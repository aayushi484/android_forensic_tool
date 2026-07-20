import os
import yaml
import unicodedata

def levenshtein_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    return previous_row[-1]

def load_red_flags(config_path: str = None) -> dict:
    """Load keyword config from YAML. Default: bundled red_flags.yaml."""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config', 'red_flags.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def match_keywords(text: str, keywords: dict = None, config_path: str = None) -> list[dict]:
    """Match text against RED-FLAG keywords.
    Returns list of {'keyword': str, 'match_type': 'exact'|'fuzzy', 'matched_text': str, 'score': float, 'language': str}
    """
    if keywords is None:
        keywords = load_red_flags(config_path)
    
    text = unicodedata.normalize('NFC', text)
    text_lower = text.lower()
    
    matches = []
    
    kw_config = keywords.get('keywords', {})
    fuzzy_config = keywords.get('fuzzy', {})
    max_ed = fuzzy_config.get('max_edit_distance', 2)
    min_len = fuzzy_config.get('min_word_length_for_fuzzy', 4)
    
    # Exact matches
    for lang, kws in kw_config.items():
        if not kws: continue
        for kw in kws:
            kw_norm = unicodedata.normalize('NFC', kw).lower()
            if kw_norm in text_lower:
                matches.append({
                    'keyword': kw,
                    'match_type': 'exact',
                    'matched_text': kw_norm,
                    'score': 1.0,
                    'language': lang
                })
    
    # Fuzzy matching on transliteration keywords
    words = text_lower.split()
    transliteration_kws = kw_config.get('transliteration', [])
    for word in words:
        if len(word) >= min_len:
            for kw in transliteration_kws:
                kw_norm = unicodedata.normalize('NFC', kw).lower()
                dist = levenshtein_distance(word, kw_norm)
                if dist <= max_ed and dist > 0:
                    score = 1.0 - (dist / max(len(word), len(kw_norm)))
                    matches.append({
                        'keyword': kw,
                        'match_type': 'fuzzy',
                        'matched_text': word,
                        'score': score,
                        'language': 'transliteration'
                    })
    
    matches.sort(key=lambda x: x['score'], reverse=True)
    return matches
