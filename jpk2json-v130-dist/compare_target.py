#!/usr/bin/env python3
import json

def compare_files():
    # Load standalone output and target baseline
    with open('standalone_output.json', 'r') as f:
        standalone = json.load(f)
        
    with open('../baseline/test_output_v130.json', 'r') as f:
        target_baseline = json.load(f)

    print('=== COMPARISON: Standalone vs Target Baseline ===')
    print(f'Standalone file size: {len(json.dumps(standalone))} characters')
    print(f'Target baseline size: {len(json.dumps(target_baseline))} characters')

    # Compare structure
    s_proj = standalone['project']
    t_proj = target_baseline['project']

    print(f'\nComponents: Standalone={len(s_proj.get("components", []))}, Target={len(t_proj.get("components", []))}')
    print(f'Assets: Standalone={len(s_proj.get("assets", []))}, Target={len(t_proj.get("assets", []))}')
    print(f'Adapters: Standalone={len(s_proj.get("adapters", []))}, Target={len(t_proj.get("adapters", []))}')
    print(f'Workflows: Standalone={len(s_proj.get("workflows", []))}, Target={len(t_proj.get("workflows", []))}')

    # Check first few components to see if they match
    print('\nFirst 5 component names comparison:')
    for i in range(min(5, len(s_proj.get('components', [])), len(t_proj.get('components', [])))):
        s_comp = s_proj['components'][i]
        t_comp = t_proj['components'][i]
        match = s_comp.get('name') == t_comp.get('name')
        print(f'  [{i}] S: {s_comp.get("name")}')
        print(f'      T: {t_comp.get("name")} - {"MATCH" if match else "DIFFER"}')
        if not match:
            print(f'      ID match: {s_comp.get("id") == t_comp.get("id")}')
        print()

    # Check if standalone matches target better than baseline
    print('Key Insight: Does standalone match target baseline?')
    matching_components = 0
    for i in range(min(len(s_proj['components']), len(t_proj['components']))):
        s_comp = s_proj['components'][i]
        t_comp = t_proj['components'][i]
        if s_comp.get('name') == t_comp.get('name'):
            matching_components += 1
    
    match_percentage = (matching_components / len(t_proj['components'])) * 100
    print(f'Component name match rate: {matching_components}/{len(t_proj["components"])} ({match_percentage:.1f}%)')

if __name__ == '__main__':
    compare_files()