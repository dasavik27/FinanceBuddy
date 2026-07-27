import os

files_to_fix = [
    "routers/tabs/journey.py",
    "routers/tabs/performance.py",
    "routers/tabs/compare.py",
    "routers/auth.py",
    "core/sessions.py",
    "core/finance.py",
    "core/cache.py",
    "core/parser.py",
    "core/storage.py",
    "services/market_indices.py",
    "services/providers/yahoo.py",
    "services/providers/mfapi.py",
    "services/market_data.py"
]

for file in files_to_fix:
    path = os.path.join("backend", file)
    with open(path, "r") as f:
        lines = f.readlines()
        
    # Remove existing bad injections
    clean_lines = []
    for line in lines:
        if line.strip() == "import logging":
            continue
        if line.strip() == "logger = logging.getLogger(__name__)":
            continue
        clean_lines.append(line)
        
    # Find safe insertion point (after top docstring)
    insert_idx = 0
    in_docstring = False
    for i, line in enumerate(clean_lines):
        if line.strip().startswith('"""') or line.strip().startswith("'''"):
            if in_docstring:
                in_docstring = False
                insert_idx = i + 1
                break
            else:
                in_docstring = True
                
    injection = "import logging\nlogger = logging.getLogger(__name__)\n\n"
    clean_lines.insert(insert_idx, injection)
    
    with open(path, "w") as f:
        f.writelines(clean_lines)
    print(f"Fixed correctly {path}")
