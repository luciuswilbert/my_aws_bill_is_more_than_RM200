"""
Text File to Cultural Analysis Pipeline
Simple flow: Text File -> Bedrock Flow -> Analysis JSON
"""
import boto3
import json
import os
from dotenv import load_dotenv

load_dotenv()

class BedrockFlowInvoker:
    """
    Invokes a Bedrock Flow for cultural analysis.
    """
    def __init__(self, flow_id="CJB0RNM9XM", flow_alias="I4LBMMG8G8"):
        """
        Initializes the invoker with a Bedrock Agent Runtime client.
        """
        self.region = os.getenv('AWS_DEFAULT_REGION', 'us-east-1')
        self.client = boto3.client("bedrock-agent-runtime", region_name=self.region)
        self.flow_id = flow_id
        self.flow_alias = flow_alias

    def invoke_cultural_analysis_flow(self, text_content, country="Malaysia", file_type="text"):
        """
        Invokes the cultural analysis flow with the given text content
        and streams the response.
        """
        try:
            # Build input document based on the user's example
            input_document = {
                "content": text_content,
                "country": country,
                "file_type": file_type
            }

            # Invoke the flow
            response = self.client.invoke_flow(
                flowIdentifier=self.flow_id,
                flowAliasIdentifier=self.flow_alias,
                enableTrace=True,
                inputs=[
                    {
                        "content": {
                            "document": input_document
                        },
                        "nodeName": "FlowInputNode",
                        "nodeOutputName": "document"
                    }
                ]
            )

            final_output = None
            for event in response["responseStream"]:
                # Each event is a dict with exactly one key
                for event_type, event_value in event.items():
                    if event_type == "flowOutputEvent":
                        # The output is nested under 'content' and then 'document'
                        output_value = event_value.get('content', {}).get('document')
                        if output_value:
                            final_output = output_value
                    elif event_type == "exception":
                        # In a server environment, this should be logged properly.
                        print(f"Exception received from Bedrock Flow: {json.dumps(event_value)}")

            return final_output

        except Exception as e:
            print(f"Error invoking Bedrock Flow: {e}")
            return None


def process_text_and_get_analysis(file_path: str) -> dict:
    """
    Processes a single text file and runs it through a cultural analysis
    Bedrock Flow. Designed for server use.

    Args:
        file_path (str): The path to the text file.

    Returns:
        dict: A dictionary containing the analysis result or an error message.
    """
    print(f"Step 1: Reading content from text file '{file_path}'...")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            text_content = f.read()
    except FileNotFoundError:
        print(f"...error: file not found at '{file_path}'.")
        return {"error": f"File not found: {file_path}"}
    except Exception as e:
        print(f"...error reading file: {e}")
        return {"error": f"Failed to read file: {e}"}
    print("...text content read successfully.")

    print("Step 2: Invoking cultural analysis flow...")
    flow_invoker = BedrockFlowInvoker()
    flow_result = flow_invoker.invoke_cultural_analysis_flow(text_content)

    if not flow_result:
        print("...failed to get result from Bedrock Flow.")
        return {"error": "Failed to get result from Bedrock Flow."}
    print("...analysis received successfully.")

    return flow_result


def main():
    text_files = [f for f in os.listdir('.') if f.lower().endswith('.txt')]

    if text_files:
        text_file = text_files[0]
        print(f"Found text file: {text_file}. Starting analysis pipeline...")
        analysis_result = process_text_and_get_analysis(text_file)

        print("\n--- Final Analysis Result (JSON) ---")
        print(json.dumps(analysis_result, indent=2))
        print("------------------------------------")
    else:
        print("No text files with extension (.txt) found in the current directory.")


if __name__ == "__main__":
    main()
