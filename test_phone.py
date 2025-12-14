#!/usr/bin/env python3
"""
Test script to check what data your phone provides
Run this to diagnose network data capture issues
"""

import subprocess
import re
import os

# ADB path - try common locations
ADB_PATH = '/opt/homebrew/bin/adb'  # Default for Apple Silicon Mac
if not os.path.exists(ADB_PATH):
    ADB_PATH = '/usr/local/bin/adb'  # Intel Mac
if not os.path.exists(ADB_PATH):
    ADB_PATH = 'adb'  # Fallback to PATH

def test_command(name, cmd):
    """Test a command and show results"""
    print(f"\n{'='*70}")
    print(f"🔍 Testing: {name}")
    print(f"   Command: {' '.join(cmd)}")
    print(f"{'='*70}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            print(f"❌ Command failed with code {result.returncode}")
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}")
            return None

        output = result.stdout
        print(f"✅ Success! Output length: {len(output)} chars\n")

        return output

    except subprocess.TimeoutExpired:
        print("❌ Command timed out")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def extract_data(output, pattern, label):
    """Extract data using regex"""
    matches = re.findall(pattern, output)
    if matches:
        print(f"   ✅ Found {label}: {matches[:3]}...")
        return matches
    else:
        print(f"   ❌ No {label} found")
        return []

def main():
    print("\n╔═══════════════════════════════════════════════════════════════╗")
    print("║          📱 PHONE DATA DIAGNOSTIC TEST                       ║")
    print("╚═══════════════════════════════════════════════════════════════╝")

    # Test 1: ADB devices
    print("\n📱 Checking ADB connection...")
    result = subprocess.run([ADB_PATH, 'devices'], capture_output=True, text=True)
    print(result.stdout)

    # Test 2: dumpsys telephony.registry (most reliable)
    output = test_command("dumpsys telephony.registry",
                         [ADB_PATH, 'shell', 'dumpsys', 'telephony.registry'])

    if output:
        print("\n📊 Analyzing telephony.registry data:")

        # Look for CellInfo
        cell_info = extract_data(output, r'CellInfoLte:\{[^}]+\}', "CellInfoLte blocks")

        # Look for signal strength
        extract_data(output, r'rssi=(-?\d+)', "RSSI values")
        extract_data(output, r'rsrp=(-?\d+)', "RSRP values")
        extract_data(output, r'rsrq=(-?\d+)', "RSRQ values")

        # Look for cell IDs
        extract_data(output, r'mMcc=(\d+)', "MCC values")
        extract_data(output, r'mMnc=(\d+)', "MNC values")
        extract_data(output, r'mPci=(\d+)', "PCI values")
        extract_data(output, r'mCi=(\d+)', "Cell ID values")

        # Show a sample of the output
        if cell_info:
            print(f"\n📋 Sample CellInfoLte block:")
            print(f"   {cell_info[0][:300]}...")

    # Test 3: cmd phone cell-info
    output = test_command("cmd phone cell-info",
                         [ADB_PATH, 'shell', 'cmd', 'phone', 'cell-info'])

    if output:
        if "Unknown" in output:
            print("   ⚠️  Command not supported (returns 'Unknown command')")
        else:
            print("\n📊 Analyzing cell-info data:")
            extract_data(output, r'CellInfoLte', "CellInfoLte entries")
            extract_data(output, r'rssi=(-?\d+)', "RSSI values")
            print(f"\n📋 First 500 chars:")
            print(f"   {output[:500]}...")

    # Test 4: dumpsys location
    output = test_command("dumpsys location",
                         [ADB_PATH, 'shell', 'dumpsys', 'location'])

    if output:
        print("\n📊 Analyzing location data:")
        locations = extract_data(output, r'Location\[[^\]]+\]', "Location entries")

        # Look for GPS specifically
        gps_locs = extract_data(output, r'last location=Location\[gps[^\]]+\]', "GPS locations")

        if gps_locs:
            print(f"\n📋 Sample GPS location:")
            print(f"   {gps_locs[0]}")

    # Test 5: Device info
    print("\n\n" + "="*70)
    print("📱 Device Information:")
    print("="*70)

    for prop, label in [
        ('ro.product.brand', 'Brand'),
        ('ro.product.model', 'Model'),
        ('ro.build.version.release', 'Android Version'),
        ('ro.build.version.sdk', 'SDK Level'),
    ]:
        result = subprocess.run([ADB_PATH, 'shell', 'getprop', prop],
                              capture_output=True, text=True)
        value = result.stdout.strip()
        print(f"   {label}: {value}")

    # Summary
    print("\n\n╔═══════════════════════════════════════════════════════════════╗")
    print("║                    📝 SUMMARY                                 ║")
    print("╚═══════════════════════════════════════════════════════════════╝")
    print("\nIf you see network data above (RSSI, MCC, PCI, etc.):")
    print("  ✅ Your phone provides network data")
    print("  → Try running: ./start.sh")
    print("  → Check the [MONITOR] logs for detailed extraction info")
    print("\nIf you DON'T see network data:")
    print("  ❌ Your phone may not expose this data via ADB")
    print("  → Some phones require root access")
    print("  → Try enabling Developer Options fully")
    print("  → Check if phone has active SIM card with network")
    print("\n")

if __name__ == '__main__':
    main()
