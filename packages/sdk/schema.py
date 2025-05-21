# sdk/schema.py

"""Schema validation utilities for FlowForge plugins."""

import json
from typing import Dict, Any
import jsonschema

class SchemaValidationError(Exception):
    """Exception raised when data doesn't match schema."""
    pass

def validate_schema(data: Any, schema: Dict[str, Any]) -> None:
    """Validate data against a JSON schema."""
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.exceptions.ValidationError as e:
        raise SchemaValidationError(str(e))

def generate_schema_from_action(action_def: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a JSON schema from an action definition."""
    schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {},
        "required": []
    }
    
    # Process inputs
    inputs = action_def.get("inputs", {})
    for input_name, input_def in inputs.items():
        if isinstance(input_def, dict) and input_def.get("required", False):
            schema["required"].append(input_name)
            
        schema["properties"][input_name] = {
            "type": map_type_to_schema(input_def.get("type", "string")),
            "description": input_def.get("description", "")
        }
    
    return schema

def map_type_to_schema(type_str: str) -> Union[str, List[str]]:
    """Map a type string to JSON schema type or list of types."""
    type_str = type_str.lower()
    if type_str == "any":
        return ["string", "number", "object", "array", "boolean", "null"]
    type_map = {
        "string": "string",
        "number": "number",
        "integer": "integer",
        "boolean": "boolean",
        "array": "array",
        "object": "object"
    }
    return type_map.get(type_str, "string")
