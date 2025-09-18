#!/usr/bin/env python3
import json

def compare_files():
    # Load both files
    with open('standalone_output.json', 'r') as f:
        standalone = json.load(f)
        
    with open('../baseline/baseline_output_v130.json', 'r') as f:
        baseline = json.load(f)

    print("=== DETAILED COMPARISON REPORT ===\n")
    
    # Project level comparison
    s_project = standalone['project']
    b_project = baseline['project']
    
    print("Project Level Properties:")
    for key in sorted(s_project.keys()):
        if key == 'components':
            continue  # We'll handle this separately
        s_val = s_project.get(key)
        b_val = b_project.get(key)
        match = s_val == b_val
        print(f"  {key}: {'✓' if match else '✗'} {'MATCH' if match else 'DIFFER'}")
        if not match:
            print(f"    Standalone: {s_val}")
            print(f"    Baseline:   {b_val}")
    
    print("\nComponent Differences:")
    s_components = s_project['components']
    b_components = b_project['components']
    
    differences = []
    for i, (s_comp, b_comp) in enumerate(zip(s_components, b_components)):
        diffs = []
        for key in sorted(set(s_comp.keys()) | set(b_comp.keys())):
            s_val = s_comp.get(key)
            b_val = b_comp.get(key)
            if s_val != b_val:
                diffs.append(key)
        if diffs:
            differences.append((i, s_comp.get('name', f'Component {i}'), diffs))
    
    if differences:
        print(f"  Found differences in {len(differences)} components:")
        for i, name, diff_keys in differences[:10]:  # Show first 10
            print(f"    [{i}] {name}: {diff_keys}")
            # Show specific differences for first few components
            if i < 3:
                s_comp = s_components[i]
                b_comp = b_components[i]
                for key in diff_keys[:3]:  # Show first 3 different keys
                    s_val = s_comp.get(key, 'MISSING')
                    b_val = b_comp.get(key, 'MISSING')
                    print(f"      {key}: S='{s_val}' vs B='{b_val}'")
    else:
        print("  All components match exactly")
    
    # Content size analysis
    s_total_content = sum(len(comp.get('content', '')) for comp in s_components)
    b_total_content = sum(len(comp.get('content', '')) for comp in b_components)
    
    print(f"\nContent Analysis:")
    print(f"  Standalone total content: {s_total_content:,} chars")
    print(f"  Baseline total content:   {b_total_content:,} chars")
    print(f"  Difference: {b_total_content - s_total_content:,} chars")
    
    # Find specific content differences
    content_diffs = []
    for i, (s_comp, b_comp) in enumerate(zip(s_components, b_components)):
        s_content = s_comp.get('content', '')
        b_content = b_comp.get('content', '')
        if len(s_content) != len(b_content):
            content_diffs.append((i, s_comp.get('name', f'Component {i}'), len(s_content), len(b_content)))
    
    if content_diffs:
        print(f"\n  Components with different content lengths ({len(content_diffs)} total):")
        for i, name, s_len, b_len in content_diffs[:5]:  # Show first 5
            print(f"    [{i}] {name}: {s_len} vs {b_len} chars (diff: {b_len-s_len:+})")

if __name__ == '__main__':
    compare_files()