#!/usr/bin/env python3
import json

def analyze_json(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    print(f'Analysis of {filepath}:')
    if 'project' in data:
        project = data['project']
        print(f'  Project name: {project.get("name", "N/A")}')
        print(f'  Components: {len(project.get("components", []))}')
        print(f'  Assets: {len(project.get("assets", []))}')
        print(f'  APIs: {len(project.get("apis", []))}')
        print(f'  Adapters: {len(project.get("adapters", []))}')
        print(f'  Workflows: {len(project.get("workflows", []))}')
        
        # Component type breakdown
        components = project.get('components', [])
        component_types = {}
        for comp in components:
            comp_type = comp.get('type', 'unknown')
            component_types[comp_type] = component_types.get(comp_type, 0) + 1
        print(f'  Component types: {dict(sorted(component_types.items()))}')
    else:
        print('  No project key found')
    
    print(f'  Total file size: {len(json.dumps(data))} characters')
    print()

if __name__ == '__main__':
    analyze_json('standalone_output.json')
    analyze_json('../baseline/baseline_output_v130.json')