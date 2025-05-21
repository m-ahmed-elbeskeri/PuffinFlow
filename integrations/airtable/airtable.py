"""Integration with Airtable for creating, reading, updating and deleting records."""

import os
import requests
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Union

# Airtable API base URL
AIRTABLE_API_URL = "https://api.airtable.com/v0"

def _get_headers():
    """Get Airtable API headers with authentication."""
    api_key = os.environ.get("AIRTABLE_API_KEY", "")
    if not api_key:
        raise ValueError("AIRTABLE_API_KEY environment variable is not set")
    
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

def _build_url(base_id: str, table_name: str, record_id: Optional[str] = None) -> str:
    """Build an Airtable API URL."""
    table_name = table_name.replace(" ", "%20")
    url = f"{AIRTABLE_API_URL}/{base_id}/{table_name}"
    
    if record_id:
        url += f"/{record_id}"
    
    return url

def list_records(base_id: str, table_name: str, view: Optional[str] = None,
                 max_records: int = 100, formula: Optional[str] = None,
                 fields: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Get records from an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        view: The view to use
        max_records: Maximum number of records to return
        formula: Formula to filter records
        fields: Array of field names to return
        
    Returns:
        Dictionary with array of records from the table
    """
    url = _build_url(base_id, table_name)
    headers = _get_headers()
    params = {}
    
    if view:
        params["view"] = view
    
    if max_records:
        params["maxRecords"] = max_records
    
    if formula:
        params["filterByFormula"] = formula
    
    if fields:
        params["fields"] = fields
    
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        # Process records to make them more usable
        processed_records = []
        for record in data.get("records", []):
            processed_record = {
                "id": record.get("id", ""),
                **record.get("fields", {})
            }
            processed_records.append(processed_record)
        
        return {"records": processed_records}
    
    except requests.exceptions.RequestException as e:
        error_message = f"Airtable API error: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_message = f"Airtable API error: {error_data.get('error', {}).get('message', str(e))}"
            except:
                pass
        
        return {"error": error_message, "records": []}

def get_record(base_id: str, table_name: str, record_id: str) -> Dict[str, Any]:
    """
    Get a specific record from an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        record_id: The ID of the record to retrieve
        
    Returns:
        Dictionary with the retrieved record
    """
    url = _build_url(base_id, table_name, record_id)
    headers = _get_headers()
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        record = response.json()
        
        # Process record to make it more usable
        processed_record = {
            "id": record.get("id", ""),
            **record.get("fields", {})
        }
        
        return {"record": processed_record}
    
    except requests.exceptions.RequestException as e:
        error_message = f"Airtable API error: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_message = f"Airtable API error: {error_data.get('error', {}).get('message', str(e))}"
            except:
                pass
        
        return {"error": error_message, "record": {}}

def create_record(base_id: str, table_name: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a new record in an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        fields: Field values for the new record
        
    Returns:
        Dictionary with the created record
    """
    url = _build_url(base_id, table_name)
    headers = _get_headers()
    
    payload = {
        "fields": fields
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        record = response.json()
        
        # Process record to make it more usable
        processed_record = {
            "id": record.get("id", ""),
            **record.get("fields", {})
        }
        
        return {"record": processed_record}
    
    except requests.exceptions.RequestException as e:
        error_message = f"Airtable API error: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_message = f"Airtable API error: {error_data.get('error', {}).get('message', str(e))}"
            except:
                pass
        
        return {"error": error_message, "record": {}}

def update_record(base_id: str, table_name: str, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update an existing record in an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        record_id: The ID of the record to update
        fields: New field values for the record
        
    Returns:
        Dictionary with the updated record
    """
    url = _build_url(base_id, table_name, record_id)
    headers = _get_headers()
    
    payload = {
        "fields": fields
    }
    
    try:
        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()
        record = response.json()
        
        # Process record to make it more usable
        processed_record = {
            "id": record.get("id", ""),
            **record.get("fields", {})
        }
        
        return {"record": processed_record}
    
    except requests.exceptions.RequestException as e:
        error_message = f"Airtable API error: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_message = f"Airtable API error: {error_data.get('error', {}).get('message', str(e))}"
            except:
                pass
        
        return {"error": error_message, "record": {}}

def delete_record(base_id: str, table_name: str, record_id: str) -> Dict[str, Any]:
    """
    Delete a record from an Airtable table.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        record_id: The ID of the record to delete
        
    Returns:
        Dictionary with status of the deletion
    """
    url = _build_url(base_id, table_name, record_id)
    headers = _get_headers()
    
    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        return {
            "success": True,
            "deleted_id": data.get("id", record_id)
        }
    
    except requests.exceptions.RequestException as e:
        error_message = f"Airtable API error: {str(e)}"
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                error_message = f"Airtable API error: {error_data.get('error', {}).get('message', str(e))}"
            except:
                pass
        
        return {"error": error_message, "success": False}

def create_or_update_record(base_id: str, table_name: str, match_field: str, 
                            match_value: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create a record or update it if it exists based on a field value match.
    
    Args:
        base_id: The ID of the Airtable base
        table_name: The name of the table
        match_field: The field to match on
        match_value: The value to match
        fields: Field values for the record
        
    Returns:
        Dictionary with the created or updated record and operation performed
    """
    # Include the match field in the fields dictionary to ensure it's included
    fields_with_match = {**fields, match_field: match_value}
    
    # Check if a record with this match_field value exists
    formula = f"{{{match_field}}} = '{match_value}'"
    existing_records = list_records(
        base_id=base_id, 
        table_name=table_name, 
        formula=formula,
        max_records=1
    )
    
    if existing_records.get("error"):
        return {
            "error": existing_records["error"],
            "record": {},
            "operation": "failed"
        }
    
    if existing_records.get("records") and len(existing_records["records"]) > 0:
        # Update existing record
        record_id = existing_records["records"][0]["id"]
        result = update_record(
            base_id=base_id,
            table_name=table_name,
            record_id=record_id,
            fields=fields_with_match
        )
        
        if result.get("error"):
            return {
                "error": result["error"],
                "record": result.get("record", {}),
                "operation": "failed"
            }
        
        return {
            "record": result["record"],
            "operation": "updated"
        }
    else:
        # Create new record
        result = create_record(
            base_id=base_id,
            table_name=table_name,
            fields=fields_with_match
        )
        
        if result.get("error"):
            return {
                "error": result["error"],
                "record": result.get("record", {}),
                "operation": "failed"
            }
        
        return {
            "record": result["record"],
            "operation": "created"
        }