
def filter_adapters_by_usage(baseline_adapters: List[Dict[str, Any]], 
                           jpk_components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filter adapters to only include those actually used by JPK components.
    
    Args:
        baseline_adapters: List of adapters from baseline JSON
        jpk_components: List of components generated from JPK
    
    Returns:
        Filtered list of adapters that are actually used
    """
    # Built-in adapters that don't need explicit definition
    BUILTIN_ADAPTERS = {'tempstorage', 'salesforce', 'netsuite'}
    
    # Find adapters actually used by JPK components
    used_adapters = set()
    for comp in jpk_components:
        adapter_id = comp.get('adapterId')
        if adapter_id and adapter_id not in BUILTIN_ADAPTERS:
            used_adapters.add(adapter_id)
    
    # Filter baseline adapters to only include used ones
    filtered_adapters = []
    for adapter in baseline_adapters:
        adapter_id = adapter.get('id')
        
        # Skip if not used by JPK components
        if adapter_id not in used_adapters:
            print(f"   🚫 Filtering unused adapter: {adapter_id}")
            continue
        
        # Validate adapter properties
        if has_null_default_values(adapter):
            print(f"   ❌ Skipping adapter with null defaultValue: {adapter_id}")
            continue
        
        filtered_adapters.append(adapter)
        print(f"   ✅ Including used adapter: {adapter_id}")
    
    return filtered_adapters

def has_null_default_values(adapter: Dict[str, Any]) -> bool:
    """Check if adapter has properties with null defaultValue."""
    properties = adapter.get('endpoint', {}).get('properties', [])
    for prop in properties:
        if prop.get('defaultValue') is None and prop.get('name') != 'entityId':
            return True
    return False
