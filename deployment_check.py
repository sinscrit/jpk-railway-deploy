#!/usr/bin/env python3
import os
import json

REQUIRED_FILES = [
    'jpk2json/lib/type1000_components.json',
    'jpk2json/lib/type600_components.json', 
    'jpk2json/lib/type900_components.json',
    'jpk2json/lib/type1200_components.json',
    'jpk2json/lib/type1300_components.json',
    'jpk2json/lib/type500_components.json',
    'jpk2json/tmp/type700_document_content.json',
    'jpk2json/tmp/type700_simplified_mapping.json'
]

def audit_deployment():
    results = {}
    for file_path in REQUIRED_FILES:
        exists = os.path.exists(file_path)
        size = os.path.getsize(file_path) if exists else 0
        results[file_path] = {'exists': exists, 'size': size}
        status = "✅" if exists else "❌"
        print(f"{status} {file_path} [{size} bytes]")
    return results

if __name__ == "__main__":
    print("🔍 Auditing converter deployment files...")
    results = audit_deployment()
    
    missing_files = [f for f, info in results.items() if not info['exists']]
    if missing_files:
        print(f"\n❌ {len(missing_files)} files missing:")
        for file in missing_files:
            print(f"   - {file}")
        exit(1)
    else:
        print(f"\n✅ All {len(REQUIRED_FILES)} files present")
        exit(0)
