#!/usr/bin/env python3
import py_compile
import sys

files = ["config.py", "logger.py", "movida_playwright.py", "emailnator_module.py", "pessoa_generator.py", "main.py"]
ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"  OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"  FAIL: {f} -> {e}")
        ok = False

if ok:
    print("\nTodos os modulos compilam corretamente!")
else:
    print("\nErros encontrados!")
    sys.exit(1)
