with open('tests/test_integration.py', 'r') as f:
    code = f.read()

fix = "import sys, os\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))\n"

if "sys.path.insert" not in code:
    with open('tests/test_integration.py', 'w') as f:
        f.write(fix + code)
    print("✅ SUCCESS: Python path fixed for tests!")
