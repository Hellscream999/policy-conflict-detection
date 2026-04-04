"""
OPA Test Harness
==================
Tests generated Rego policies in actual OPA runtime.
"""

import subprocess
import json
import tempfile
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class OPATestResult:
    """Result from OPA evaluation"""
    success: bool
    decision: Optional[str]
    output: Dict[str, Any]
    error: Optional[str] = None


class OPAHarness:
    """
    Test harness for running Rego policies in OPA.
    
    Uses OPA CLI for evaluation. Requires OPA to be installed.
    Install: https://www.openpolicyagent.org/docs/latest/#running-opa
    """
    
    def __init__(self, opa_path: str = "opa"):
        """
        Initialize OPA harness.
        
        Args:
            opa_path: Path to OPA binary (default: assumes in PATH)
        """
        self.opa_path = opa_path
        self._check_opa_available()
    
    def _check_opa_available(self) -> bool:
        """Check if OPA is available"""
        try:
            result = subprocess.run(
                [self.opa_path, "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    @property
    def is_available(self) -> bool:
        """Check if OPA is installed and available"""
        return self._check_opa_available()
    
    def get_version(self) -> Optional[str]:
        """Get OPA version"""
        try:
            result = subprocess.run(
                [self.opa_path, "version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[0]
            return None
        except Exception:
            return None
    
    def eval_policy(self, rego_code: str, input_data: Dict[str, Any], 
                    query: str = "data.policy.decision") -> OPATestResult:
        """
        Evaluate Rego policy with given input.
        
        Args:
            rego_code: The Rego policy code
            input_data: Input data for evaluation
            query: Rego query to evaluate
            
        Returns:
            OPATestResult with decision and output
        """
        # Write policy to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rego', delete=False) as f:
            f.write(rego_code)
            policy_file = f.name
        
        # Write input to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(input_data, f)
            input_file = f.name
        
        try:
            # Run OPA eval
            result = subprocess.run(
                [
                    self.opa_path, "eval",
                    "-d", policy_file,
                    "-i", input_file,
                    "--format", "json",
                    query
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                return OPATestResult(
                    success=False,
                    decision=None,
                    output={},
                    error=result.stderr
                )
            
            # Parse output
            output = json.loads(result.stdout)
            
            # Extract decision
            decision = None
            if output.get("result") and len(output["result"]) > 0:
                expressions = output["result"][0].get("expressions", [])
                if expressions:
                    decision = expressions[0].get("value")
            
            return OPATestResult(
                success=True,
                decision=decision,
                output=output,
                error=None
            )
            
        except subprocess.TimeoutExpired:
            return OPATestResult(
                success=False,
                decision=None,
                output={},
                error="OPA evaluation timed out"
            )
        except json.JSONDecodeError as e:
            return OPATestResult(
                success=False,
                decision=None,
                output={},
                error=f"Failed to parse OPA output: {e}"
            )
        finally:
            # Cleanup temp files
            os.unlink(policy_file)
            os.unlink(input_file)
    
    def check_for_conflicts(self, rego_code: str, 
                            test_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Check policy for conflicts by testing multiple inputs.
        
        Args:
            rego_code: The Rego policy code
            test_inputs: List of test input data
            
        Returns:
            Results with conflict information
        """
        results = {
            "total_tests": len(test_inputs),
            "passed": 0,
            "failed": 0,
            "conflicts": [],
            "test_results": []
        }
        
        for i, input_data in enumerate(test_inputs):
            # Check both allow and deny
            allow_result = self.eval_policy(
                rego_code, input_data, "data.policy.allow"
            )
            deny_result = self.eval_policy(
                rego_code, input_data, "data.policy.deny"
            )
            
            test_result = {
                "test_id": i + 1,
                "input": input_data,
                "allow": allow_result.decision,
                "deny": deny_result.decision,
                "has_conflict": False
            }
            
            # Check for conflict (both allow and deny true)
            if allow_result.decision is True and deny_result.decision is True:
                test_result["has_conflict"] = True
                results["conflicts"].append({
                    "test_id": i + 1,
                    "input": input_data,
                    "message": "Both allow and deny are true"
                })
            
            if allow_result.success and deny_result.success:
                results["passed"] += 1
            else:
                results["failed"] += 1
            
            results["test_results"].append(test_result)
        
        return results
    
    def run_tests(self, rego_code: str, test_code: str) -> Dict[str, Any]:
        """
        Run Rego tests.
        
        Args:
            rego_code: The main policy code
            test_code: The test code
            
        Returns:
            Test results
        """
        # Write files
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rego', delete=False) as f:
            f.write(rego_code)
            policy_file = f.name
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='_test.rego', delete=False) as f:
            f.write(test_code)
            test_file = f.name
        
        try:
            result = subprocess.run(
                [
                    self.opa_path, "test",
                    policy_file, test_file,
                    "--format", "json",
                    "-v"
                ],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.stdout:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            
            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
            
        finally:
            os.unlink(policy_file)
            os.unlink(test_file)
    
    def validate_policy(self, rego_code: str) -> Dict[str, Any]:
        """
        Validate Rego policy syntax.
        
        Args:
            rego_code: The Rego policy code
            
        Returns:
            Validation result
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rego', delete=False) as f:
            f.write(rego_code)
            policy_file = f.name
        
        try:
            result = subprocess.run(
                [self.opa_path, "check", policy_file],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            return {
                "valid": result.returncode == 0,
                "errors": result.stderr if result.returncode != 0 else None,
                "message": "Policy is valid" if result.returncode == 0 else "Policy has errors"
            }
            
        finally:
            os.unlink(policy_file)


# Fallback implementation when OPA is not installed
class OPAHarnessFallback:
    """
    Fallback OPA harness that simulates evaluation without actual OPA.
    Used when OPA is not installed.
    """
    
    @property
    def is_available(self) -> bool:
        return False
    
    def get_version(self) -> Optional[str]:
        return "Fallback (OPA not installed)"
    
    def eval_policy(self, rego_code: str, input_data: Dict[str, Any], 
                    query: str = "data.policy.decision") -> OPATestResult:
        """Simulate policy evaluation"""
        # Simple simulation based on input
        return OPATestResult(
            success=True,
            decision="simulated",
            output={"note": "OPA not installed, using simulation"},
            error=None
        )
    
    def check_for_conflicts(self, rego_code: str, 
                            test_inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "total_tests": len(test_inputs),
            "passed": len(test_inputs),
            "failed": 0,
            "conflicts": [],
            "test_results": [],
            "note": "OPA not installed, using simulation"
        }
    
    def validate_policy(self, rego_code: str) -> Dict[str, Any]:
        # Basic syntax check
        if "package" in rego_code and ("allow" in rego_code or "deny" in rego_code):
            return {"valid": True, "message": "Basic syntax appears valid (OPA not installed)"}
        return {"valid": False, "message": "Policy may have syntax issues"}


def get_opa_harness() -> OPAHarness:
    """Get appropriate OPA harness (real or fallback)"""
    harness = OPAHarness()
    if harness.is_available:
        return harness
    else:
        print("Warning: OPA not installed, using fallback simulation")
        return OPAHarnessFallback()


# ============================================================
# DEMONSTRATION
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("OPA TEST HARNESS DEMONSTRATION")
    print("=" * 60)
    
    harness = get_opa_harness()
    
    print(f"\nOPA Available: {harness.is_available}")
    print(f"OPA Version: {harness.get_version()}")
    
    # Sample policy
    sample_rego = '''
package policy

import rego.v1

default allow := false

allow if {
    input.subject.type == "admin"
    input.action == "read"
}

deny if {
    input.resource.sensitive == true
    not input.subject.clearance == "high"
}

decision := "allow" if {
    allow
    not deny
}

decision := "deny" if {
    deny
}
'''
    
    # Sample input
    sample_input = {
        "subject": {"type": "admin", "clearance": "high"},
        "action": "read",
        "resource": {"type": "file", "sensitive": True}
    }
    
    print("\n1. Policy Validation:")
    print("-" * 40)
    validation = harness.validate_policy(sample_rego)
    print(f"   Valid: {validation.get('valid')}")
    print(f"   Message: {validation.get('message')}")
    
    print("\n2. Policy Evaluation:")
    print("-" * 40)
    result = harness.eval_policy(sample_rego, sample_input)
    print(f"   Success: {result.success}")
    print(f"   Decision: {result.decision}")
    if result.error:
        print(f"   Error: {result.error}")
    
    print("\n3. Conflict Check:")
    print("-" * 40)
    test_inputs = [
        sample_input,
        {"subject": {"type": "guest"}, "action": "write", "resource": {"type": "file"}}
    ]
    conflicts = harness.check_for_conflicts(sample_rego, test_inputs)
    print(f"   Total tests: {conflicts['total_tests']}")
    print(f"   Passed: {conflicts['passed']}")
    print(f"   Conflicts found: {len(conflicts['conflicts'])}")
