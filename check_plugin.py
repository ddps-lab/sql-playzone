#!/usr/bin/env python
"""Check if SQL Challenge plugin is loaded"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from CTFd import create_app
from CTFd.plugins.challenges import CHALLENGE_CLASSES

app = create_app()

with app.app_context():
    print("Registered Challenge Types:")
    print("=" * 40)
    for challenge_type, challenge_class in CHALLENGE_CLASSES.items():
        print(f"  - {challenge_type}: {challenge_class.__name__}")
    
    if "sql" in CHALLENGE_CLASSES:
        print("\n✓ SQL Challenge plugin is successfully loaded!")
        sql_class = CHALLENGE_CLASSES["sql"]
        print(f"  Class: {sql_class}")
        print(f"  Templates: {sql_class.templates}")
        print(f"  Scripts: {sql_class.scripts}")
    else:
        print("\n✗ SQL Challenge plugin not found in registered types")