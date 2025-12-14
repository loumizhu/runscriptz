#!/usr/bin/env python3
"""
Debug script for hotkey testing
"""

def main():
    """Test function for hotkey debugging"""
    print("=== Hotkey Debug Test ===")
    print("This script is running via hotkey!")
    
    # Test Krita API access
    try:
        from krita import Krita
        app = Krita.instance()
        if app:
            print("✓ Krita instance found")
            doc = app.activeDocument()
            if doc:
                print(f"✓ Active document: {doc.name()}")
            else:
                print("⚠ No active document")
        else:
            print("✗ No Krita instance found")
    except Exception as e:
        print(f"✗ Error accessing Krita API: {e}")
    
    print("=== End Debug Test ===")

if __name__ == "__main__":
    main()
