#!/usr/bin/env python3
import sys, os
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import config
from backend import data_module

provider = data_module.get_provider('yfinance')
results = {}
for s in config.SYMBOL_MAP.keys():
    try:
        cache_path = None
        if hasattr(provider, '_get_cache_path'):
            cache_path = provider._get_cache_path(s, config.DEFAULT_TIMEFRAME)
        df = data_module.load_symbol(s, config.DEFAULT_TIMEFRAME, count=10, provider_type='yfinance')
        results[s] = {'bars': len(df), 'cache': cache_path}
    except Exception as e:
        results[s] = {'error': str(e)}

import json
print(json.dumps(results, indent=2))
