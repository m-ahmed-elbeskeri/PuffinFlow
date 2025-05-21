"""Flow execution worker for FlowForge."""

import os
import sys
import json
import yaml
import time
from pathlib import Path
from typing import Dict, Any, Optional
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("flowforge_worker")

# Import FlowForge components
from flowforge.packages.core.engine import FlowEngine
from flowforge.packages.sdk.plugin_loader import load_plugins

class FlowWorker:
    """Worker for executing FlowForge flows."""
    
    def __init__(self, flows_dir: Optional[str] = None):
        """
        Initialize the flow worker.
        
        Args:
            flows_dir: Directory containing flow definitions
        """
        self.flows_dir = Path(flows_dir or os.environ.get("FLOWFORGE_FLOWS_DIR", "./flows"))
        self.flows_dir.mkdir(exist_ok=True, parents=True)
        
        # Load plugins
        self.plugins = load_plugins()
        logger.info(f"Loaded plugins: {list(self.plugins.keys())}")
        
        # Initialize flow engine
        self.engine = FlowEngine(debug_mode=False, base_flows_path=self.flows_dir)
        
        # Queue for flow execution
        self.queue = []
        self.running = False
    
    def add_to_queue(self, flow_id: str, inputs: Optional[Dict[str, Any]] = None):
        """
        Add a flow to the execution queue.
        
        Args:
            flow_id: ID of the flow to execute
            inputs: Optional inputs for the flow
        """
        logger.info(f"Adding flow '{flow_id}' to queue")
        self.queue.append({
            "id": flow_id,
            "inputs": inputs or {},
            "added_at": time.time()
        })
    
    def execute_flow(self, flow_id: str, inputs: Optional[Dict[str, Any]] = None):
        """
        Execute a flow.
        
        Args:
            flow_id: ID of the flow to execute
            inputs: Optional inputs for the flow
            
        Returns:
            Execution result
        """
        try:
            # Find flow file
            flow_file = None
            for file in self.flows_dir.glob("*.yaml"):
                with open(file) as f:
                    flow_data = yaml.safe_load(f)
                    if flow_data.get("id") == flow_id:
                        flow_file = file
                        break
            
            if not flow_file:
                flow_file = self.flows_dir / f"{flow_id}.yaml"
                if not flow_file.exists():
                    raise ValueError(f"Flow '{flow_id}' not found")
            
            # Execute flow
            logger.info(f"Executing flow '{flow_id}'")
            start_time = time.time()
            result = self.engine.execute_flow(flow_file, flow_inputs=inputs)
            execution_time = time.time() - start_time
            
            logger.info(f"Flow '{flow_id}' executed in {execution_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"Error executing flow '{flow_id}': {e}", exc_info=True)
            return {"error": str(e)}
    
    def process_queue(self):
        """Process the flow execution queue."""
        if not self.queue:
            return
        
        # Get next flow from queue
        next_flow = self.queue.pop(0)
        flow_id = next_flow["id"]
        inputs = next_flow["inputs"]
        
        try:
            # Execute flow
            self.execute_flow(flow_id, inputs)
        except Exception as e:
            logger.error(f"Error processing queue item for flow '{flow_id}': {e}", exc_info=True)
    
    def run(self):
        """Run the worker loop."""
        logger.info("Starting FlowForge worker")
        self.running = True
        
        try:
            while self.running:
                # Process queue
                if self.queue:
                    self.process_queue()
                else:
                    # Sleep if queue is empty
                    time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Worker stopped by user")
            self.running = False
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            self.running = False

# Run worker if executed directly
if __name__ == "__main__":
    flows_dir = os.environ.get("FLOWFORGE_FLOWS_DIR")
    worker = FlowWorker(flows_dir)
    worker.run()