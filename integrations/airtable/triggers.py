"""Airtable triggers for detecting new and updated records."""

import os
import time
import json
from datetime import datetime, timezone
import hashlib
from typing import Dict, List, Any, Optional

# Import functions from the main airtable module
from . import airtable

# State storage for triggers
TRIGGER_STATE_DIR = os.path.expanduser("~/.flowforge/triggers/airtable")

def _ensure_state_dir():
    """Ensure the state directory exists."""
    os.makedirs(TRIGGER_STATE_DIR, exist_ok=True)

def _get_state_file_path(base_id: str, table_name: str, trigger_type: str) -> str:
    """Get the path to the state file for a specific trigger."""
    # Create a hash of the base_id and table_name to use as the filename
    hash_key = hashlib.md5(f"{base_id}_{table_name}_{trigger_type}".encode()).hexdigest()
    return os.path.join(TRIGGER_STATE_DIR, f"{hash_key}.json")

def _get_state(base_id: str, table_name: str, trigger_type: str) -> Dict[str, Any]:
    """Get the state for a specific trigger."""
    _ensure_state_dir()
    state_file = _get_state_file_path(base_id, table_name, trigger_type)
    
    try:
        if os.path.exists(state_file):
            with open(state_file, 'r') as f:
                return json.load(f)
    except Exception as e:
        print(f"Error reading state file: {e}")
    
    # Default state
    return {
        "last_run": None,
        "record_ids": [],
        "record_hashes": {}
    }

def _save_state(base_id: str, table_name: str, trigger_type: str, state: Dict[str, Any]) -> None:
    """Save the state for a specific trigger."""
    _ensure_state_dir()
    state_file = _get_state_file_path(base_id, table_name, trigger_type)
    
    # Update the last run time
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    
    try:
        with open(state_file, 'w') as f:
            json.dump(state, f)
    except Exception as e:
        print(f"Error writing state file: {e}")

def _get_record_hash(record: Dict[str, Any]) -> str:
    """Create a hash of a record to detect changes."""
    # Convert record to a stable string representation and hash it
    record_str = json.dumps(record, sort_keys=True)
    return hashlib.md5(record_str.encode()).hexdigest()

def new_record(base_id: str, table_name: str, polling_interval: int = 300) -> Dict[str, Any]:
    """
    Trigger when a new record is created in an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        polling_interval: Polling interval in seconds
        
    Returns:
        Dictionary containing the new record if one is found
    """
    # Get the current state
    state = _get_state(base_id, table_name, "new_record")
    
    # Get the current records
    result = airtable.list_records(base_id=base_id, table_name=table_name)
    
    if result.get("error"):
        return {
            "error": result["error"],
            "record": {}
        }
    
    # Get the current record IDs
    current_records = result["records"]
    current_record_ids = [record["id"] for record in current_records]
    
    # Find new records
    known_record_ids = state.get("record_ids", [])
    new_record_ids = [record_id for record_id in current_record_ids if record_id not in known_record_ids]
    
    # Update the state
    state["record_ids"] = current_record_ids
    _save_state(base_id, table_name, "new_record", state)
    
    # Return the first new record if any
    if new_record_ids:
        new_record = next((record for record in current_records if record["id"] == new_record_ids[0]), None)
        if new_record:
            return {"record": new_record}
    
    # If no new records, wait and try again
    time.sleep(polling_interval)
    return {"record": {}}

def updated_record(base_id: str, table_name: str, polling_interval: int = 300) -> Dict[str, Any]:
    """
    Trigger when a record is updated in an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        polling_interval: Polling interval in seconds
        
    Returns:
        Dictionary containing the updated record if one is found
    """
    # Get the current state
    state = _get_state(base_id, table_name, "updated_record")
    record_hashes = state.get("record_hashes", {})
    
    # Get the current records
    result = airtable.list_records(base_id=base_id, table_name=table_name)
    
    if result.get("error"):
        return {
            "error": result["error"],
            "record": {}
        }
    
    # Check for updated records
    current_records = result["records"]
    updated_record = None
    
    for record in current_records:
        record_id = record["id"]
        record_hash = _get_record_hash(record)
        
        # If we've seen this record before and the hash is different, it's been updated
        if record_id in record_hashes and record_hashes[record_id] != record_hash:
            updated_record = record
            break
        
        # Update the hash
        record_hashes[record_id] = record_hash
    
    # Update the state
    state["record_hashes"] = record_hashes
    _save_state(base_id, table_name, "updated_record", state)
    
    # Return the updated record if found
    if updated_record:
        return {"record": updated_record}
    
    # If no updated records, wait and try again
    time.sleep(polling_interval)
    return {"record": {}}