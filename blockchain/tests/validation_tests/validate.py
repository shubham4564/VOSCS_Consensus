#!/usr/bin/env python3
"""
Validation Test Runner
=====================

This script provides easy access to all validation tests.
Run specific validation tests or all tests with simple commands.
"""

import sys
import os
import argparse
from pathlib import Path

# Add blockchain modules to path
blockchain_root = Path(__file__).parent.parent
sys.path.insert(0, str(blockchain_root))

def run_leader_schedule_validation():
    """Run real-time leader schedule validation"""
    print("🚀 Starting Leader Schedule Validation...")
    print("=" * 60)
    
    try:
        from leader_schedule_validator import main as leader_validator_main
        return leader_validator_main()
    except ImportError as e:
        print(f"❌ Cannot import leader schedule validator: {e}")
        return False
    except Exception as e:
        print(f"❌ Leader schedule validation failed: {e}")
        return False

def run_all_validations():
    """Run all available validation tests"""
    print("🧪 RUNNING ALL VALIDATION TESTS")
    print("=" * 60)
    
    tests = [
        ("Leader Schedule Validation", run_leader_schedule_validation),
        # Add more validation tests here as they are created
    ]
    
    results = {}
    
    for test_name, test_func in tests:
        print(f"\n📊 Running: {test_name}")
        print("-" * 40)
        
        try:
            success = test_func()
            results[test_name] = success
            status = "✅ PASSED" if success else "❌ FAILED"
            print(f"{status}: {test_name}")
        except Exception as e:
            results[test_name] = False
            print(f"❌ ERROR in {test_name}: {e}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("📋 VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, success in results.items():
        status = "✅ PASSED" if success else "❌ FAILED"
        print(f"{status} {test_name}")
    
    print("-" * 60)
    print(f"📊 Overall: {passed}/{total} tests passed")
    
    return passed == total

def list_available_validations():
    """List all available validation tests"""
    print("🧪 AVAILABLE VALIDATION TESTS")
    print("=" * 60)
    print("1. leader-schedule  - Real-time leader schedule monitoring")
    print("   Command: python3 validate.py leader-schedule")
    print()
    print("2. all             - Run all validation tests")
    print("   Command: python3 validate.py all")
    print()
    print("To add more validation tests, create new test files in this directory")
    print("and update the validate.py runner.")

def main():
    """Main validation runner"""
    parser = argparse.ArgumentParser(
        description="Blockchain Validation Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available validation tests:
  leader-schedule    Real-time leader schedule monitoring
  all               Run all validation tests
  list              List available validation tests

Examples:
  python3 validate.py leader-schedule
  python3 validate.py all
  python3 validate.py list
        """
    )
    
    parser.add_argument(
        'test',
        nargs='?',
        default='list',
        help='Validation test to run (default: list)'
    )
    
    parser.add_argument(
        '--update-interval',
        type=float,
        default=2.0,
        help='Update interval for real-time tests (default: 2.0 seconds)'
    )
    
    args = parser.parse_args()
    
    # Change to validation tests directory
    validation_dir = Path(__file__).parent
    os.chdir(validation_dir)
    
    if args.test == 'leader-schedule':
        print(f"📊 Update interval: {args.update_interval}s")
        return run_leader_schedule_validation()
    
    elif args.test == 'all':
        return run_all_validations()
    
    elif args.test == 'list':
        list_available_validations()
        return True
    
    else:
        print(f"❌ Unknown validation test: {args.test}")
        print("Use 'python3 validate.py list' to see available tests")
        return False

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Validation interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"❌ Validation runner error: {e}")
        sys.exit(1)
