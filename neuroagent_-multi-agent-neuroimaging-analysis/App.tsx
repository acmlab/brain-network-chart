import React, { useState, useEffect } from 'react';
import { 
  AgentType, ChatMessage, Dataset, ToolVisualization, VisualizationType, McpTool 
} from './types';
import { MOCK_CSV_DATA } from './constants';
import { parseCSV } from './utils/stats';
import { 
  generateNeuroPlan,
  generateGeneralPlan,
  classifyQuery,
  generateResearchInsights, 
  generateLiterature, 
  generatePreprocessingMapping,
  validatePlan,
  checkOllamaConnection, 
  getAvailableModels, 
  setGeneralModel, 
  setNeuroModel,
  getGeneralModel,
  getNeuroModel,
} from './services/ollamaService';
import { mcpClient } from './services/mcpService';
import { INTERNAL_TOOLS, executeInternalTool } from './services/internalTools';
import ChatArea from './components/Chat/ChatArea';
import VisualizerArea from './components/Visualizer/VisualizerArea';
import { useWorkflow } from './hooks/useWorkflow';

const App: React.FC = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [dataset, setDataset] = useState<Dataset | null>(null);
  const [visualizations, setVisualizations] = useState<ToolVisualization[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [mcpTools, setMcpTools] = useState<McpTool[]>([]);
  const [mcpConnected, setMcpConnected] = useState(false);
  const [ollamaConnected, setOllamaConnected] = useState(false);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [highlightedMessageId, setHighlightedMessageId] = useState<string | null>(null);

  const [selectedGeneralModel, setSelectedGeneralModel] = useState<string>('llama3');
  const [selectedNeuroModel, setSelectedNeuroModel] = useState<string>('llama3');

  const { workflowState, wf } = useWorkflow();

  useEffect(() => {
    const initSystem = async () => {
      const isOllamaUp = await checkOllamaConnection();
      setOllamaConnected(isOllamaUp);
      if (isOllamaUp) {
        addMessage(AgentType.SYSTEM, "AI Service: Connected to Ollama (Local).");
        const models = await getAvailableModels();
        setAvailableModels(models);
        
        if (models.length > 0) {
          const preferred = models.find(m => m.includes('llama3')) || models[0];
          setSelectedGeneralModel(preferred);
          setSelectedNeuroModel(preferred);
          setGeneralModel(preferred);
          setNeuroModel(preferred);
        }
      } else {
        addMessage(AgentType.SYSTEM, "CRITICAL WARNING: Could not connect to Ollama (http://127.0.0.1:11434). Ensure it is running with OLLAMA_ORIGINS=\"*\".");
      }

      try {
        await mcpClient.connect();
        const tools = await mcpClient.listTools();
        setMcpTools(tools);
        setMcpConnected(true);
        addMessage(AgentType.SYSTEM, `MCP Server: Connected. Found ${tools.length} tools: ${tools.map(t => t.name).join(', ')}.`);
      } catch (err) {
        console.error("Failed to connect to MCP:", err);
        addMessage(AgentType.SYSTEM, "Warning: Could not connect to MCP Server (localhost:8010). Using internal tools.");
      }
    };

    initSystem();
    return () => { mcpClient.disconnect(); };
  }, []);

  useEffect(() => {
    if (messages.length === 0) {
      addMessage(AgentType.SYSTEM, "Welcome to the NeuroAgent Multi-Agent System. Please upload a neuroimaging dataset (CSV) or load the demo data.");
    }
  }, []);

  const addMessage = (role: AgentType, content: string, metadata?: any): ChatMessage => {
    let usedModel: string | undefined;

    if (role === AgentType.ORCHESTRATOR || role === AgentType.GENERAL_PLANNER) {
      usedModel = selectedGeneralModel;
    } else if (role === AgentType.NEURO_PLANNER || role === AgentType.PLAN_VALIDATOR || role === AgentType.PREPROCESSOR || role === AgentType.RESEARCHER) {
      usedModel = selectedNeuroModel;
    }

    const msg: ChatMessage = {
      id: Date.now().toString() + Math.random(),
      role,
      content,
      timestamp: Date.now(),
      metadata: { ...metadata, model: usedModel }
    };
    setMessages(prev => [...prev, msg]);
    return msg;
  };

  const addVisualization = (viz: ToolVisualization) => {
    setVisualizations(prev => [viz, ...prev]);
  };

  const handleFileUpload = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      loadData(text, file.name);
    };
    reader.readAsText(file);
  };

  const handleLoadDemo = () => {
    loadData(MOCK_CSV_DATA, "Amyloid_SUVR_Swapped.csv");
  };

  const handleGeneralModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModel = e.target.value;
    setSelectedGeneralModel(newModel);
    setGeneralModel(newModel);
    addMessage(AgentType.SYSTEM, `General Model switched to: ${newModel}`);
  };

  const handleNeuroModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const newModel = e.target.value;
    setSelectedNeuroModel(newModel);
    setNeuroModel(newModel);
    addMessage(AgentType.SYSTEM, `Neuro Model switched to: ${newModel}`);
  };

  const loadData = (csvText: string, name: string) => {
    const { columns, data } = parseCSV(csvText);
    setDataset({ name, columns, data });
    addMessage(AgentType.SYSTEM, `Dataset "${name}" loaded with ${data.length} rows and columns: ${columns.join(', ')}.`);
    setVisualizations([{
      type: VisualizationType.DATA_TABLE,
      title: 'Data Inspection',
      data: data
    }]);
  };

  const parseMcpResultToVisualization = (toolName: string, content: string): ToolVisualization | null => {
    try {
      const json = JSON.parse(content);
      if (json.r !== undefined && json.p !== undefined && Array.isArray(json.dataPoints)) {
        return { type: VisualizationType.SCATTER_PLOT, title: `Result: ${toolName}`, data: json };
      }
      if (json.stats && Array.isArray(json.stats) && json.pVal !== undefined) {
        return { type: VisualizationType.BOX_PLOT, title: `Result: ${toolName}`, data: json };
      }
      if (Array.isArray(json) && json.length > 0 && typeof json[0] === 'object') {
        return { type: VisualizationType.DATA_TABLE, title: `Output: ${toolName}`, data: json };
      }
    } catch (e) { }
    return null;
  };

  const executePlanSteps = async (
    plan: any, 
    startStepIndex: number = 0, 
    initialParamsOverride: any = null,
    currentData: any[],
    currentColumns: string[],
    intent: 'RESEARCH' | 'GENERAL'
  ) => {
    const resultsSummary: string[] = [];
    const stepIdToMessageId: Record<number, string> = {};
    const stepsToRun = plan.analysis_steps.slice(startStepIndex);
    const totalSteps = stepsToRun.length;

    for (let i = 0; i < stepsToRun.length; i++) {
      const step = stepsToRun[i];
      const params = (i === 0 && initialParamsOverride) ? initialParamsOverride : step.parameters;

      // Update execution sub-progress
      wf.setExecutionProgress(i, totalSteps);

      const executorMsg = addMessage(
        AgentType.EXECUTOR, 
        `Executing Step ${step.step_id}: ${step.tool}...`,
        { 
          plan, 
          stepIndex: startStepIndex + i, 
          tool: step.tool,
          params: params
        }
      );
      
      stepIdToMessageId[step.step_id] = executorMsg.id;
      let stepResult = "";
      let viz: ToolVisualization | null = null;
      const internalToolDef = INTERNAL_TOOLS.find(t => t.name === step.tool);
      const mcpToolDef = mcpTools.find(t => t.name === step.tool);

      try {
        if (internalToolDef) {
            if (step.tool === 'TRANSFORM_DATA') {
                const col = params.column;
                if (currentColumns.includes(col)) {
                    const preMsg = addMessage(AgentType.PREPROCESSOR, `Analyzing column '${col}' to determine numeric mapping...`);
                    
                    const uniqueVals = Array.from(new Set(currentData.map(row => row[col])));
                    const mappingResult = await generatePreprocessingMapping(col, uniqueVals as string[]);
                    const mapping = mappingResult.mapping;
                    const rationale = mappingResult.rationale;

                    setMessages(prev => prev.map(m => 
                      m.id === preMsg.id 
                        ? { ...m, content: `**Analysis of '${col}':** ${rationale || 'Mapping generated.'}\n\nMapping: ${JSON.stringify(mapping)}` } 
                        : m
                    ));

                    const result = executeInternalTool(step.tool, { ...params, mapping }, currentData);
                    const transformResult = result as any;
                    
                    currentData = transformResult.transformedData;
                    const newColName = transformResult.newColumn;
                    
                    if (!currentColumns.includes(newColName)) currentColumns.push(newColName);
                    
                    setDataset(prev => prev ? ({ ...prev, data: currentData, columns: currentColumns }) : null);

                    stepResult = `Converted '${col}' to '${newColName}' using mapping: ${JSON.stringify(mapping)}.`;
                    viz = {
                         type: VisualizationType.DATA_TABLE,
                         title: `Preprocessing: ${col} -> ${newColName}`,
                         data: Object.entries(mapping).map(([k,v]) => ({ Original: k, Numeric: v }))
                    };
                } else {
                    stepResult = `Error: Column '${col}' not found.`;
                }
            }
            else if (step.tool === 'MODIFY_VISUALIZATION') {
                const result = executeInternalTool(step.tool, params, currentData);
                setVisualizations(prev => {
                    if (prev.length === 0) return prev;
                    const targetIndex = prev.findIndex(v => v.messageId === highlightedMessageId);
                    const indexToUpdate = targetIndex !== -1 ? targetIndex : 0;
                    const updated = [...prev];
                    const targetViz = { ...updated[indexToUpdate] };
                    targetViz.config = { ...targetViz.config, ...result };
                    if (result.title) targetViz.title = result.title;
                    updated[indexToUpdate] = targetViz;
                    return updated;
                });
                stepResult = `Updated visualization style: ${JSON.stringify(result)}`;
            }
            else if (step.tool === 'DATA_INSPECT') {
                const result = executeInternalTool(step.tool, params, currentData) as any;
                viz = { type: VisualizationType.DATA_TABLE, title: 'Data Inspection', data: result.data };
                stepResult = `Inspected data. Loaded ${result.data.length} rows.`;
            }
            else {
                const result = executeInternalTool(step.tool, params, currentData);
                
                if (step.tool === 'CORRELATION_ANALYSIS') {
                    const corrResult = result as any;
                    const vizData = {
                      ...corrResult,
                      xCol: params.x_column || params.x || 'X',
                      yCol: params.y_column || params.y || 'Y'
                    };
                    viz = { type: VisualizationType.SCATTER_PLOT, title: `Correlation: ${corrResult.r.toFixed(2)}`, data: vizData };
                    stepResult = `Correlation Analysis complete. R=${corrResult.r.toFixed(3)}, p-value=${corrResult.p.toExponential(3)}.`;
                } else if (step.tool === 'GROUP_COMPARISON') {
                     const groupResult = result as any;
                     viz = { type: VisualizationType.BOX_PLOT, title: `Group Comparison`, data: groupResult };
                     stepResult = `Group Comparison complete. ANOVA p-value=${groupResult.pVal.toExponential(3)}.`;
                }
            }
        }
        else if (mcpToolDef) {
           const args = { ...params };
           if (mcpToolDef.inputSchema.properties && 'data' in mcpToolDef.inputSchema.properties) {
              args.data = currentData;
           }
           const result = await mcpClient.callTool(step.tool, args);
           const textContent = result.content.filter(c => c.type === 'text').map(c => c.text).join('\n');
           stepResult = textContent || "Tool executed successfully.";
           viz = parseMcpResultToVisualization(step.tool, textContent);
           if (result.isError) stepResult = `Error executing tool: ${stepResult}`;
        } 
        else if (step.tool === 'LITERATURE_SEARCH') {
           const topic = step.description.replace('Search literature for', '').trim();
           const papers = await generateLiterature(topic);
           viz = { type: VisualizationType.LITERATURE_LIST, title: `Literature: ${topic}`, data: papers };
           stepResult = `Found ${papers.length} relevant papers.`;
        }
        else {
           stepResult = `Unknown tool: ${step.tool}. Skipping.`;
        }
      } catch (e: any) {
        stepResult = `Error: ${e.message}`;
      }

      setMessages(prev => prev.map(m => 
        m.id === executorMsg.id ? { ...m, content: `${m.content}\n\n\u2705 ${stepResult}` } : m
      ));

      if (viz) {
        viz.messageId = executorMsg.id;
        addVisualization(viz);
      }
      
      resultsSummary.push(`Step ${step.step_id} (${step.tool}): ${stepResult}`);
      await new Promise(r => setTimeout(r, 1000));
    }

    // Final execution step done
    wf.setExecutionProgress(totalSteps, totalSteps);

    if (intent === 'RESEARCH') {
      wf.setPhase('researching');

      const researchMsg = addMessage(AgentType.RESEARCHER, "Reviewing findings and generating report...");
      const finalInsights = await generateResearchInsights(resultsSummary.join('\n'));
      
      setMessages(prev => prev.map(m => 
        m.id === researchMsg.id ? { ...m, content: finalInsights } : m
      ));

      addVisualization({
        type: VisualizationType.RESEARCH_REPORT,
        title: "Scientific Research Report",
        data: {
          report: finalInsights,
          stepIdToMessageId
        },
        messageId: researchMsg.id
      });

    } else {
      addMessage(AgentType.SYSTEM, "Task complete.");
    }

    wf.setPhase('done');
  };

  const handleRestartFromStep = async (messageId: string, newParams: any) => {
    if (!dataset) return;
    const msgIndex = messages.findIndex(m => m.id === messageId);
    if (msgIndex === -1) return;
    const msg = messages[msgIndex];

    if (msg.role === AgentType.EXECUTOR) {
        if (!msg.metadata || msg.metadata.stepIndex === undefined) return;
        const { plan, stepIndex } = msg.metadata;
        const newMessages = messages.slice(0, msgIndex);
        setMessages(newMessages);
        const validMessageIds = new Set(newMessages.map(m => m.id));
        setVisualizations(prev => prev.filter(v => !v.messageId || validMessageIds.has(v.messageId)));
        setIsProcessing(true);
        addMessage(AgentType.SYSTEM, `Restarting execution from Step ${stepIndex + 1} with updated parameters...`);
        await executePlanSteps(plan, stepIndex, newParams, [...dataset.data], [...dataset.columns], 'RESEARCH');
        setIsProcessing(false);
    } 
    else if (msg.role === AgentType.NEURO_PLANNER || msg.role === AgentType.GENERAL_PLANNER) {
        const newPlan = newParams;
        const intent = msg.role === AgentType.NEURO_PLANNER ? 'RESEARCH' : 'GENERAL';
        const newMessages = messages.slice(0, msgIndex + 1);
        newMessages[msgIndex] = {
            ...msg,
            metadata: { ...msg.metadata, plan: newPlan },
            content: `**Plan Updated Manually:**\n${newPlan.analysis_steps.map((s: any) => `${s.step_id}. ${s.tool}: ${s.description}`).join('\n')}\n\nRationale: ${newPlan.rationale || 'Manual update'}`
        };
        setMessages(newMessages);
        const validMessageIds = new Set(newMessages.map(m => m.id));
        setVisualizations(prev => prev.filter(v => !v.messageId || validMessageIds.has(v.messageId)));
        setIsProcessing(true);
        
        wf.setPhase('validating');
        addMessage(AgentType.PLAN_VALIDATOR, "Validating manually updated plan...");
        const validation = await validatePlan(newPlan, [...INTERNAL_TOOLS, ...mcpTools], dataset.columns);
        
        if (!validation.valid) {
            addMessage(AgentType.PLAN_VALIDATOR, `\u26a0\ufe0f Validation Error: ${validation.errors.join(', ')}\n\nSuggestion: ${validation.suggestions}`);
            setIsProcessing(false);
            return;
        }

        addMessage(AgentType.PLAN_VALIDATOR, "Plan validated successfully. Resuming execution...");
        
        wf.setPhase('executing');
        await executePlanSteps(newPlan, 0, null, [...dataset.data], [...dataset.columns], intent);
        setIsProcessing(false);
    }
  };

  const handleUserQuery = async (query: string) => {
    if (!dataset) return;
    
    addMessage(AgentType.USER, query);
    setIsProcessing(true);
    wf.startNewQuery(query, messages.length);

    try {
      if (!ollamaConnected) {
         const recheck = await checkOllamaConnection();
         if (!recheck) {
            addMessage(AgentType.SYSTEM, "Error: Ollama is still unreachable.");
            wf.setPhase('error');
            setIsProcessing(false);
            return;
         }
         setOllamaConnected(true);
      }

      // ═══ ORCHESTRATOR ═══
      addMessage(AgentType.ORCHESTRATOR, "Evaluating query intent...");
      const intent = await classifyQuery(query);
      addMessage(AgentType.ORCHESTRATOR, `Identified intent: ${intent}`);

      // ═══ PLANNER ═══
      wf.setPhase('planning');

      const allTools = [...INTERNAL_TOOLS, ...mcpTools];
      let plan: any = { analysis_steps: [] };
      let planIsValid = false;
      let planningRetries = 0;
      const MAX_PLANNING_RETRIES = 3;
      let currentFeedback = "";

      while (!planIsValid && planningRetries < MAX_PLANNING_RETRIES) {
        if (intent === 'RESEARCH') {
          addMessage(AgentType.NEURO_PLANNER, planningRetries === 0 ? "Formulating research analysis plan..." : "Refining research plan based on feedback...");
          plan = await generateNeuroPlan(query, dataset.columns.join(', '), allTools, currentFeedback);
          addMessage(AgentType.NEURO_PLANNER, `Plan created:\n${plan.analysis_steps.map((s: any) => `${s.step_id}. ${s.tool}: ${s.description}`).join('\n')}\n\nRationale: ${plan.rationale}`, { plan });
        } else {
          addMessage(AgentType.GENERAL_PLANNER, planningRetries === 0 ? "Formulating general task plan..." : "Refining general plan based on feedback...");
          plan = await generateGeneralPlan(query, allTools, currentFeedback);
          addMessage(AgentType.GENERAL_PLANNER, `Plan created:\n${plan.analysis_steps.map((s: any) => `${s.step_id}. ${s.tool}: ${s.description}`).join('\n')}`, { plan });
        }

        // ═══ VALIDATOR ═══
        wf.setPhase('validating');

        addMessage(AgentType.PLAN_VALIDATOR, "Verifying analysis steps...");
        const validation = await validatePlan(plan, allTools, dataset.columns);

        if (validation.valid) {
          planIsValid = true;
          addMessage(AgentType.PLAN_VALIDATOR, "Plan verified. Proceeding to execution.");
        } else {
          planningRetries++;
          currentFeedback = `Validation errors: ${validation.errors.join(', ')}. Suggestions: ${validation.suggestions}`;
          addMessage(AgentType.PLAN_VALIDATOR, `Plan rejected (Attempt ${planningRetries}/${MAX_PLANNING_RETRIES}):\n${validation.errors.map((e: string) => `- ${e}`).join('\n')}\n\nProviding feedback to Planner for correction...`);
          
          // Go back to planning phase for retry
          wf.setPhase('planning');

          if (planningRetries >= MAX_PLANNING_RETRIES) {
            wf.setPhase('error');
            addMessage(AgentType.SYSTEM, "Critical: Planning failed to stabilize after multiple validation cycles. Stopping execution.");
            setIsProcessing(false);
            return;
          }
        }
      }

      // ═══ EXECUTOR ═══
      wf.setPhase('executing');

      await executePlanSteps(plan, 0, null, [...dataset.data], [...dataset.columns], intent);

    } catch (error) {
      console.error(error);
      addMessage(AgentType.SYSTEM, "An error occurred during the workflow.");
      wf.setPhase('error');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleVizClick = (messageId?: string) => {
    if (messageId) {
        setHighlightedMessageId(messageId);
    }
  };

  return (
    <div className="flex h-screen w-full overflow-hidden bg-slate-950 text-slate-200">
      <div className="w-1/2 p-4 flex flex-col h-full border-r border-slate-800">
        <header className="mb-4 flex-none flex flex-col gap-2">
           <div className="flex justify-between items-center">
            <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
              <span className="bg-indigo-600 p-1 rounded-lg">NA</span>
              NeuroAgent <span className="text-slate-500 font-normal">Platform</span>
            </h1>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${ollamaConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-slate-500">Ollama</span>
              </div>
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${mcpConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-xs text-slate-500">MCP</span>
              </div>
            </div>
          </div>
          
          {availableModels.length > 0 && (
            <div className="flex gap-2 text-xs">
              <div className="flex flex-col gap-1 w-1/2">
                <label className="text-slate-500">General Model</label>
                <select 
                  value={selectedGeneralModel} 
                  onChange={handleGeneralModelChange}
                  className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-indigo-500"
                >
                  {availableModels.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1 w-1/2">
                <label className="text-slate-500">Neuro Model</label>
                <select 
                  value={selectedNeuroModel} 
                  onChange={handleNeuroModelChange}
                  className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-indigo-500"
                >
                  {availableModels.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </div>
            </div>
          )}
        </header>
        <div className="flex-1 min-h-0">
          <VisualizerArea 
            visualizations={visualizations} 
            datasetName={dataset?.name} 
            onVizClick={handleVizClick}
          />
        </div>
      </div>

      <div className="w-1/2 h-full flex flex-col">
        <ChatArea 
          messages={messages} 
          onSendMessage={handleUserQuery} 
          onFileUpload={handleFileUpload}
          onLoadDemo={handleLoadDemo}
          isProcessing={isProcessing}
          hasData={!!dataset}
          highlightedMessageId={highlightedMessageId}
          onRestartStep={handleRestartFromStep}
          workflow={workflowState}
        />
      </div>
    </div>
  );
};

export default App;
