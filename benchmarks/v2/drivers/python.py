import importlib, json, sys
sys.path.insert(0, "/work")
module, function = sys.argv[1].rsplit(".", 1)
try:
    result = getattr(importlib.import_module(module), function)(*json.load(sys.stdin))
    print(json.dumps({"value": result}))
except Exception as error:
    print(json.dumps({"exception": type(error).__name__}))
