import json
import re
import uvicorn
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agent_client import OllamaLLM

class ManipulationRequest(BaseModel):
    """Input payload from the frontend or planner agent"""
    user_query: str
    available_files: list[str] = Field(..., description="List of dataset file paths currently available to the user.")
    raw_datasets: dict = Field(default={}, description="A mapping of filename to a list of dicts (the actual data).")

class ManipulationResult(BaseModel):
    """Output sent back to the network to execute the tool"""
    tool_to_call: str = Field(..., description="The exact name of the MCP tool to execute (e.g., 'merge_datasets').")
    parameters: dict = Field(..., description="The JSON parameters to pass into the tool.")
    explanation: str = Field(..., description="Brief explanation of what the agent decided to do.")
    merged_csv_data: str = Field(default="", description="The raw CSV data if a merge was performed successfully.")

class DataManipulatorAgent:
    def __init__(self, llm_client):
        self.llm = llm_client

    def plan_manipulation(self, user_query: str, available_files: list[str], raw_datasets: dict) -> ManipulationResult:
        
        system_prompt = (
            "You are a Senior Data Engineering Agent.\n"
            "Your Job: Listen to the user's request and decide how to manipulate their datasets.\n"
            "Currently, you have access to the following tools:\n"
            "1. 'merge_datasets' (Parameters: file_paths (list of strings), output_filename (string), join_columns (list of strings))\n"
            "   - Use 'join_columns' if the user specifies one or more columns to merge on (e.g., ['Case', 'age']). Provide an empty list if unknown.\n"
            "You must return ONLY a JSON object."
        )

        user_prompt = f"""
        ### TASK
        Determine which data manipulation tool to call based on the user's query.

        **User Query:** "{user_query}"
        **Available Files:** {available_files}

        ### REQUIRED OUTPUT FORMAT (JSON ONLY)
        {{
            "tool_to_call": "merge_datasets",
            "parameters": {{
                "file_paths": ["file_A.csv", "file_B.csv"],
                "output_filename": "merged_output.csv",
                "join_columns": ["ID"]
            }},
            "explanation": "Merging file A and B based on the user request."
        }}
        """

        # Call the LLM 
        try:
            raw_response = self.llm.generate_text(user_prompt, system=system_prompt)
            parsed_result = self._clean_and_parse(raw_response)
            
            # Execute the merge immediately on the backend if merge_datasets was selected
            if parsed_result.tool_to_call == "merge_datasets":
                file_paths = parsed_result.parameters.get("file_paths", [])
                join_columns = parsed_result.parameters.get("join_columns", [])
                
                if isinstance(join_columns, str):
                    join_columns = [join_columns] if join_columns else []
                
                # Robust matching: If the LLM returned nothing, but we only have 2 files in the context, just use them.
                if not file_paths and len(raw_datasets) >= 2:
                    file_paths = list(raw_datasets.keys())
                elif not isinstance(file_paths, list):
                    file_paths = [file_paths]

                # Fetch data from the provided raw_datasets mapped from the frontend
                dfs = []
                seen_keys = set()
                
                # Pre-filter file_paths to prevent LLM hallucinating the same file twice
                unique_fps = []
                for fp in file_paths:
                    if fp not in unique_fps:
                        unique_fps.append(fp)

                for fp in unique_fps:
                    matched_key = None
                    # Exact match
                    if fp in raw_datasets:
                        matched_key = fp
                    else:
                        # Fuzzy match (substring)
                        for raw_k in raw_datasets.keys():
                            if fp.lower() in raw_k.lower() or raw_k.lower() in fp.lower():
                                matched_key = raw_k
                                break
                    
                    if matched_key and matched_key not in seen_keys:
                        # Convert frontend dict records back to pandas dataframe
                        df = pd.DataFrame(raw_datasets[matched_key])
                        dfs.append(df)
                        seen_keys.add(matched_key)
                    elif not matched_key:
                        parsed_result.explanation += f" (Warning: File '{fp}' not found in uploaded dataset context)"
                
                # Fallback: if we still didn't find at least 2 datasets, but the context has 2+ files, just grab the first two.
                if len(dfs) < 2 and len(raw_datasets) >= 2:
                    dfs = []
                    for k, data in list(raw_datasets.items())[:2]:
                        dfs.append(pd.DataFrame(data))
                    parsed_result.explanation += " (Fallback: Merged available files because specific matches failed.)"

                if len(dfs) >= 2:
                    try:
                        # Helper to find a fuzzy column match in a dataframe
                        def find_col(df, query_col):
                            if query_col in df.columns:
                                return query_col
                            # Fuzzy check: case insensitive or substring
                            for c in df.columns:
                                if query_col.lower() == c.lower() or query_col.lower() in c.lower() or c.lower() in query_col.lower():
                                    return c
                            return None

                        # Match join_columns for each dataframe independently
                        df_join_keys = [[] for _ in dfs]
                        valid_merge = False

                        if join_columns:
                            valid_merge = True
                            for req_col in join_columns:
                                for i, df in enumerate(dfs):
                                    matched_col = find_col(df, req_col)
                                    if matched_col:
                                        df_join_keys[i].append(matched_col)
                                    else:
                                        valid_merge = False # Missing column in at least one DF
                        
                        # The Universal Fix: Dynamic Intersection
                        # If no explicit join_columns were provided or they failed, find the exact intersection of all columns.
                        if not valid_merge:
                            # Find common columns across all dataframes (case-insensitive intersection)
                            common_cols_lower = set(col.lower() for col in dfs[0].columns)
                            for df in dfs[1:]:
                                common_cols_lower = common_cols_lower.intersection(set(col.lower() for col in df.columns))
                            
                            if common_cols_lower:
                                valid_merge = True
                                df_join_keys = [[] for _ in dfs]
                                # Map the lowercased common columns back to their original case for each dataframe
                                for c_lower in common_cols_lower:
                                    for i, df in enumerate(dfs):
                                        for orig_col in df.columns:
                                            if orig_col.lower() == c_lower:
                                                df_join_keys[i].append(orig_col)
                                                break
                        
                        if valid_merge:
                            merged_df = dfs[0]
                            left_keys = df_join_keys[0]
                            
                            for i, df in enumerate(dfs[1:], start=1):
                                right_keys = df_join_keys[i]
                                
                                # Perform merge mapping left keys to right keys
                                merged_df = pd.merge(merged_df, df, left_on=left_keys, right_on=right_keys, how='outer', suffixes=('', f'_file{i+1}'))
                                
                                # If the right keys had a different name than the left keys, drop the redundant right key column
                                for l_key, r_key in zip(left_keys, right_keys):
                                    if l_key != r_key and r_key in merged_df.columns:
                                        merged_df.drop(columns=[r_key], inplace=True)
                            
                            # Move join columns to front
                            cols = left_keys + [c for c in merged_df.columns if c not in left_keys]
                            merged_df = merged_df[cols]
                        else:
                            # If absolutely no columns match, attempting to concat horizontally is dangerous for medical data
                            # because it assumes perfect row alignment. We will reject the merge to prevent silent data corruption.
                            raise ValueError("Cannot merge datasets: No common columns found to join on, and horizontal concatenation is unsafe.")
                        
                        # Convert back to CSV string to send to frontend (na_rep outputs empty string for NaNs)
                        parsed_result.merged_csv_data = merged_df.to_csv(index=False, na_rep="")
                        parsed_result.explanation += " Merge executed successfully on the backend."
                    except Exception as merge_err:
                        parsed_result.tool_to_call = "error"
                        parsed_result.explanation = f"Backend merge failed: {str(merge_err)}"
                        
            return parsed_result
        except Exception as e:
            return ManipulationResult(
                tool_to_call="error", 
                parameters={}, 
                explanation=f"LLM Error: {str(e)}"
            )

    def _clean_and_parse(self, raw_text: str) -> ManipulationResult:
        """Helper to extract JSON from LLM chatter."""
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if not match:
            return ManipulationResult(tool_to_call="error", parameters={}, explanation="Agent returned invalid JSON.")
        
        try:
            data = json.loads(match.group(0))
            return ManipulationResult(**data)
        except Exception:
            return ManipulationResult(tool_to_call="error", parameters={}, explanation="JSON parsing failed.")

# Mock Client for offline testing
class MockOllamaLLM:
    def __init__(self, host, model):
        print(f"Offline Mode: Simulating {model}...")

    def generate_text(self, prompt, system=None):
        return '{"tool_to_call": "merge_datasets", "parameters": {"file_paths": ["test1.csv", "test2.csv"], "output_filename": "merged.csv"}, "explanation": "Simulation Mode"}'

app = FastAPI(title="Data Manipulator Agent Server")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize the LLM Client
try:
    print("Attempting connection to LLM...")
    llm = OllamaLLM(
        host='http://localhost:11434', # Standard local Ollama port
        model='qwen3:latest' # Using the general model specified in README
    )
    llm.client.list() 
    print("Connected to LLM!")
except Exception as e:
    print(f"Connection Failed: {e}")
    print("Switching to MOCK MODE.")
    llm = MockOllamaLLM(host='fake', model='fake')

agent = DataManipulatorAgent(llm)

@app.post("/manipulate", response_model=ManipulationResult)
async def manipulate_endpoint(request: ManipulationRequest):
    """
    Endpoint for the UI or Orchestrator to call.
    Usage: POST http://localhost:8015/manipulate
    """
    print(f"Received data manipulation request: {request.user_query}")
    result = agent.plan_manipulation(request.user_query, request.available_files, request.raw_datasets)
    return result

if __name__ == "__main__":
    # The team's ports: Planner=8011, Executor=8012, Researcher=9013, Validator=8014. 
    # Use 8015 for the Manipulator
    print("Starting Data Manipulator A2A Server on Port 8015")
    uvicorn.run(app, host="0.0.0.0", port=8015)
