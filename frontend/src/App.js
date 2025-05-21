import React, { useState } from 'react';
import ChatUI from './components/ChatUI';
import FlowVisualizer from './components/FlowVisualizer';

const App = () => {
  const [generatedFlow, setGeneratedFlow] = useState(null);
  const [flowYaml, setFlowYaml] = useState('');
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // Handle flow generation from ChatUI
  const handleFlowGenerated = (yaml) => {
    setFlowYaml(yaml);
    setGeneratedFlow(parseYamlToFlow(yaml));
  };

  // Toggle sidebar collapsed state
  const toggleSidebar = () => {
    setSidebarCollapsed(!sidebarCollapsed);
  };

  // Parse YAML flow into visualization structure
  const parseYamlToFlow = (yaml) => {
    try {
      // Simple parsing for demonstration (in a real app, use a proper YAML parser)
      const lines = yaml.split('\n');
      let flowId = '';
      let steps = [];
      
      // Extract flow ID
      for (const line of lines) {
        if (line.startsWith('id:')) {
          flowId = line.replace('id:', '').trim();
          break;
        }
      }
      
      // Extract steps
      let inSteps = false;
      let currentStep = {};
      
      for (const line of lines) {
        const trimmedLine = line.trim();
        
        if (trimmedLine === 'steps:') {
          inSteps = true;
          continue;
        }
        
        if (inSteps) {
          if (trimmedLine.startsWith('- id:')) {
            if (Object.keys(currentStep).length > 0) {
              steps.push(currentStep);
            }
            currentStep = {
              id: trimmedLine.replace('- id:', '').trim(),
              inputs: {}
            };
          } else if (trimmedLine.startsWith('action:') && Object.keys(currentStep).length > 0) {
            currentStep.action = trimmedLine.replace('action:', '').trim();
          } else if (trimmedLine.startsWith('inputs:')) {
            // Inputs section starts
          } else if (trimmedLine.match(/^\s+\w+:/)) {
            // Input parameter
            const parts = trimmedLine.trim().split(':');
            if (parts.length >= 2) {
              const key = parts[0].trim();
              const value = parts.slice(1).join(':').trim();
              currentStep.inputs[key] = value.replace(/"/g, '').replace(/'/g, '');
            }
          }
        }
      }
      
      // Add last step
      if (Object.keys(currentStep).length > 0) {
        steps.push(currentStep);
      }
      
      // Build connections based on step references
      const connections = [];
      
      steps.forEach((step, index) => {
        // For control nodes, look for specific next step references
        if (step.action && step.action.startsWith('control.')) {
          if (step.action === 'control.if_node' || step.action === 'control.if') {
            if (step.inputs.then_step) {
              connections.push({
                id: `${step.id}-then-${step.inputs.then_step}`,
                source: step.id,
                target: step.inputs.then_step,
                label: 'then'
              });
            }
            if (step.inputs.else_step) {
              connections.push({
                id: `${step.id}-else-${step.inputs.else_step}`,
                source: step.id,
                target: step.inputs.else_step,
                label: 'else'
              });
            }
          } else if (step.action === 'control.switch') {
            // Handle cases
            Object.entries(step.inputs).forEach(([key, value]) => {
              if (key === 'cases' && typeof value === 'object') {
                Object.entries(value).forEach(([caseVal, targetStep]) => {
                  connections.push({
                    id: `${step.id}-case-${caseVal}-${targetStep}`,
                    source: step.id,
                    target: targetStep,
                    label: `case: ${caseVal}`
                  });
                });
              } else if (key === 'default' && value) {
                connections.push({
                  id: `${step.id}-default-${value}`,
                  source: step.id,
                  target: value,
                  label: 'default'
                });
              }
            });
          }
        } 
        // Also add sequential flow for non-control structures
        else if (index < steps.length - 1) {
          connections.push({
            id: `${step.id}-to-${steps[index + 1].id}`,
            source: step.id,
            target: steps[index + 1].id
          });
        }
        
        // Look for input references to other steps
        Object.entries(step.inputs || {}).forEach(([key, value]) => {
          if (typeof value === 'string' && value.includes('.')) {
            const [refStepId, refOutput] = value.split('.');
            // Check if refStepId exists in steps
            if (steps.some(s => s.id === refStepId)) {
              connections.push({
                id: `${refStepId}-data-${step.id}`,
                source: refStepId,
                target: step.id,
                label: `data: ${refOutput}`,
                style: { stroke: '#888', strokeDasharray: '5,5' },
                type: 'smoothstep'
              });
            }
          }
        });
      });
      
      return {
        id: flowId,
        steps,
        connections
      };
    } catch (error) {
      console.error('Error parsing YAML:', error);
      return null;
    }
  };

  // Styles
  const styles = {
    container: {
      display: 'flex',
      height: '100vh',
      overflow: 'hidden'
    },
    sidebar: {
      width: sidebarCollapsed ? '48px' : '380px',
      minWidth: sidebarCollapsed ? '48px' : '380px',
      height: '100%',
      borderRight: '1px solid #e5e7eb',
      transition: 'width 0.3s ease, min-width 0.3s ease',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column'
    },
    mainContent: {
      flex: 1,
      height: '100%',
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column'
    },
    toggleButton: {
      position: 'absolute',
      top: '50%',
      left: sidebarCollapsed ? '48px' : '380px',
      transform: 'translateY(-50%)',
      width: '24px',
      height: '48px',
      backgroundColor: '#f9fafb',
      border: '1px solid #e5e7eb',
      borderLeft: 'none',
      borderRadius: '0 4px 4px 0',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      cursor: 'pointer',
      zIndex: 10,
      transition: 'left 0.3s ease'
    },
    toggleIcon: {
      width: '12px',
      height: '12px',
      borderTop: '2px solid #6b7280',
      borderRight: '2px solid #6b7280',
      transform: sidebarCollapsed ? 'rotate(45deg)' : 'rotate(-135deg)'
    },
    noFlowMessage: {
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100%',
      color: '#6b7280',
      textAlign: 'center',
      padding: '0 2rem'
    },
    messageTitle: {
      fontSize: '1.5rem',
      fontWeight: 'bold',
      marginBottom: '1rem'
    },
    messageText: {
      fontSize: '1rem',
      maxWidth: '600px',
      lineHeight: '1.5'
    }
  };

  return (
    <div style={styles.container}>
      {/* Sidebar with ChatUI */}
      <div style={styles.sidebar}>
        <ChatUI 
          onFlowGenerated={handleFlowGenerated} 
          isCollapsed={sidebarCollapsed} 
        />
      </div>
      
      {/* Toggle button for sidebar */}
      <div style={styles.toggleButton} onClick={toggleSidebar}>
        <div style={styles.toggleIcon}></div>
      </div>
      
      {/* Main content with FlowVisualizer */}
      <div style={styles.mainContent}>
        {generatedFlow ? (
          <FlowVisualizer flow={generatedFlow} yaml={flowYaml} />
        ) : (
          <div style={styles.noFlowMessage}>
            <div style={styles.messageTitle}>No Flow Visualization</div>
            <p style={styles.messageText}>
              Use the chat panel to generate a flow, then it will be displayed here
              for visualization and editing. You can drag nodes to reposition them and
              zoom in/out to better see the flow structure.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default App;