"""Flow execution engine for FlowForge."""

import os
import sys
import json
import yaml
import copy
import re
import time
from pathlib import Path
from typing import Dict, Any, List, Set, Optional, Union
from datetime import datetime, timedelta, timezone

# Import licensing
from packages.core.licensing import has_feature
from packages.sdk.plugin_loader import load_plugins


# Define a base path for flows if not passed explicitly
DEFAULT_FLOWS_DIR = Path(__file__).parent.parent / "flows"

class FlowEngine:
    """Execute flows by stepping through their definitions with proper control flow handling."""

    def __init__(self, registry, debug_mode=False, base_flows_path: Path = DEFAULT_FLOWS_DIR, parent_context: Optional[Dict[str, Any]] = None):
        self.registry = registry
        self.debug_mode = debug_mode
        self.base_flows_path = base_flows_path

        self.step_results: Dict[str, Any] = {}
        self.executed_step_count_total: int = 0
        self.loop_counters: Dict[str, int] = {}
        self.retry_counters: Dict[str, int] = {}
        self.terminated: bool = False
        self.termination_message: Optional[str] = None

        # Variables management enhancements
        self.flow_variables: Dict[str, Any] = {}  # Local flow-scoped variables
        self.environment = os.environ.copy()      # Environment variables 
        
        # Initialize flow variables from parent context if provided
        if parent_context:
            self.flow_variables.update(parent_context)
            self.current_flow_inputs = copy.deepcopy(parent_context)
        else:
            self.current_flow_inputs = {}


    def execute_flow(self, flow_definition: Union[Dict[str, Any], Path], flow_inputs: Optional[Dict[str, Any]] = None):
        flow: Dict[str, Any]
        flow_id: str

        if isinstance(flow_definition, Path):
            flow_file_path = flow_definition
            if not flow_file_path.is_absolute():
                flow_file_path = (self.base_flows_path / flow_file_path).resolve()

            if not flow_file_path.exists():
                raise FileNotFoundError(f"Flow file not found: {flow_file_path}")
            with open(flow_file_path, 'r') as f:
                flow = yaml.safe_load(f)
            flow_id = flow.get('id', flow_file_path.stem)
        elif isinstance(flow_definition, dict):
            flow = flow_definition
            flow_id = flow.get('id', 'unnamed_inline_flow')
        else:
            raise TypeError("flow_definition must be a dict or a Path object.")

        if flow_inputs:
            self.current_flow_inputs.update(flow_inputs)
            # Also add flow inputs to flow variables
            self.flow_variables.update(flow_inputs)

        self.step_results = {"flow_input": copy.deepcopy(self.current_flow_inputs)} if self.current_flow_inputs else {}
        self.executed_step_count_total = 0
        self.loop_counters = {}
        self.retry_counters = {}
        self.terminated = False
        self.termination_message = None

        steps = flow.get('steps', [])
        if not steps:
            print(f"Warning: Flow '{flow_id}' contains no steps.")
            return {}

        print("\n" + "=" * 40)
        print(f"Executing flow: {flow_id} (Inputs: {self.current_flow_inputs if self.current_flow_inputs else 'None'})")
        if self.flow_variables:
            print(f"Flow Variables: {self.flow_variables}")
        print("=" * 40 + "\n")

        step_lookup = {step['id']: step for step in steps}
        current_step_id = steps[0]['id']
        executed_main_step_ids = []

        while current_step_id and not self.terminated:
            if current_step_id not in step_lookup:
                raise ValueError(f"Step '{current_step_id}' not found in flow '{flow_id}'")

            step_def_obj = step_lookup[current_step_id]
            s_id = step_def_obj['id']
            action = step_def_obj.get('action', '')
            result = None

            if action.startswith('control.'):
                control_type = action.split('.')[1]
                if control_type in ['while_loop', 'while']:
                    result = self._execute_while_loop(step_def_obj, step_lookup)
                elif control_type == 'for_each':
                    result = self._execute_for_each(step_def_obj, step_lookup)
                elif control_type == 'parallel':
                    result = self._execute_parallel(step_def_obj, step_lookup)
                elif control_type in ['try_catch', 'try_except', 'try']:
                    result = self._execute_try_catch(step_def_obj, step_lookup)
                elif control_type == 'retry':
                    result = self._execute_retry(step_def_obj, step_lookup)
                elif control_type == 'subflow':
                    result = self._execute_subflow_wrapper(step_def_obj)
                elif control_type == 'delay':
                    result = self._execute_delay(step_def_obj)
                elif control_type == 'wait_for':
                    result = self._execute_wait_for(step_def_obj)
                elif control_type == 'terminate':
                    result = self._execute_terminate(step_def_obj)
                else:
                    result = self._execute_step_action(step_def_obj)
            else:
                result = self._execute_step_action(step_def_obj)

            self.step_results[s_id] = result
            if s_id not in executed_main_step_ids: executed_main_step_ids.append(s_id)

            if self.terminated:
                print(f"Flow execution terminated by step '{s_id}': {self.termination_message or 'No message provided'}")
                break

            current_step_id = self._get_next_step(step_def_obj, result, steps)

        print("\n" + "=" * 40)
        final_output_result: Any = {}
        if self.terminated:
            print(f"Flow Terminated: {flow_id}")
            print(f"Message: {self.termination_message or 'No message provided'}")
            last_step_id_executed = executed_main_step_ids[-1] if executed_main_step_ids else None
            final_output_result = {"terminated": True, "message": self.termination_message, "last_step_results": self.step_results.get(last_step_id_executed)}
        else:
            print(f"Flow Completed: {flow_id}")
            last_step_id_executed = executed_main_step_ids[-1] if executed_main_step_ids else None
            if last_step_id_executed:
                 final_output_result = self.step_results.get(last_step_id_executed, {})
                 print(f"Final Result (from step '{last_step_id_executed}'):")
            else:
                 print(f"Final Result (No steps executed or flow empty):")
                 final_output_result = self.step_results

            try:
                print(json.dumps(final_output_result, indent=2, default=str))
            except TypeError:
                print(str(final_output_result))
        
        # Include flow variables in the output if present
        if self.flow_variables:
            print(f"\nFinal Flow Variables:")
            for name, value in sorted(self.flow_variables.items()):
                print(f"  {name} = {repr(value)}")
        
        return final_output_result

    def _get_next_step(self, current_step: Dict[str, Any], result: Any, main_flow_steps: List[Dict[str, Any]]) -> Optional[str]:
        step_id = current_step['id']
        action = current_step.get('action', '')

        if action.startswith('control.'):
            action_type = action.split('.')[1]
            processed_control_inputs = self._process_inputs(current_step.get('inputs', {}))

            if action_type in ['if_node', 'if']:
                condition_eval_result = result.get('result', False)
                return processed_control_inputs.get('then_step') if condition_eval_result else processed_control_inputs.get('else_step')

            if action_type == 'switch':
                matched_case_step_id = result.get('matched_case')
                return matched_case_step_id

        current_index_in_main_flow = next((i for i, s_def in enumerate(main_flow_steps) if s_def['id'] == step_id), -1)
        if current_index_in_main_flow != -1 and current_index_in_main_flow < len(main_flow_steps) - 1:
            return main_flow_steps[current_index_in_main_flow + 1]['id']

        return None

    def _resolve_subflow_definitions(self, subflow_spec: Union[List[Dict[str, Any]], List[str], str], main_step_lookup: Dict[str, Dict[str, Any]], context_step_id: str, subflow_type: str) -> List[Dict[str, Any]]:
        resolved_step_definitions = []
        step_ids_in_order = self._prepare_subflow_steps(subflow_spec)

        inline_definitions_lookup = {}
        if isinstance(subflow_spec, list) and subflow_spec and isinstance(subflow_spec[0], dict):
            inline_definitions_lookup = {s['id']: s for s in subflow_spec if 'id' in s}

        for step_id_to_exec in step_ids_in_order:
            definition = inline_definitions_lookup.get(step_id_to_exec)
            if not definition:
                definition = main_step_lookup.get(step_id_to_exec)
            if not definition:
                raise ValueError(f"Subflow step '{step_id_to_exec}' for {subflow_type} '{context_step_id}' not found in main flow or inline definition.")
            resolved_step_definitions.append(definition)
        return resolved_step_definitions

    def _execute_while_loop(self, while_step_def: Dict[str, Any], main_step_lookup: Dict[str, Dict[str, Any]]):
        step_id = while_step_def['id']
        inputs = while_step_def.get('inputs', {})

        condition_expr = inputs.get('condition', 'False')
        subflow_spec = inputs.get('subflow', [])
        max_iterations = int(self._process_inputs({"val": inputs.get('max_iterations', 100)}).get("val", 100))

        # Identify condition variables in the inputs
        condition_var_to_source_ref: Dict[str, str] = {}
        parsed_vars_in_condition = set(re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', condition_expr))
        for var_name in parsed_vars_in_condition:
            if var_name in inputs:
                source_ref_candidate = inputs[var_name]
                if isinstance(source_ref_candidate, str) and '.' in source_ref_candidate:
                    condition_var_to_source_ref[var_name] = source_ref_candidate
                elif self.debug_mode:
                    print(f"DEBUG (while_loop '{step_id}'): Condition var '{var_name}' from expr is in inputs, "
                          f"but its value '{source_ref_candidate}' is not a 'step.output' string. "
                          f"State update for it via subflow might not be standard.")

        if not condition_var_to_source_ref and self.debug_mode:
            print(f"DEBUG (while_loop '{step_id}'): No direct 'step.output' source_refs identified for condition variables "
                  f"from inputs. Condition: '{condition_expr}', Relevant input keys: {list(inputs.keys())}. "
                  f"Loop progression may depend on external state or subflow side-effects not tracked by this mechanism.")
        elif self.debug_mode:
            print(f"DEBUG (while_loop '{step_id}'): Identified condition variable source_refs: {condition_var_to_source_ref}")

        self.loop_counters[step_id] = 0
        iteration_results_list = []

        subflow_step_definitions = self._resolve_subflow_definitions(subflow_spec, main_step_lookup, step_id, "while_loop")

        # Determine the sub-step that updates the loop's state variables
        updater_sub_step_id: Optional[str] = inputs.get("loop_variable_updater_step")
        updater_sub_step_output_key: str = inputs.get("loop_variable_updater_output", "value")

        if not updater_sub_step_id and subflow_step_definitions:
            conventional_updater_name = "update_loop_total"
            if any(s['id'] == conventional_updater_name for s in subflow_step_definitions):
                updater_sub_step_id = conventional_updater_name
            else:
                updater_sub_step_id = subflow_step_definitions[-1]['id']

            if self.debug_mode:
                print(f"DEBUG (while_loop '{step_id}'): 'loop_variable_updater_step' not specified in inputs. "
                      f"Heuristically set to subflow step '{updater_sub_step_id}' (output key: '{updater_sub_step_output_key}').")

        print(f"--- Executing Control: {step_id} (control.while_loop) ---")

        condition_vars_for_eval = self._prepare_condition_inputs(condition_expr, inputs)
        condition_result = self._evaluate_condition(condition_expr, condition_vars_for_eval)
        print(f"Initial condition for '{step_id}': \"{condition_expr}\" -> {condition_result} (vars: {condition_vars_for_eval})")

        while condition_result and self.loop_counters[step_id] < max_iterations and not self.terminated:
            self.loop_counters[step_id] += 1
            iteration_num = self.loop_counters[step_id]
            print(f"\n--- While Loop '{step_id}' Iteration {iteration_num} ---")

            current_iteration_sub_results = {}
            for sub_step_def in subflow_step_definitions:
                sub_result = self._execute_step_action(sub_step_def)
                self.step_results[sub_step_def['id']] = sub_result
                current_iteration_sub_results[sub_step_def['id']] = sub_result
                if self.terminated: break

            iteration_results_list.append(current_iteration_sub_results)
            if self.terminated: break

            # After subflow iteration, update the identified state locations using the updater sub-step's output
            if updater_sub_step_id and updater_sub_step_id in current_iteration_sub_results:
                updater_step_full_result = current_iteration_sub_results[updater_sub_step_id]
                if isinstance(updater_step_full_result, dict):
                    new_value_from_updater = updater_step_full_result.get(updater_sub_step_output_key)

                    if new_value_from_updater is not None:
                        # Also update flow variables if the updater is a variables.set action
                        sub_step = next((s for s in subflow_step_definitions if s['id'] == updater_sub_step_id), None)
                        if sub_step and sub_step.get('action', '').startswith('variables.set'):
                            var_name = sub_step.get('inputs', {}).get('name')
                            if var_name:
                                self.flow_variables[var_name] = new_value_from_updater
                                if self.debug_mode:
                                    print(f"DEBUG (while_loop '{step_id}'): Updated flow variable '{var_name}' to '{new_value_from_updater}'")

                        if not condition_var_to_source_ref and self.debug_mode:
                             print(f"DEBUG (while_loop '{step_id}'): Updater step '{updater_sub_step_id}' produced value '{new_value_from_updater}', "
                                   f"but no specific condition source_refs were identified to update. Loop state might not change as expected.")

                        for cond_var_name, source_ref_str in condition_var_to_source_ref.items():
                            source_parts = source_ref_str.split('.', 1)
                            if len(source_parts) == 2:
                                target_step_id_for_state, target_key_for_state = source_parts

                                if target_step_id_for_state not in self.step_results:
                                    self.step_results[target_step_id_for_state] = {}

                                if isinstance(self.step_results[target_step_id_for_state], dict):
                                    self.step_results[target_step_id_for_state][target_key_for_state] = new_value_from_updater
                                    if self.debug_mode:
                                        print(f"DEBUG (while_loop '{step_id}'): Updated state '{source_ref_str}' (for condition var '{cond_var_name}') "
                                              f"to '{new_value_from_updater}' from subflow step '{updater_sub_step_id}.{updater_sub_step_output_key}'.")
                                elif self.debug_mode:
                                    print(f"DEBUG (while_loop '{step_id}'): Cannot update state for '{source_ref_str}'; "
                                          f"target step_results['{target_step_id_for_state}'] is not a dict.")
                            elif self.debug_mode:
                                print(f"DEBUG (while_loop '{step_id}'): Malformed source_ref_str '{source_ref_str}' for condition var '{cond_var_name}'. Cannot update state.")
                    elif self.debug_mode:
                        print(f"DEBUG (while_loop '{step_id}'): Updater sub-step '{updater_sub_step_id}' did not produce expected output key '{updater_sub_step_output_key}'. Result: {updater_step_full_result}")
                elif self.debug_mode:
                    print(f"DEBUG (while_loop '{step_id}'): Result of updater sub-step '{updater_sub_step_id}' is not a dict. Result: {updater_step_full_result}")
            elif updater_sub_step_id and self.debug_mode:
                print(f"DEBUG (while_loop '{step_id}'): Identified updater sub-step '{updater_sub_step_id}' was not found in the current iteration's subflow results: {list(current_iteration_sub_results.keys())}")

            # Re-evaluate condition with potentially updated state
            condition_vars_for_eval = self._prepare_condition_inputs(condition_expr, inputs)
            condition_result = self._evaluate_condition(condition_expr, condition_vars_for_eval)
            print(f"Condition for '{step_id}' after iteration {iteration_num}: \"{condition_expr}\" -> {condition_result} (vars: {condition_vars_for_eval})")

        if self.loop_counters[step_id] >= max_iterations and condition_result and not self.terminated:
            print(f"Warning: Max iterations ({max_iterations}) reached for while_loop '{step_id}' and condition still true.")

        return {"iterations_run": self.loop_counters[step_id], "results_per_iteration": iteration_results_list, "loop_ended_naturally": not condition_result}

    def _execute_for_each(self, for_each_step_def: Dict[str, Any], main_step_lookup: Dict[str, Dict[str, Any]]):
        step_id = for_each_step_def['id']
        inputs = for_each_step_def.get('inputs', {})

        list_input_key_in_yaml = inputs.get('list_variable_name', 'list')
        iterator_name = inputs.get('iterator_name', 'item')
        subflow_spec = inputs.get('subflow', [])

        processed_parent_inputs = self._process_inputs(inputs)

        iterable_list = processed_parent_inputs.get(list_input_key_in_yaml, [])
        if not isinstance(iterable_list, (list, tuple, set)):
            try: iterable_list = list(iterable_list)
            except TypeError:
                print(f"Warning: Input '{list_input_key_in_yaml}' for for_each '{step_id}' is not iterable. Defaulting to empty list.")
                iterable_list = []

        subflow_step_definitions = self._resolve_subflow_definitions(subflow_spec, main_step_lookup, step_id, "for_each")
        all_iterations_results = []

        print(f"--- Executing Control: {step_id} (control.for_each) on {len(iterable_list)} items, iterator: '{iterator_name}' ---")

        for index, item_value in enumerate(iterable_list):
            if self.terminated: break
            print(f"\n--- For Each Loop '{step_id}' Iteration {index + 1}/{len(iterable_list)}, {iterator_name} = {repr(item_value)} ---")

            # Store the iterator in flow variables for easy access in templates
            self.flow_variables[iterator_name] = item_value
            self.flow_variables[f"{iterator_name}_index"] = index

            original_iterator_context = self.step_results.get(iterator_name)
            self.step_results[iterator_name] = {"value": item_value, "index": index}

            current_iteration_sub_results = {iterator_name: item_value, "_index": index}
            for sub_step_def in subflow_step_definitions:
                sub_result = self._execute_step_action(sub_step_def)
                self.step_results[sub_step_def['id']] = sub_result
                current_iteration_sub_results[sub_step_def['id']] = sub_result
                if self.terminated: break

            all_iterations_results.append(current_iteration_sub_results)

            if original_iterator_context is not None:
                self.step_results[iterator_name] = original_iterator_context
            elif iterator_name in self.step_results:
                if isinstance(self.step_results[iterator_name], dict) and \
                   set(self.step_results[iterator_name].keys()) == {"value", "index"}:
                     del self.step_results[iterator_name]

        return {"iterations_completed": len(all_iterations_results), "results_per_iteration": all_iterations_results}

    def _execute_parallel(self, parallel_step_def: Dict[str, Any], main_step_lookup: Dict[str, Dict[str, Any]]):
        step_id = parallel_step_def['id']
        inputs = parallel_step_def.get('inputs', {})

        processed_parent_inputs = self._process_inputs(inputs)
        actual_branch_specs_list = processed_parent_inputs.get('branches', [])

        all_branch_run_results = []
        print(f"--- Executing Control: {step_id} (control.parallel) with {len(actual_branch_specs_list)} branches (simulated sequentially) ---")

        for i, branch_subflow_spec in enumerate(actual_branch_specs_list):
            if self.terminated: break
            print(f"\n--- Parallel Branch {i + 1}/{len(actual_branch_specs_list)} of '{step_id}' ---")

            branch_step_definitions = self._resolve_subflow_definitions(branch_subflow_spec, main_step_lookup, f"{step_id}_branch_{i+1}", "parallel_branch")
            current_branch_sub_results = {}
            for sub_step_def in branch_step_definitions:
                sub_result = self._execute_step_action(sub_step_def)
                self.step_results[sub_step_def['id']] = sub_result
                current_branch_sub_results[sub_step_def['id']] = sub_result
                if self.terminated: break
            all_branch_run_results.append(current_branch_sub_results)

        return {"branches_executed": len(all_branch_run_results), "outputs_per_branch": all_branch_run_results}

    def _execute_try_catch(self, try_catch_step_def: Dict[str, Any], main_step_lookup: Dict[str, Dict[str, Any]]):
        step_id = try_catch_step_def['id']
        inputs = try_catch_step_def.get('inputs', {})

        try_subflow_spec = inputs.get('subflow', inputs.get('try_subflow', []))
        on_error_subflow_spec = inputs.get('on_error', inputs.get('catch_subflow', []))

        try_block_step_definitions = self._resolve_subflow_definitions(try_subflow_spec, main_step_lookup, step_id, "try_block")

        print(f"--- Executing Control: {step_id} (control.try_catch) ---")

        error_occurred_in_try = False
        exception_info = None
        try_block_run_results = {}

        try:
            print(f"\n--- Try Block for '{step_id}' ---")
            for sub_step_def in try_block_step_definitions:
                sub_result = self._execute_step_action(sub_step_def)
                self.step_results[sub_step_def['id']] = sub_result
                try_block_run_results[sub_step_def['id']] = sub_result
                if self.terminated: break
            if self.terminated:
                 return {"success": False, "error_details": {"type": "FlowTerminated", "message": self.termination_message}, "try_block_results": try_block_run_results}

        except Exception as e:
            error_occurred_in_try = True
            exception_info = {"type": type(e).__name__, "message": str(e)}
            print(f"Error caught in try_block of '{step_id}': {type(e).__name__} - {e}")

            if on_error_subflow_spec and not self.terminated:
                print(f"\n--- Catch Block for '{step_id}' ---")
                catch_block_step_definitions = self._resolve_subflow_definitions(on_error_subflow_spec, main_step_lookup, step_id, "catch_block")

                error_context_key = f"__error_{step_id}"
                original_error_context_value = self.step_results.get(error_context_key)
                self.step_results[error_context_key] = {"details": copy.deepcopy(exception_info)}

                # Store error info in flow variables for easy access
                self.flow_variables["__error"] = {"type": type(e).__name__, "message": str(e)}

                for sub_step_def in catch_block_step_definitions:
                    sub_result = self._execute_step_action(sub_step_def)
                    self.step_results[sub_step_def['id']] = sub_result
                    if self.terminated: break

                if original_error_context_value is not None: self.step_results[error_context_key] = original_error_context_value
                elif error_context_key in self.step_results : del self.step_results[error_context_key]
                
                # Clean up flow variables
                if "__error" in self.flow_variables:
                    del self.flow_variables["__error"]
            elif self.terminated:
                print(f"Skipping catch block for '{step_id}' as flow is already terminated.")

        return {"success": not error_occurred_in_try, "error_details": exception_info, "try_block_results": try_block_run_results}

    def _execute_retry(self, retry_step_def: Dict[str, Any], main_step_lookup: Dict[str, Dict[str, Any]]):
        step_id = retry_step_def['id']
        inputs = retry_step_def.get('inputs', {})

        processed_inputs = self._process_inputs(inputs)
        action_to_retry_step_id = processed_inputs.get('action_step')
        max_attempts = int(processed_inputs.get('attempts', 3))
        backoff_seconds = float(processed_inputs.get('backoff_seconds', 0))

        if not action_to_retry_step_id or action_to_retry_step_id not in main_step_lookup:
            raise ValueError(f"Retry step '{step_id}': 'action_step' ID '{action_to_retry_step_id}' not found in main flow.")

        step_to_retry_def_obj = main_step_lookup[action_to_retry_step_id]
        self.retry_counters[step_id] = 0
        last_result_from_action = None
        action_succeeded = False

        print(f"--- Executing Control: {step_id} (control.retry) on step '{action_to_retry_step_id}' (Max attempts: {max_attempts}) ---")

        for attempt_num in range(1, max_attempts + 1):
            if self.terminated: break
            self.retry_counters[step_id] = attempt_num
            print(f"\n--- Retry Attempt {attempt_num}/{max_attempts} for '{action_to_retry_step_id}' (via '{step_id}') ---")
            try:
                last_result_from_action = self._execute_step_action(step_to_retry_def_obj)
                self.step_results[action_to_retry_step_id] = last_result_from_action
                action_succeeded = True
                print(f"Step '{action_to_retry_step_id}' succeeded on attempt {attempt_num}.")
                break
            except Exception as e:
                print(f"Error on attempt {attempt_num} for '{action_to_retry_step_id}': {type(e).__name__} - {e}")
                if attempt_num < max_attempts and not self.terminated:
                    if backoff_seconds > 0:
                        print(f"Waiting {backoff_seconds}s before next attempt...")
                        time.sleep(backoff_seconds)
                elif self.terminated:
                    print(f"Retry '{step_id}' interrupted due to flow termination.")
                else:
                    print(f"Step '{action_to_retry_step_id}' failed after {max_attempts} attempts.")

        return {"action_succeeded": action_succeeded, "attempts_made": self.retry_counters[step_id], "last_action_result": last_result_from_action}

    def _execute_subflow_wrapper(self, subflow_control_step_def: Dict[str, Any]):
        step_id = subflow_control_step_def['id']
        inputs = subflow_control_step_def.get('inputs', {})
        processed_inputs = self._process_inputs(inputs)

        target_flow_identifier = processed_inputs.get('flow_id', processed_inputs.get('flow_ref'))
        if not target_flow_identifier:
            raise ValueError(f"Subflow step '{step_id}' is missing 'flow_id' or 'flow_ref' input.")

        subflow_explicit_inputs = processed_inputs.get('inputs', {})

        print(f"--- Executing Control: {step_id} (control.subflow) for target '{target_flow_identifier}' ---")
        self.executed_step_count_total +=1

        subflow_path_candidate = Path(target_flow_identifier)
        if not subflow_path_candidate.suffix and not subflow_path_candidate.exists():
            subflow_path_candidate = subflow_path_candidate.with_suffix(".yaml")

        if subflow_path_candidate.is_absolute():
            actual_subflow_path = subflow_path_candidate
        else:
            actual_subflow_path = (self.base_flows_path / subflow_path_candidate).resolve()

        if not actual_subflow_path.exists():
            raise FileNotFoundError(f"Subflow definition YAML file not found for '{target_flow_identifier}'. Tried: {actual_subflow_path}")

        # Pass current flow variables to subflow
        combined_inputs = copy.deepcopy(self.flow_variables)
        combined_inputs.update(subflow_explicit_inputs)
        
        sub_engine = FlowEngine(self.registry, self.debug_mode, self.base_flows_path, parent_context=combined_inputs)

        try:
            subflow_result = sub_engine.execute_flow(actual_subflow_path)
            
            # Import updated variables back from subflow
            for var_name, var_value in sub_engine.flow_variables.items():
                if var_name not in combined_inputs or var_value != combined_inputs[var_name]:
                    self.flow_variables[var_name] = var_value
                    if self.debug_mode:
                        print(f"Imported variable '{var_name}' with value {repr(var_value)} from subflow")
            
            if sub_engine.terminated:
                self.terminated = True
                self.termination_message = f"Subflow '{target_flow_identifier}' terminated: {sub_engine.termination_message}"
            return {"subflow_id": target_flow_identifier, "result": subflow_result, "terminated_by_subflow": sub_engine.terminated}
        except Exception as e:
            print(f"ERROR during subflow '{target_flow_identifier}' execution: {type(e).__name__} - {e}")
            raise RuntimeError(f"Subflow '{target_flow_identifier}' failed.") from e

    def _execute_delay(self, delay_step_def: Dict[str, Any]):
        step_id = delay_step_def['id']
        inputs = delay_step_def.get('inputs', {})
        processed_inputs = self._process_inputs(inputs)
        seconds_to_delay = 0.0
        try:
            seconds_to_delay = float(processed_inputs.get('seconds', 0))
        except (ValueError, TypeError):
            print(f"Warning: Invalid 'seconds' value for delay step '{step_id}'. Defaulting to 0.")

        print(f"--- Executing Control: {step_id} (control.delay) for {seconds_to_delay}s ---")
        self.executed_step_count_total +=1
        if seconds_to_delay > 0: time.sleep(seconds_to_delay)
        return {"delayed_for_seconds": seconds_to_delay, "completed": True}

    def _execute_wait_for(self, wait_for_step_def: Dict[str, Any]):
        step_id = wait_for_step_def['id']
        inputs = wait_for_step_def.get('inputs', {})
        processed_inputs = self._process_inputs(inputs)

        until_condition = processed_inputs.get('until', processed_inputs.get('event'))
        timeout_str = processed_inputs.get('timeout')

        self.executed_step_count_total +=1
        print(f"--- Executing Control: {step_id} (control.wait_for) event/condition '{until_condition}' with timeout '{timeout_str}' ---")

        sleep_duration_td: Optional[timedelta] = None
        target_time_utc: Optional[datetime] = None

        if isinstance(until_condition, str):
            sleep_duration_td = parse_duration(until_condition)
            if not sleep_duration_td:
                try:
                    if until_condition.endswith('Z'):
                        target_time_utc = datetime.fromisoformat(until_condition[:-1]).replace(tzinfo=timezone.utc)
                    else:
                         dt_obj = datetime.fromisoformat(until_condition)
                         target_time_utc = dt_obj.astimezone(timezone.utc) if dt_obj.tzinfo else dt_obj.replace(tzinfo=timezone.utc)
                except ValueError:
                    pass

        elif isinstance(until_condition, (int, float)):
             sleep_duration_td = timedelta(seconds=until_condition)

        if target_time_utc:
            now_utc = datetime.now(timezone.utc)
            if target_time_utc > now_utc:
                sleep_seconds = (target_time_utc - now_utc).total_seconds()
                print(f"Waiting until specified timestamp: {until_condition} (approx {sleep_seconds:.2f}s from now).")
                if sleep_seconds > 0: time.sleep(sleep_seconds)
                return {"event_triggered": True, "condition_met": True, "waited_until_time": True, "details": until_condition}
            else:
                print(f"Specified timestamp {until_condition} is in the past. Proceeding immediately.")
                return {"event_triggered": True, "condition_met": True, "waited_until_time": False, "details": "Timestamp in past"}
        elif sleep_duration_td:
            sleep_seconds = sleep_duration_td.total_seconds()
            print(f"Waiting for duration: {until_condition} (approx {sleep_seconds:.2f}s).")
            if sleep_seconds > 0: time.sleep(sleep_seconds)
            return {"event_triggered": True, "condition_met": True, "waited_for_duration": True, "details": until_condition}
        else:
            print(f"Note: Waiting for arbitrary event '{until_condition}' is simulated as immediately satisfied. Timeout: {timeout_str}")
            return {"event_triggered": True, "condition_met": True, "simulated_event": True, "details": until_condition}

    def _execute_terminate(self, terminate_step_def: Dict[str, Any]):
        step_id = terminate_step_def['id']
        inputs = terminate_step_def.get('inputs', {})
        processed_inputs = self._process_inputs(inputs)
        message = processed_inputs.get('message', f"Flow terminated by step '{step_id}'.")

        print(f"--- Executing Control: {step_id} (control.terminate) ---")
        self.executed_step_count_total +=1
        self.terminated = True
        self.termination_message = message
        return {"terminated": True, "message": message}

    def _execute_step_action(self, step_definition: Dict[str, Any]):
        step_id = step_definition['id']
        action = step_definition.get('action', '')
        inputs = step_definition.get('inputs', {})

        self.executed_step_count_total += 1
        print(f"--- Step {self.executed_step_count_total}: {step_id} ({action}) ---")

        processed_inputs = self._process_inputs(inputs)
        
        # Special handling for variable operations
        if action.startswith('variables.'):
            var_action = action.split('.')[1]
            
            if var_action == 'get_local':
                var_name = processed_inputs.get('name')
                default = processed_inputs.get('default')
                value = self.flow_variables.get(var_name, default)
                return {"value": value}
                
            elif var_action == 'set_local':
                var_name = processed_inputs.get('name')
                value = processed_inputs.get('value')
                self.flow_variables[var_name] = value
                return {"value": value}
                
            elif var_action == 'get_env':
                env_name = processed_inputs.get('name')
                default = processed_inputs.get('default', '')
                value = self.environment.get(env_name, default)
                return {"value": value}
            
            elif var_action == 'get':
                # Legacy support for 'get'
                var_name = processed_inputs.get('name')
                default = processed_inputs.get('default')
                # Check flow variables first, then env variables
                if var_name in self.flow_variables:
                    return {"value": self.flow_variables.get(var_name)}
                else:
                    return {"value": self.environment.get(var_name, default)}
                
            elif var_action == 'set':
                # Legacy support for 'set'
                var_name = processed_inputs.get('name')
                value = processed_inputs.get('value')
                self.flow_variables[var_name] = value
                return {"value": value}

        try:
            result = self.registry.execute_action(action, **processed_inputs)

            if isinstance(result, dict):
                if 'answer' in result: print(f"Result for '{step_id}': answer = {repr(result['answer'])}")
                elif 'response' in result and isinstance(result['response'], str) and len(result['response']) > 100:
                    print(f"Result for '{step_id}': response (truncated) = {result['response'][:100]}...")
                elif len(str(result)) < 300 :
                    try: print(f"Result for '{step_id}': {json.dumps(result, indent=2, default=str)}")
                    except TypeError: print(f"Result for '{step_id}': {str(result)}")
                else: print(f"Result for '{step_id}' (keys): {list(result.keys())}")
            else: print(f"Result for '{step_id}': {result}")
            return result

        except Exception as e:
            print(f"ERROR executing step '{step_id}' ({action}): {type(e).__name__} - {str(e)}")
            if self.debug_mode:
                import traceback
                traceback.print_exc()
            raise

    def _prepare_subflow_steps(self, subflow_spec: Union[List[Any], str]) -> List[str]:
        if isinstance(subflow_spec, list):
            if not subflow_spec: return []
            if isinstance(subflow_spec[0], dict):
                return [s['id'] for s in subflow_spec if 'id' in s]
            else:
                return [s for s in subflow_spec if isinstance(s, str)]
        elif isinstance(subflow_spec, str):
            return [subflow_spec]
        return []

    def _prepare_condition_inputs(self, condition_expr: str, parent_step_inputs: Dict[str, Any]) -> Dict[str, Any]:
        control_keywords = {'condition', 'subflow', 'max_iterations', 'then_step', 'else_step', 'cases', 'default',
                            'list_variable_name', 'list', 'iterator_name', 'branches', 'wait_for_all', 'try_subflow',
                            'catch_subflow', 'on_error', 'action_step', 'attempts', 'backoff_seconds',
                            'flow_id', 'flow_ref', 'inputs', 'seconds', 'until', 'event', 'message',
                            'loop_variable_updater_step', 'loop_variable_updater_output'}

        potential_var_keys_from_parent_inputs = {k: v for k, v in parent_step_inputs.items() if k not in control_keywords}
        resolved_condition_vars = self._process_inputs(potential_var_keys_from_parent_inputs)
        return resolved_condition_vars

    def _evaluate_condition(self, condition_expr: str, condition_vars: Dict[str, Any]) -> bool:
        try:
            if not isinstance(condition_expr, str):
                return bool(condition_expr)

            if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", condition_expr) and condition_expr in condition_vars:
                return bool(condition_vars[condition_expr])

            # First check if there are variable references that should be resolved from flow_variables
            for var_name in re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', condition_expr):
                if var_name in self.flow_variables and var_name not in condition_vars:
                    condition_vars[var_name] = self.flow_variables[var_name]

            safe_globals = {"__builtins__": {"True": True, "False": False, "None": None,
                                             "bool": bool, "int": int, "float": float, "str": str,
                                             "len": len, "list": list, "dict": dict, "round": round,
                                             "sum": sum, "min": min, "max": max, "abs": abs}}
            return bool(eval(condition_expr, safe_globals, condition_vars))
        except Exception as e:
            print(f"ERROR evaluating condition \"{condition_expr}\" with vars {condition_vars}: {type(e).__name__} - {e}")
            return False

    def _process_inputs(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        processed = {}
        if not isinstance(inputs, dict): return {}

        for key, value in inputs.items():
            if isinstance(value, str):
                is_direct_reference_resolved = False
                
                # Priority 0: Direct step output reference
                if '.' in value and not value.startswith("'") and not value.startswith('"') and not re.search(r"\{\{.*\}\}|\{.*\}", value):
                    parts = value.split('.', 1)
                    if len(parts) == 2:
                        source_step_id, output_key_name = parts[0], parts[1]
                        
                        # Special handling for env. and var./local. references
                        if source_step_id == 'env':
                            processed[key] = self.environment.get(output_key_name, '')
                            is_direct_reference_resolved = True
                        elif source_step_id in ('var', 'local'):
                            processed[key] = self.flow_variables.get(output_key_name, None)
                            is_direct_reference_resolved = True
                        elif source_step_id in self.step_results:
                            source_step_result_data = self.step_results[source_step_id]
                            if isinstance(source_step_result_data, dict) and output_key_name in source_step_result_data:
                                processed[key] = source_step_result_data[output_key_name]
                                is_direct_reference_resolved = True
                            elif self.debug_mode:
                                print(f"DEBUG: Direct ref '{value}' for '{key}', key '{output_key_name}' not in '{source_step_id}' results: {source_step_result_data}")
                        elif self.debug_mode:
                             print(f"DEBUG: Direct ref '{value}' for '{key}', step '{source_step_id}' not in results. Available: {list(self.step_results.keys())}")

                if is_direct_reference_resolved:
                    continue

                # Priority 1: Template string handling (if not a resolved direct reference)
                processed_value_str = self._process_single_string_template(value, f"input_key:'{key}'")

                # Attempt to convert back if the original template was simple and result is convertible
                if processed_value_str != value:
                    match_simple_template = re.fullmatch(r"\{\{([\s\S]+?)\}\}|\{([\s\S]+?)\}", value)
                    if match_simple_template:
                        # Try to infer type for simple {{var}} substitutions
                        # If var was e.g. item.value, and item.value was a number, processed_value_str is its string form.
                        # We try to convert it back to a number or boolean if it looks like one.
                        try:
                            float_val = float(processed_value_str)
                            processed[key] = int(float_val) if float_val == int(float_val) else float_val
                            continue
                        except ValueError:
                            if processed_value_str.lower() == 'true':
                                processed[key] = True
                                continue
                            elif processed_value_str.lower() == 'false':
                                processed[key] = False
                                continue

                processed[key] = processed_value_str

            elif isinstance(value, (list, dict)):
                processed[key] = self._process_inputs_recursive(value)
            else:
                processed[key] = value
        return processed

    def _process_inputs_recursive(self, item: Any) -> Any:
        if isinstance(item, dict):
            return self._process_inputs(item)
        elif isinstance(item, list):
            return [self._process_inputs_recursive(elem) for elem in item]
        elif isinstance(item, str):
            # Process string element: direct reference or template
            # Check for direct reference first
            if '.' in item and not item.startswith("'") and not item.startswith('"') and not re.search(r"\{\{.*\}\}|\{.*\}", item):
                parts = item.split('.', 1)
                if len(parts) == 2:
                    source_step_id, output_key_name = parts[0], parts[1]
                    
                    # Special handling for env. and var./local. references
                    if source_step_id == 'env':
                        return self.environment.get(output_key_name, '')
                    elif source_step_id in ('var', 'local'):
                        return self.flow_variables.get(output_key_name, None)
                    elif source_step_id in self.step_results:
                        source_step_result_data = self.step_results[source_step_id]
                        if isinstance(source_step_result_data, dict) and output_key_name in source_step_result_data:
                            return source_step_result_data[output_key_name] # Return resolved value directly

            # Then check for template
            processed_str = self._process_single_string_template(item, "recursive_item")
            # Try to convert back simple template results to their likely original type
            if processed_str != item:
                match_simple_template = re.fullmatch(r"\{\{([\s\S]+?)\}\}|\{([\s\S]+?)\}", item)
                if match_simple_template:
                    try:
                        float_val = float(processed_str)
                        return int(float_val) if float_val == int(float_val) else float_val
                    except ValueError:
                        if processed_str.lower() == 'true': return True
                        if processed_str.lower() == 'false': return False
            return processed_str # Return string if not converted

        else:
            return item

    def _process_single_string_template(self, value_str: str, context_key_for_debug: str) -> str:
        """Process template strings with support for variable references."""
        template_pattern = r"\{\{([\s\S]+?)\}\}|\{([\s\S]+?)\}"

        if not re.search(template_pattern, value_str):
            return value_str

        def replace_match(match_obj):
            content_double_braced = match_obj.group(1)
            content_single_braced = match_obj.group(2)
            content_to_resolve = (content_double_braced if content_double_braced is not None else content_single_braced)
            if content_to_resolve is None: return match_obj.group(0)
            content_to_resolve = content_to_resolve.strip()

            # Special variable prefix handlers
            if content_to_resolve.startswith('env.'):
                # Environment variable reference like {{env.HOME}}
                env_var = content_to_resolve[4:]
                return str(self.environment.get(env_var, ''))
            
            elif content_to_resolve.startswith('var.') or content_to_resolve.startswith('local.'):
                # Local variable reference like {{var.counter}} or {{local.counter}}
                local_var = content_to_resolve.split('.', 1)[1]
                return str(self.flow_variables.get(local_var, ''))
            
            # Check flow variables for direct name match
            if content_to_resolve in self.flow_variables:
                return str(self.flow_variables[content_to_resolve])
                
            # Try expressions with flow variables
            if not '.' in content_to_resolve:
                try:
                    # Create a combined dictionary with flow variables and other context
                    expr_context = dict(self.flow_variables)
                    if content_to_resolve in expr_context:
                        return str(expr_context[content_to_resolve])
                    else:
                        # Try evaluating as an expression using flow variables
                        safe_globals = {"__builtins__": {"True": True, "False": False, "None": None,
                                                        "bool": bool, "int": int, "float": float, "str": str,
                                                        "len": len, "list": list, "dict": dict, "round": round,
                                                        "sum": sum, "min": min, "max": max, "abs": abs}}
                        result = eval(content_to_resolve, safe_globals, expr_context)
                        return str(result)
                except:
                    # If eval fails, continue with standard processing
                    pass

            # Then proceed with existing step result resolution
            resolved_val = None
            if '.' in content_to_resolve:
                parts = content_to_resolve.split('.', 1)
                potential_source_var, key_in_source = parts[0], parts[1]
                # Check if potential_source_var is an iterator context we created
                if potential_source_var in self.step_results and \
                   isinstance(self.step_results[potential_source_var], dict) and \
                   key_in_source in self.step_results[potential_source_var] and \
                   ("value" in self.step_results[potential_source_var] or "index" in self.step_results[potential_source_var]): # Iterator heuristic
                    resolved_val = self.step_results[potential_source_var][key_in_source]
                # Else, check if it's a standard step.output
                elif potential_source_var in self.step_results and \
                     isinstance(self.step_results[potential_source_var], dict) and \
                     key_in_source in self.step_results[potential_source_var]:
                    resolved_val = self.step_results[potential_source_var][key_in_source]

            if resolved_val is None and content_to_resolve in self.step_results:
                 resolved_val = self.step_results[content_to_resolve]

            if resolved_val is not None:
                return str(resolved_val) # Always convert to string for re.sub replacement

            original_placeholder = match_obj.group(0)
            if self.debug_mode: print(f"DEBUG: Unresolved template var '{original_placeholder}' in string '{value_str}' for context '{context_key_for_debug}'.")
            return original_placeholder

        return re.sub(template_pattern, replace_match, value_str)

    # Variable management methods
    def get_variable(self, name, default=None):
        """Get a variable value from the flow variable store."""
        return self.flow_variables.get(name, default)

    def set_variable(self, name, value):
        """Set a variable value in the flow variable store."""
        self.flow_variables[name] = value
        return value

    def list_variables(self):
        """List all variables in the flow variable store."""
        return dict(self.flow_variables)
    
    def get_env_variable(self, name, default=""):
        """Get an environment variable."""
        return self.environment.get(name, default)
