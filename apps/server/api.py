"""REST API server for FlowForge."""

import os
import json
import yaml
from typing import Dict, Any, List, Optional
from pathlib import Path
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Import FlowForge components
from flowforge.packages.core.licensing import has_feature
from flowforge.packages.core.engine import FlowEngine
from flowforge.packages.sdk.plugin_loader import load_plugins

# Create FastAPI app
app = FastAPI(
    title="FlowForge API",
    description="API for FlowForge workflow automation",
    version="0.1.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class FlowDefinition(BaseModel):
    id: str
    steps: List[Dict[str, Any]]

class FlowExecutionRequest(BaseModel):
    flow_id: str
    inputs: Optional[Dict[str, Any]] = None

class FlowCreateRequest(BaseModel):
    definition: FlowDefinition
    description: Optional[str] = None

# Settings
FLOWS_DIR = Path(os.environ.get("FLOWFORGE_FLOWS_DIR", "./flows"))

# Initialization
@app.on_event("startup")
async def startup_event():
    """Initialize on startup."""
    # Ensure flows directory exists
    FLOWS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load plugins
    global plugins
    plugins = load_plugins()
    
    print(f"FlowForge API started")
    print(f"Flows directory: {FLOWS_DIR}")
    print(f"Loaded plugins: {list(plugins.keys())}")

# Routes
@app.get("/")
async def read_root():
    """Root endpoint."""
    return {
        "name": "FlowForge API",
        "version": "0.1.0",
        "enterprise_features": {
            "rbac": has_feature("rbac"),
            "team_management": has_feature("team_management"),
            "audit_logging": has_feature("audit_logging")
        }
    }

@app.get("/flows")
async def list_flows():
    """List all flows."""
    flows = []
    for flow_file in FLOWS_DIR.glob("*.yaml"):
        try:
            with open(flow_file) as f:
                flow = yaml.safe_load(f)
                flows.append({
                    "id": flow.get("id", flow_file.stem),
                    "file": flow_file.name,
                    "path": str(flow_file.relative_to(FLOWS_DIR))
                })
        except Exception as e:
            print(f"Error loading flow from {flow_file}: {e}")
    
    return {"flows": flows}

@app.get("/flows/{flow_id}")
async def get_flow(flow_id: str):
    """Get a specific flow by ID."""
    # Try to find flow by ID
    for flow_file in FLOWS_DIR.glob("*.yaml"):
        try:
            with open(flow_file) as f:
                flow = yaml.safe_load(f)
                if flow.get("id") == flow_id:
                    return {
                        "id": flow_id,
                        "file": flow_file.name,
                        "definition": flow
                    }
        except Exception as e:
            print(f"Error loading flow from {flow_file}: {e}")
    
    # Try by filename
    flow_file = FLOWS_DIR / f"{flow_id}.yaml"
    if flow_file.exists():
        try:
            with open(flow_file) as f:
                flow = yaml.safe_load(f)
                return {
                    "id": flow.get("id", flow_id),
                    "file": flow_file.name,
                    "definition": flow
                }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error loading flow: {str(e)}")
    
    raise HTTPException(status_code=404, detail="Flow not found")

@app.post("/flows")
async def create_flow(flow: FlowCreateRequest):
    """Create a new flow."""
    flow_id = flow.definition.id
    
    # Check if flow already exists
    existing_flow = None
    try:
        existing_flow = await get_flow(flow_id)
    except HTTPException:
        pass
    
    if existing_flow:
        raise HTTPException(status_code=409, detail=f"Flow with ID '{flow_id}' already exists")
    
    # Save flow
    flow_file = FLOWS_DIR / f"{flow_id}.yaml"
    try:
        with open(flow_file, "w") as f:
            yaml.dump(flow.definition.dict(), f)
        
        return {
            "id": flow_id,
            "file": flow_file.name,
            "message": "Flow created successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating flow: {str(e)}")

@app.post("/flows/{flow_id}/execute")
async def execute_flow(flow_id: str, request: FlowExecutionRequest, background_tasks: BackgroundTasks):
    """Execute a flow."""
    try:
        # Get flow
        flow_data = await get_flow(flow_id)
        
        # Execute in background
        background_tasks.add_task(
            run_flow_in_background,
            flow_id,
            flow_data["definition"],
            request.inputs
        )
        
        return {
            "id": flow_id,
            "status": "executing",
            "message": "Flow execution started"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error executing flow: {str(e)}")

async def run_flow_in_background(flow_id: str, flow_definition: Dict[str, Any], inputs: Optional[Dict[str, Any]]):
    """Run a flow in the background."""
    try:
        engine = FlowEngine(debug_mode=False, base_flows_path=FLOWS_DIR)
        result = engine.execute_flow(flow_definition, flow_inputs=inputs)
        print(f"Flow '{flow_id}' execution completed")
        # Store result or send notification if needed
    except Exception as e:
        print(f"Error executing flow '{flow_id}': {e}")

# Add more endpoints for RBAC, team management, etc. if licensed
if has_feature("rbac"):
    # Include team/user management endpoints
    pass

# Run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)