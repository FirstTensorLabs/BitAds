# Validator package version
__version__ = '0.0.1'


def _version_to_int(version_str: str) -> int:
    """
    Convert version string (e.g., '0.0.1') to integer.
    Removes leading zero segments and concatenates remaining parts.
    
    Args:
        version_str: Version string like '0.0.1', '0.1.5', '1.2.3', etc.
    
    Returns:
        Integer version after removing leading zeros and concatenating
    
    Examples:
        '0.0.1' -> 1   (0,0,1 -> skip leading zeros -> 1)
        '0.1.5' -> 15  (0,1,5 -> skip leading zero -> 1,5 -> 15)
        '1.2.3' -> 123 (1,2,3 -> no leading zeros -> 123)
    """
    try:
        # Split by '.' and convert to integers
        parts = [int(part) for part in version_str.split('.')]
        
        # Remove leading zero segments
        while parts and parts[0] == 0:
            parts.pop(0)
        
        # If all parts were zeros, return 1
        if not parts:
            return 1
        
        # Concatenate remaining parts as string, then convert to int
        return int(''.join(str(part) for part in parts))
    except (ValueError, AttributeError):
        pass
    # Fallback to 1 if conversion fails
    return 1


# Convert __version__ string to integer for version_key
version_as_int = _version_to_int(__version__)
    